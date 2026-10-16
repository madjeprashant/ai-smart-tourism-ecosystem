from __future__ import annotations

from typing import Any

from . import geoapify_service
from . import osm_service
from . import provider_manager


def _geoapify(destination: str) -> dict[str, Any]:
    geocoded = geoapify_service.geocode(destination, limit=1)

    if not geocoded:
        raise LookupError(
            f"Geoapify could not geocode destination: {destination}"
        )

    location = geocoded[0]
    latitude = location.get("latitude")
    longitude = location.get("longitude")

    if latitude is None or longitude is None:
        raise LookupError(
            f"Geoapify returned invalid coordinates for: {destination}"
        )

    restaurants = geoapify_service.places(
        latitude,
        longitude,
        categories="catering.restaurant",
        radius=5000,
        limit=20,
        place_id=(
            location.get("place_id")
            if location.get("is_area")
            else None
        ),
    )

    restaurants = geoapify_service.filter_by_category(
        restaurants or [],
        category="restaurant",
    )

    return {
        "destination": destination,
        "restaurants": restaurants,
    }


def _osm(destination: str) -> dict[str, Any]:
    return {
        "destination": destination,
        "restaurants": osm_service.nearby(
            destination,
            "restaurant",
        ) or [],
    }


def get_restaurants(destination: str) -> dict[str, Any]:
    """Return restaurants using Geoapify -> OSM -> no data."""
    destination = destination.strip()

    if not destination:
        raise ValueError("Destination cannot be empty")

    result = provider_manager.run(
        destination=destination,
        quota_provider="geoapify",
        live_provider="Geoapify",
        live_call=lambda: _geoapify(destination),
        osm_call=lambda: _osm(destination),
        kind="restaurants",
    )

    if result.get("status") == "no_data":
        result["restaurants"] = []
        result.pop("data", None)

    return result
