"""
STEP 9 - PHASE 4
TRIP PLANNER END-TO-END VALIDATION

Purpose:
Validate the complete Trip Planner request flow through the existing
FastAPI application without calling Gemini, Nominatim, Overpass, or any
other external travel service.

This test intentionally uses:
- FastAPI TestClient for HTTP-level validation
- an isolated in-memory SQLite database
- a deterministic planner-generator stub

The real planner logic was already validated in Phase 2. Phase 4 checks
that the existing HTTP routes, personalization inputs, persistence, and
saved-itinerary ownership work together correctly.
"""

import json
from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.models import User
from app.routers import planner
from app.security import get_current_user


# ---------------------------------------------------------------------------
# ISOLATED TEST DATABASE
# ---------------------------------------------------------------------------

TEST_ENGINE = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(
    bind=TEST_ENGINE,
    autocommit=False,
    autoflush=False,
)

Base.metadata.create_all(bind=TEST_ENGINE)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# DETERMINISTIC PLANNER RESULT
# ---------------------------------------------------------------------------

CALLS = []


def fake_generate_personalized_itinerary(
    destination: str,
    days: int,
    interests: list[str],
    budget: float,
):
    """Deterministic replacement for external travel services."""
    CALLS.append(
        {
            "destination": destination,
            "days": days,
            "interests": list(interests),
            "budget": budget,
        }
    )

    activities = [
        {
            "type": "real_place",
            "name": "Promenade Beach",
            "title": "Promenade Beach",
            "description": "Beach visit and coastal walk.",
            "category": "beaches",
            "budget_inr": 200,
        },
        {
            "type": "real_place",
            "name": "Pondicherry Museum",
            "title": "Pondicherry Museum",
            "description": "Explore local history and culture.",
            "category": "culture",
            "budget_inr": 150,
        },
        {
            "type": "real_place",
            "name": "Local Food Street",
            "title": "Local Food Street",
            "description": "Try local cuisine.",
            "category": "food",
            "budget_inr": 500,
        },
    ]

    return {
        "destination": destination,
        "location": {
            "latitude": 11.9416,
            "longitude": 79.8083,
            "display_name": "Puducherry, India",
        },
        "days": days,
        "budget": budget,
        "interests": interests,
        "planner_version": "V11",
        "data_source": "OpenStreetMap + personalized recommendation engine",
        "real_places_found": 3,
        "selected_real_places": 3,
        "itinerary": [
            {
                "day": day,
                "theme": "Personalized travel day",
                "destination": destination,
                "budget_level": "moderate",
                "activities": activities,
                "guide_sections": [
                    {
                        "title": item["title"],
                        "description": item["description"],
                        "category": item["category"],
                        "budget_inr": item["budget_inr"],
                    }
                    for item in activities
                ],
            }
            for day in range(1, days + 1)
        ],
    }


# ---------------------------------------------------------------------------
# TEST HELPERS
# ---------------------------------------------------------------------------

def reset_database():
    Base.metadata.drop_all(bind=TEST_ENGINE)
    Base.metadata.create_all(bind=TEST_ENGINE)

    db = TestSessionLocal()

    user_a = User(
        full_name="Phase 4 User A",
        email="phase4a@example.com",
        phone="9000000001",
        password="test-password",
        role="traveler",
    )
    user_b = User(
        full_name="Phase 4 User B",
        email="phase4b@example.com",
        phone="9000000002",
        password="test-password",
        role="traveler",
    )

    db.add_all([user_a, user_b])
    db.commit()
    db.refresh(user_a)
    db.refresh(user_b)

    db.close()

    CALLS.clear()

    return user_a.id, user_b.id


def main():
    user_a_id, user_b_id = reset_database()

    # Preserve the real application objects and restore them at the end.
    original_generator = planner.generate_personalized_itinerary

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = (
        lambda: {"sub": "phase4a@example.com"}
    )
    planner.generate_personalized_itinerary = (
        fake_generate_personalized_itinerary
    )

    checks = []

    client = TestClient(app)

    payload = {
        "destination": "Pondicherry",
        "days": 3,
        "budget": 10000,
        "interests": ["culture", "food", "beaches"],
    }

    # -----------------------------------------------------------------------
    # 1. PUBLIC PREVIEW
    # -----------------------------------------------------------------------

    preview_response = client.post(
        "/api/itineraries/preview",
        json=payload,
    )

    preview_ok = (
        preview_response.status_code == 200
        and preview_response.json().get("destination") == "Pondicherry"
        and preview_response.json().get("days") == 3
        and preview_response.json().get("budget") == 10000
        and preview_response.json().get("interests")
        == ["culture", "food", "beaches"]
        and isinstance(preview_response.json().get("itinerary"), list)
        and len(preview_response.json()["itinerary"]) == 3
    )

    checks.append(
        (
            "Public preview accepts the planner request",
            preview_ok,
        )
    )

    checks.append(
        (
            "Preview works without an Authorization header",
            "authorization" not in preview_response.request.headers,
        )
    )

    checks.append(
        (
            "Preview passes destination, duration, budget and interests to generator",
            any(
                call == {
                    "destination": "Pondicherry",
                    "days": 3,
                    "interests": ["culture", "food", "beaches"],
                    "budget": 10000,
                }
                for call in CALLS
            ),
        )
    )

    checks.append(
        (
            "Preview returns personalized itinerary structure",
            preview_ok
            and all(
                day.get("activities")
                and day.get("guide_sections")
                for day in preview_response.json()["itinerary"]
            ),
        )
    )

    # -----------------------------------------------------------------------
    # 2. AUTHENTICATED SAVE
    # -----------------------------------------------------------------------

    save_response = client.post(
        "/api/itineraries",
        json=payload,
    )

    save_data = save_response.json()

    checks.append(
        (
            "Authenticated save route accepts the same planner request",
            save_response.status_code == 200,
        )
    )

    checks.append(
        (
            "Saved itinerary belongs to the authenticated user",
            save_response.status_code == 200
            and save_data.get("user_id") == user_a_id,
        )
    )

    checks.append(
        (
            "Saved response preserves planner inputs and generated itinerary",
            save_response.status_code == 200
            and save_data.get("destination") == "Pondicherry"
            and save_data.get("days") == 3
            and save_data.get("budget") == 10000
            and save_data.get("interests")
            == ["culture", "food", "beaches"]
            and isinstance(save_data.get("itinerary"), list)
            and len(save_data["itinerary"]) == 3,
        )
    )

    required_saved_fields = {
        "id",
        "user_id",
        "destination",
        "days",
        "budget",
        "interests",
        "location",
        "planner_version",
        "data_source",
        "real_places_found",
        "selected_real_places",
        "itinerary",
        "created_at",
    }

    checks.append(
        (
            "Saved response exposes the complete planner contract",
            save_response.status_code == 200
            and required_saved_fields.issubset(save_data.keys()),
        )
    )

    trip_id = save_data.get("id")

    # -----------------------------------------------------------------------
    # 3. PERSISTENCE / RETRIEVAL
    # -----------------------------------------------------------------------

    own_list_response = client.get("/api/itineraries")

    checks.append(
        (
            "Saved itinerary is retrievable from the user's itinerary list",
            own_list_response.status_code == 200
            and own_list_response.json().get("count") == 1
            and any(
                item.get("id") == trip_id
                for item in own_list_response.json().get(
                    "itineraries", []
                )
            ),
        )
    )

    own_get_response = client.get(f"/api/itineraries/{trip_id}")

    checks.append(
        (
            "Saved itinerary can be retrieved by its own user",
            own_get_response.status_code == 200
            and own_get_response.json().get("id") == trip_id
            and own_get_response.json().get("destination")
            == "Pondicherry",
        )
    )

    # -----------------------------------------------------------------------
    # 4. USER ISOLATION
    # -----------------------------------------------------------------------

    app.dependency_overrides[get_current_user] = (
        lambda: {"sub": "phase4b@example.com"}
    )

    other_user_list_response = client.get("/api/itineraries")
    other_user_get_response = client.get(
        f"/api/itineraries/{trip_id}"
    )

    checks.append(
        (
            "Another user cannot see the saved itinerary in their list",
            other_user_list_response.status_code == 200
            and other_user_list_response.json().get("count") == 0,
        )
    )

    checks.append(
        (
            "Another user cannot retrieve the saved itinerary by ID",
            other_user_get_response.status_code == 404,
        )
    )

    # -----------------------------------------------------------------------
    # 5. INPUT VALIDATION STILL WORKS THROUGH HTTP
    # -----------------------------------------------------------------------

    invalid_payload = {
        "destination": "Pondicherry",
        "days": 0,
        "budget": 10000,
        "interests": ["food"],
    }

    invalid_response = client.post(
        "/api/itineraries/preview",
        json=invalid_payload,
    )

    checks.append(
        (
            "Invalid duration is rejected by the API contract",
            invalid_response.status_code == 422,
        )
    )

    # -----------------------------------------------------------------------
    # OUTPUT
    # -----------------------------------------------------------------------

    print("=" * 72)
    print("STEP 9 - PHASE 4")
    print("TRIP PLANNER END-TO-END VALIDATION")
    print("=" * 72)

    passed = 0

    for name, ok in checks:
        print(("PASS: " if ok else "FAIL: ") + name)
        passed += int(bool(ok))

    print("=" * 72)
    print(f"RESULT: {passed}/{len(checks)} tests passed")
    print("=" * 72)

    # Cleanup test overrides so importing/running this module does not
    # permanently alter the application object.
    planner.generate_personalized_itinerary = original_generator
    app.dependency_overrides.clear()

    if passed == len(checks):
        print("STEP 9 PHASE 4 END-TO-END VALIDATION PASSED")
        return 0

    print("STEP 9 PHASE 4 END-TO-END VALIDATION FAILED")
    print("Fix only the failed integration checks before continuing.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
