from __future__ import annotations

import json
import os
import threading
from datetime import date
from pathlib import Path
from typing import Any


_LOCK = threading.Lock()

DEFAULT_LIMITS = {
    "geoapify": 500,
}


def _storage_path() -> Path:
    configured = os.getenv("TRAVEL_QUOTA_STORAGE_PATH", "")
    if configured:
        return Path(configured)

    return Path(__file__).resolve().parents[1] / "data" / "provider_usage.json"


def _limit(provider: str) -> int:
    env_names = {
        "geoapify": "GEOAPIFY_DAILY_LIMIT",
    }

    raw = os.getenv(env_names.get(provider, ""), "")

    if raw.strip():
        try:
            return max(0, int(raw))
        except ValueError:
            pass

    return DEFAULT_LIMITS.get(provider, 0)


def _load() -> dict[str, Any]:
    path = _storage_path()

    if not path.exists():
        return {
            "date": date.today().isoformat(),
            "usage": {},
        }

    try:
        data = json.loads(path.read_text(encoding="utf-8"))

        if data.get("date") != date.today().isoformat():
            return {
                "date": date.today().isoformat(),
                "usage": {},
            }

        return data

    except (OSError, ValueError, TypeError):
        return {
            "date": date.today().isoformat(),
            "usage": {},
        }


def _save(data: dict[str, Any]) -> None:
    path = _storage_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2),
        encoding="utf-8",
    )


def get_status(provider: str) -> dict[str, Any]:
    with _LOCK:
        data = _load()

        used = int(
            data.get("usage", {}).get(provider, 0)
        )

        limit = _limit(provider)

        return {
            "provider": provider,
            "used": used,
            "limit": limit,
            "remaining": max(0, limit - used),
            "date": data["date"],
        }


def can_consume(provider: str) -> bool:
    status = get_status(provider)
    return status["used"] < status["limit"]


def consume(provider: str, amount: int = 1) -> bool:
    if amount <= 0:
        return True

    with _LOCK:
        data = _load()

        usage = data.setdefault("usage", {})

        used = int(
            usage.get(provider, 0)
        )

        limit = _limit(provider)

        if used + amount > limit:
            return False

        usage[provider] = used + amount

        _save(data)

        return True


def snapshot() -> dict[str, dict[str, Any]]:
    return {
        provider: get_status(provider)
        for provider in DEFAULT_LIMITS
    }