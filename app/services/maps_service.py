from __future__ import annotations

from typing import Any

from dotenv import load_dotenv

from . import geoapify_service
from . import osm_service
from . import provider_manager

load_dotenv()


def _geoapify(destination: str) -> dict[str, Any]:
    results = geoapify_service.geocode(destination, limit=1)

    if not results:
        raise LookupError("Geoapify returned no result")

    location = results[0]
    latitude = location.get("latitude")
    longitude = location.get("longitude")

    if latitude is None or longitude is None:
        raise LookupError("Geoapify returned invalid coordinates")

    return {
        "destination": destination,
        "coordinates": {
            "latitude": latitude,
            "longitude": longitude,
        },
        "destination_context": {
            "formatted": location.get("formatted") or destination,
            "place_type": location.get("place_type") or "",
            "is_area": bool(location.get("is_area")),
            "bounds": location.get("bounds"),
        },
        "map": {
            "provider": "Geoapify",
        },
    }


def _osm(destination: str) -> dict[str, Any]:
    location = osm_service.geocode(destination)

    if not location:
        raise LookupError("OSM returned no result")

    return {
        "destination": destination,
        "coordinates": {
            "latitude": location["latitude"],
            "longitude": location["longitude"],
        },
        "destination_context": {
            "formatted": location.get("display_name") or destination,
            "place_type": location.get("place_type") or "",
            "is_area": bool(location.get("is_area")),
            "bounds": location.get("bounds"),
        },
        "map": {
            "provider": "OpenStreetMap",
        },
    }


def get_map_data(destination: str) -> dict[str, Any]:
    """Return map coordinates using Geoapify -> OSM -> no data."""
    destination = destination.strip()

    if not destination:
        raise ValueError("Destination cannot be empty")

    result = provider_manager.run(
        destination=destination,
        quota_provider="geoapify",
        live_provider="Geoapify",
        live_call=lambda: _geoapify(destination),
        osm_call=lambda: _osm(destination),
        kind="coordinates",
    )

    if result.get("status") == "no_data":
        result["coordinates"] = {
            "latitude": None,
            "longitude": None,
        }
        result["map"] = {
            "provider": "OpenStreetMap",
        }
        result["destination_context"] = {
            "formatted": destination,
            "place_type": "",
            "is_area": False,
            "bounds": None,
        }
        result.pop("data", None)

    return result
