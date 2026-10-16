from __future__ import annotations

from . import geoapify_service
from . import osm_service
from . import provider_manager


def _geoapify(destination: str) -> dict:
    locations = geoapify_service.geocode(destination, limit=1)

    if not locations:
        raise LookupError(
            "Unable to geocode destination with Geoapify"
        )

    location = locations[0]
    latitude = location.get("latitude")
    longitude = location.get("longitude")

    if latitude is None or longitude is None:
        raise LookupError(
            "Geoapify geocoding returned no coordinates"
        )

    hotels = geoapify_service.places(
        latitude,
        longitude,
        categories="accommodation.hotel",
        radius=5000,
        limit=20,
        place_id=(
            location.get("place_id")
            if location.get("is_area")
            else None
        ),
    )

    hotels = geoapify_service.filter_by_category(
        hotels or [],
        category="hotel",
    )

    normalized = []

    for hotel in hotels:
        normalized.append(
            {
                "id": hotel.get("id"),
                "name": hotel.get("name", ""),
                "address": hotel.get("address", ""),
                "latitude": hotel.get("latitude"),
                "longitude": hotel.get("longitude"),
                "type": "hotel",
                "source": "Geoapify",
                "provider": "Geoapify",
                "website": hotel.get("website"),
                "phone": hotel.get("phone"),
                "opening_hours": hotel.get("opening_hours"),
            }
        )

    return {
        "destination": destination,
        "hotels": normalized,
    }


def _osm(destination: str) -> dict:
    return {
        "destination": destination,
        "hotels": osm_service.nearby(destination, "hotel") or [],
    }


def get_hotels(destination: str) -> dict:
    """Return hotels using Geoapify -> OSM -> no data."""
    destination = destination.strip()

    if not destination:
        raise ValueError("Destination cannot be empty")

    return provider_manager.run(
        destination=destination,
        quota_provider="geoapify",
        live_provider="Geoapify",
        live_call=lambda: _geoapify(destination),
        osm_call=lambda: _osm(destination),
        kind="hotels",
    )
