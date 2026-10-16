"""Centralized runtime configuration for VoyageAI.

The project intentionally keeps provider credentials and JWT secrets out of the
frontend.  Values are loaded from environment variables so local development,
testing, and final deployment can use different configuration safely.
"""

from __future__ import annotations

import os
import secrets
from typing import List

from dotenv import load_dotenv

load_dotenv(override=True)

APP_ENV = os.getenv("APP_ENV", "development").strip().lower()

# A fresh development secret is generated when the developer has not supplied
# one.  This is deliberately ephemeral: tokens become invalid after restart.
# Production deployments are required to provide JWT_SECRET_KEY explicitly.
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "").strip() or secrets.token_urlsafe(48)

JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256").strip() or "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./tourism.db").strip()


def _csv(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


CORS_ORIGINS = _csv(os.getenv("CORS_ORIGINS", "*")) or ["*"]


def validate_runtime_configuration() -> None:
    """Validate settings that must be explicit in production."""
    if APP_ENV == "production":
        supplied_secret = os.getenv("JWT_SECRET_KEY", "").strip()
        if not supplied_secret or len(supplied_secret) < 32:
            raise RuntimeError(
                "JWT_SECRET_KEY must be set to a random value of at least 32 "
                "characters when APP_ENV=production."
            )

        if "*" in CORS_ORIGINS:
            raise RuntimeError(
                "CORS_ORIGINS must list explicit trusted origins when APP_ENV=production."
            )
