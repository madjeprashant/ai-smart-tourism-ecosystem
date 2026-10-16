from __future__ import annotations

from typing import Any

from . import geoapify_service
from . import quota_manager


def get_route(
    start_latitude: float,
    start_longitude: float,
    end_latitude: float,
    end_longitude: float,
    *,
    mode: str = "drive",
) -> dict[str, Any]:
    """Return a Geoapify route while respecting the application quota."""

    mode = mode.strip().lower()

    if mode not in {"drive", "walk", "bicycle", "scooter", "truck"}:
        raise ValueError("Unsupported routing mode")

    if not quota_manager.can_consume("geoapify"):
        return {
            "type": "FeatureCollection",
            "features": [],
            "provider": "Geoapify",
            "source": "Geoapify",
            "live": False,
            "fallback": False,
            "status": "quota_exhausted",
        }

    quota_manager.consume("geoapify")

    result = geoapify_service.route(
        [
            (float(start_latitude), float(start_longitude)),
            (float(end_latitude), float(end_longitude)),
        ],
        mode=mode,
    )

    result["provider"] = "Geoapify"
    result["source"] = "Geoapify"
    result["live"] = True
    result["fallback"] = False
    result["status"] = "live"
    result["mode"] = mode

    return result
