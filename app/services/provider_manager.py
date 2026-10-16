from __future__ import annotations

from typing import Any, Callable


def mode() -> str:
    """Return the configured provider mode.

    The application supports the live Geoapify -> OpenStreetMap flow.
    Demo mode is retained as a safe no-data mode; it never serves
    fabricated provider results.
    """
    import os

    value = os.getenv("TRAVEL_PROVIDER_MODE", "auto").strip().lower()
    return value if value in {"auto", "live", "demo"} else "auto"


def _has_payload(result: dict[str, Any]) -> bool:
    """Return True when an OSM result contains actual records/data."""
    for value in result.values():
        if isinstance(value, list) and value:
            return True
        if isinstance(value, dict) and value:
            # Coordinates are meaningful payload for the maps service.
            if any(v is not None for v in value.values()):
                return True
    return False


def no_data_response(reason: str) -> dict[str, Any]:
    """Return the terminal response when neither live nor OSM has data."""
    return {
        "provider": "OpenStreetMap",
        "live": False,
        "fallback": True,
        "status": "no_data",
        "fallback_reason": reason,
        "data": [],
    }


def run(
    *,
    destination: str,
    quota_provider: str,
    live_provider: str,
    live_call: Callable[[], dict[str, Any]],
    osm_call: Callable[[], dict[str, Any]],
    kind: str,
) -> dict[str, Any]:
    """Execute the only supported provider chain: Geoapify -> OSM -> no data.

    `live_provider` is kept as a parameter so existing service calls remain
    explicit about their primary provider. No cached provider data is consulted.
    """
    import os
    from . import quota_manager

    current_mode = mode()

    if current_mode == "demo":
        return no_data_response("demo_mode_no_live_provider")

    if current_mode in {"auto", "live"} and quota_manager.can_consume(quota_provider):
        try:
            result = live_call()
            quota_manager.consume(quota_provider)
            result.update(
                {
                    "provider": live_provider,
                    "live": True,
                    "fallback": False,
                    "status": "live",
                }
            )
            return result
        except Exception:
            live_reason = "provider_error"
    else:
        live_reason = "daily_quota_exceeded"

    # Geoapify failed or its application quota was exhausted.
    # OpenStreetMap is the only permitted fallback.
    try:
        result = osm_call()
        result.update(
            {
                "provider": "OpenStreetMap",
                "live": True,
                "fallback": True,
                "status": "fallback" if _has_payload(result) else "no_data",
                "fallback_reason": live_reason,
            }
        )
        return result
    except Exception:
        # No cached or synthetic result: terminate with no data.
        return no_data_response(
            live_reason or "secondary_provider_error"
        )
