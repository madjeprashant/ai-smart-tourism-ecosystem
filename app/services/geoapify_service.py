import os
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

GEOAPIFY_API_KEY = os.getenv("GEOAPIFY_API_KEY", "").strip()

PLACES_API_URL = "https://api.geoapify.com/v2/places"
GEOCODING_API_URL = "https://api.geoapify.com/v1/geocode/search"
ROUTING_API_URL = "https://api.geoapify.com/v1/routing"

AREA_RESULT_TYPES = {
    "state",
    "region",
    "county",
    "district",
    "locality",
    "country",
}


def _normalise_bounds(item: dict[str, Any]) -> dict[str, float] | None:
    """Return a normalized south/west/north/east bounds object when available."""
    bbox = item.get("bbox")
    if isinstance(bbox, dict):
        candidates = {
            "south": bbox.get("lat1") or bbox.get("south"),
            "west": bbox.get("lon1") or bbox.get("west"),
            "north": bbox.get("lat2") or bbox.get("north"),
            "east": bbox.get("lon2") or bbox.get("east"),
        }
        if all(value is not None for value in candidates.values()):
            try:
                return {key: float(value) for key, value in candidates.items()}
            except (TypeError, ValueError):
                return None
    if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
        try:
            # GeoJSON-style bounds are normally west, south, east, north.
            return {
                "south": float(bbox[1]),
                "west": float(bbox[0]),
                "north": float(bbox[3]),
                "east": float(bbox[2]),
            }
        except (TypeError, ValueError):
            return None
    return None


def _require_api_key() -> None:
    if not GEOAPIFY_API_KEY:
        raise RuntimeError("Geoapify API key is not configured")


def _get(
    url: str,
    *,
    params: dict[str, Any],
    timeout: int = 10,
) -> dict[str, Any]:
    _require_api_key()

    response = requests.get(
        url,
        params={
            **params,
            "apiKey": GEOAPIFY_API_KEY,
        },
        timeout=timeout,
    )

    response.raise_for_status()
    return response.json()


def geocode(
    text: str,
    *,
    limit: int = 1,
) -> list[dict[str, Any]]:
    """
    Convert a place/address into coordinates using Geoapify.
    """

    text = text.strip()

    if not text:
        return []

    # The application is primarily intended for Indian tourism. For ambiguous
    # names such as "Kochi", prefer an Indian match first so Geoapify does not
    # select an unrelated place in another country. If the Indian-only lookup
    # has no result, fall back to a worldwide lookup so explicitly foreign
    # destinations remain supported.
    limit = max(1, min(limit, 10))
    params = {
        "text": text,
        "limit": limit,
        "format": "json",
    }

    params["filter"] = "countrycode:in"

    response = _get(GEOCODING_API_URL, params=params)

    # If a free-form foreign destination was supplied and the focused lookup
    # produced nothing, keep the service globally useful.
    if not response.get("results") and params.get("filter") == "countrycode:in":
        response = _get(
            GEOCODING_API_URL,
            params={
                "text": text,
                "limit": limit,
                "format": "json",
            },
        )

    results = []

    for item in response.get("results", []):
        result_type = str(
            item.get("result_type") or item.get("type") or ""
        ).strip().lower()
        results.append(
            {
                "name": item.get("name") or item.get("formatted", ""),
                "formatted": item.get("formatted", ""),
                "latitude": item.get("lat"),
                "longitude": item.get("lon"),
                "country": item.get("country"),
                "state": item.get("state"),
                "city": item.get("city"),
                "postcode": item.get("postcode"),
                "place_id": item.get("place_id"),
                "place_type": result_type,
                "is_area": result_type in AREA_RESULT_TYPES,
                "bounds": _normalise_bounds(item),
                "source": "Geoapify",
                "provider": "Geoapify",
            }
        )

    return results


def places(
    latitude: float,
    longitude: float,
    *,
    categories: str,
    radius: int = 5000,
    limit: int = 20,
    place_id: str | None = None,
) -> list[dict[str, Any]]:
    """Find real places near a point or inside a returned place boundary.

    Point destinations keep the existing circle search. For state/region
    destinations, ``place_id`` lets Geoapify search the useful geographic
    boundary instead of treating the state's centroid as the destination.
    """

    radius = max(100, min(radius, 50000))
    limit = max(1, min(limit, 100))

    params: dict[str, Any] = {
        "categories": categories,
        "limit": limit,
    }

    if place_id:
        params["filter"] = f"place:{place_id}"
        params["bias"] = f"proximity:{longitude},{latitude}"
    else:
        params["filter"] = f"circle:{longitude},{latitude},{radius}"
        params["bias"] = f"proximity:{longitude},{latitude}"

    response = _get(
        PLACES_API_URL,
        params=params,
    )

    results = []

    for feature in response.get("features", []):
        properties = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}

        coordinates = geometry.get("coordinates") or []

        lon = properties.get("lon")
        lat = properties.get("lat")

        if len(coordinates) >= 2:
            lon = coordinates[0]
            lat = coordinates[1]

        name = (
            properties.get("name")
            or properties.get("formatted")
            or "Unnamed place"
        )

        results.append(
            {
                "id": properties.get("place_id"),
                "name": name,
                "address": properties.get("formatted", ""),
                "latitude": lat,
                "longitude": lon,
                "distance": properties.get("distance"),
                "categories": properties.get("categories", []),
                "website": properties.get("website"),
                "phone": properties.get("phone"),
                "opening_hours": properties.get("opening_hours"),
                "cuisine": properties.get("cuisine"),
                "type": "real_place",
                "source": "Geoapify",
                "provider": "Geoapify",
            }
        )

    return results


def filter_by_category(
    places: list[dict[str, Any]],
    *,
    category: str,
) -> list[dict[str, Any]]:
    """Keep places whose provider categories are compatible with the UI bucket.

    Geoapify normally enforces the requested category at query time, but a
    place can belong to more than one category.  For the Travel Explorer UI
    we keep restaurants and accommodations separated when the provider
    explicitly reports a conflicting top-level category.  Missing category
    metadata is preserved so OSM/demo/test records are not discarded merely
    because they use a different schema.
    """
    if category not in {"restaurant", "hotel"}:
        return list(places)

    kept: list[dict[str, Any]] = []

    for place in places:
        raw_categories = place.get("categories")
        categories = [str(value).strip().lower() for value in (raw_categories or [])]

        if not categories:
            kept.append(place)
            continue

        if category == "restaurant":
            has_accommodation = any(
                value == "accommodation" or value.startswith("accommodation.")
                for value in categories
            )
            if has_accommodation:
                continue
        else:
            has_catering = any(
                value == "catering" or value.startswith("catering.")
                for value in categories
            )
            if has_catering:
                continue

        kept.append(place)

    return kept


def route(
    waypoints: list[tuple[float, float]],
    *,
    mode: str = "drive",
) -> dict[str, Any]:
    """
    Calculate a route through two or more waypoints.

    Each waypoint is supplied as:
        (latitude, longitude)
    """

    if len(waypoints) < 2:
        raise ValueError("At least two waypoints are required")

    waypoint_string = "|".join(
        f"{latitude},{longitude}"
        for latitude, longitude in waypoints
    )

    response = _get(
        ROUTING_API_URL,
        params={
            "waypoints": waypoint_string,
            "mode": mode,
        },
    )

    response["provider"] = "Geoapify"
    response["source"] = "Geoapify"

    return response