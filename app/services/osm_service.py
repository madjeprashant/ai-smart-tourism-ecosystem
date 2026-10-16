from __future__ import annotations

import os
from typing import Any

import requests


AREA_RESULT_TYPES = {
    "administrative",
    "state",
    "region",
    "county",
    "district",
    "locality",
    "country",
}


NOMINATIM_URL = os.getenv(
    "OSM_NOMINATIM_URL",
    "https://nominatim.openstreetmap.org/search",
)

OVERPASS_URL = os.getenv(
    "OSM_OVERPASS_URL",
    "https://overpass-api.de/api/interpreter",
)

OVERPASS_FALLBACK_URLS = [
    url.strip()
    for url in os.getenv(
        "OSM_OVERPASS_FALLBACK_URLS",
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    ).split(",")
    if url.strip()
]

USER_AGENT = os.getenv(
    "OSM_USER_AGENT",
    "AI-Smart-Tourism-Ecosystem/1.0 (student project)",
)


def _http_get_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
) -> Any:
    response = requests.get(
        url,
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=12,
    )
    response.raise_for_status()
    return response.json()


def _http_post_json(url: str, *, data: str) -> Any:
    response = requests.post(
        url,
        data=data,
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def geocode(destination: str) -> dict[str, Any] | None:
    # Prefer Indian matches for ambiguous tourism destinations, while keeping
    # explicitly qualified foreign destinations supported. Nominatim supports
    # ISO-3166 country-code filtering through ``countrycodes``.
    params = {
        "q": destination,
        "format": "jsonv2",
        "limit": 1,
        "addressdetails": 1,
        "accept-language": "en",
    }

    params["countrycodes"] = "in"

    results = _http_get_json(NOMINATIM_URL, params=params)

    if not results:
        params.pop("countrycodes", None)
        results = _http_get_json(NOMINATIM_URL, params=params)

    if not results:
        return None

    first = results[0]

    address = first.get("address", {}) or {}
    result_type = str(
        first.get("addresstype") or first.get("type") or ""
    ).strip().lower()
    is_area = result_type in AREA_RESULT_TYPES or bool(
        address.get("state") and not address.get("city") and result_type in {
            "administrative", "boundary"
        }
    )

    boundingbox = first.get("boundingbox") or []
    bounds = None
    if isinstance(boundingbox, (list, tuple)) and len(boundingbox) >= 4:
        try:
            bounds = {
                "south": float(boundingbox[0]),
                "north": float(boundingbox[1]),
                "west": float(boundingbox[2]),
                "east": float(boundingbox[3]),
            }
        except (TypeError, ValueError):
            bounds = None

    return {
        "latitude": float(first["lat"]),
        "longitude": float(first["lon"]),
        "display_name": first.get("display_name", destination),
        "place_type": result_type,
        "is_area": is_area,
        "bounds": bounds,
        "osm_type": first.get("osm_type"),
        "osm_id": first.get("osm_id"),
    }


def _selectors(category: str, *, radius: int, lat: float, lon: float) -> list[str]:
    selectors = {
        "restaurant": [
            f"nwr[amenity=restaurant](around:{radius},{lat},{lon});",
            f"nwr[amenity=cafe](around:{radius},{lat},{lon});",
            f"nwr[amenity=fast_food](around:{radius},{lat},{lon});",
        ],
        "hotel": [
            f"nwr[tourism=hotel](around:{radius},{lat},{lon});",
            f"nwr[tourism=hostel](around:{radius},{lat},{lon});",
            f"nwr[tourism=guest_house](around:{radius},{lat},{lon});",
            f"nwr[tourism=motel](around:{radius},{lat},{lon});",
        ],
        "poi": [
            f"nwr[tourism=attraction](around:{radius},{lat},{lon});",
            f"nwr[tourism=museum](around:{radius},{lat},{lon});",
            f"nwr[tourism=gallery](around:{radius},{lat},{lon});",
            f"nwr[tourism=viewpoint](around:{radius},{lat},{lon});",
        ],
    }
    return selectors.get(category, selectors["poi"])


def nearby(destination: str, category: str) -> list[dict[str, Any]]:
    location = geocode(destination)

    if not location:
        return []

    lat, lon = location["latitude"], location["longitude"]

    # For state/region searches OSM does not offer the same convenient place-id
    # filter as Geoapify. Use a deliberately bounded regional search instead of
    # the old 3 km point search, avoiding an arbitrary state-centroid result.
    radius = 3000
    if location.get("is_area"):
        radius = int(os.getenv("OSM_REGION_SEARCH_RADIUS_METERS", "50000"))
        radius = max(10000, min(radius, 100000))

    query_parts = _selectors(category, radius=radius, lat=lat, lon=lon)

    query = (
        "[out:json][timeout:20];"
        + "".join(query_parts)
        + "out center tags;"
    )

    # Try the configured primary Overpass endpoint first.
    # If it fails, automatically try each configured fallback endpoint.
    overpass_urls = [OVERPASS_URL]

    for fallback_url in OVERPASS_FALLBACK_URLS:
        if fallback_url not in overpass_urls:
            overpass_urls.append(fallback_url)

    last_error: Exception | None = None

    for overpass_url in overpass_urls:
        try:
            raw = _http_post_json(overpass_url, data=query)
            break
        except Exception as exc:
            last_error = exc
    else:
        if last_error is not None:
            raise last_error
        return []

    items = []

    for element in raw.get("elements", []):
        tags = element.get("tags", {})
        center = element.get("center") or {}

        # Keep the two Travel Explorer buckets mutually exclusive when OSM
        # explicitly describes the same feature as both accommodation and a
        # food venue. A hotel may legitimately contain a restaurant, but the
        # restaurant card should not become a duplicate accommodation result.
        if category == "restaurant" and tags.get("tourism") in {
            "hotel", "hostel", "guest_house", "motel"
        }:
            continue
        if category == "hotel" and tags.get("amenity") in {
            "restaurant", "cafe", "fast_food"
        }:
            continue

        items.append(
            {
                "id": f"osm-{element.get('type', 'x')}-{element.get('id')}",
                "name": tags.get("name", "Unnamed place"),
                        "address": tags.get("addr:full")
                or ", ".join(
                    x
                    for x in [
                        tags.get("addr:street"),
                        tags.get("addr:city"),
                    ]
                    if x
                ),
                "latitude": element.get("lat", center.get("lat")),
                "longitude": element.get("lon", center.get("lon")),
                "type": (
                    tags.get("amenity")
                    or tags.get("tourism")
                    or tags.get("shop")
                    or category
                ),
                "source": "OpenStreetMap",
            }
        )

    return items