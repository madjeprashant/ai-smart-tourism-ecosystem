from __future__ import annotations

from typing import Any

import requests

from . import geoapify_service
from . import quota_manager

OSRM_ROUTE_URL = "https://router.project-osrm.org/route/v1/driving"


def _osrm_drive_route(
    start_latitude: float,
    start_longitude: float,
    end_latitude: float,
    end_longitude: float,
) -> dict[str, Any]:
    """Return a real driving route from the public OSRM demo service.

    OSRM's public demo endpoint supports driving only; it is not used to
    pretend that walking, cycling, scooter, or truck routes are available.
    """
    coordinates = (
        f"{float(start_longitude)},{float(start_latitude)};"
        f"{float(end_longitude)},{float(end_latitude)}"
    )
    response = requests.get(
        f"{OSRM_ROUTE_URL}/{coordinates}",
        params={"overview": "full", "geometries": "geojson", "steps": "true"},
        headers={"User-Agent": "AI-Smart-Tourism-Ecosystem/1.0"},
        timeout=12,
    )
    response.raise_for_status()
    payload = response.json()
    routes = payload.get("routes") or []
    if not routes or not (routes[0].get("geometry") or {}).get("coordinates"):
        raise RuntimeError("OSRM returned no route geometry")
    route = routes[0]
    return {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {
                "distance": route.get("distance"),
                "duration": route.get("duration"),
                "steps": [
                    step.get("maneuver", {}) | {
                        "name": step.get("name", ""),
                        "distance": step.get("distance"),
                        "duration": step.get("duration"),
                        "mode": step.get("mode"),
                        "type": step.get("maneuver", {}).get("type"),
                        "modifier": step.get("maneuver", {}).get("modifier"),
                    }
                    for leg in route.get("legs", [])
                    for step in leg.get("steps", [])
                ],
            },
            "geometry": route["geometry"],
        }],
        "provider": "OSRM",
        "source": "OSRM (OpenStreetMap data)",
        "live": True,
        "fallback": True,
        "status": "fallback",
        "mode": "drive",
    }


def get_route(
    start_latitude: float,
    start_longitude: float,
    end_latitude: float,
    end_longitude: float,
    *,
    mode: str = "drive",
) -> dict[str, Any]:
    """Return Geoapify directions, falling back to OSRM for driving routes."""
    mode = mode.strip().lower()
    if mode not in {"drive", "walk", "bicycle", "scooter", "truck"}:
        raise ValueError("Unsupported routing mode")

    geoapify_error: Exception | None = None
    if quota_manager.can_consume("geoapify"):
        try:
            result = geoapify_service.route(
                [(float(start_latitude), float(start_longitude)),
                 (float(end_latitude), float(end_longitude))],
                mode=mode,
            )
            quota_manager.consume("geoapify")
            result.update({
                "provider": "Geoapify", "source": "Geoapify",
                "live": True, "fallback": False, "status": "live", "mode": mode,
            })
            return result
        except Exception as exc:
            geoapify_error = exc
    else:
        geoapify_error = RuntimeError("Geoapify routing quota exhausted")

    if mode == "drive":
        try:
            return _osrm_drive_route(
                start_latitude, start_longitude, end_latitude, end_longitude
            )
        except Exception as fallback_error:
            raise RuntimeError(
                "Geoapify and OSRM routing providers are unavailable"
            ) from fallback_error

    # OSRM's public endpoint is driving-only. Do not return an incorrect route
    # for walking/cycling/truck modes when Geoapify is unavailable.
    raise RuntimeError(
        f"Geoapify routing is unavailable for mode '{mode}' and no compatible fallback exists"
    ) from geoapify_error
