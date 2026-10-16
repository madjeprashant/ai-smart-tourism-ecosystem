"""
STEP 17 - PHASE 4
AI TRAVEL PLANNER END-TO-END VALIDATION

Uses FastAPI TestClient, an isolated in-memory SQLite database, and a
deterministic planner stub. No real Gemini/Nominatim/Overpass calls occur.

Run:
    python -m tests.test_ai_travel_planner_step17_phase4
"""

from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.models import User
from app.routers import planner
from app.security import get_current_user


ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "app" / "static"

TEST_ENGINE = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(
    bind=TEST_ENGINE, autocommit=False, autoflush=False
)
Base.metadata.create_all(bind=TEST_ENGINE)

CALLS = []


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


def fake_generate_personalized_itinerary(destination, days, interests, budget):
    CALLS.append({
        "destination": destination,
        "days": days,
        "interests": list(interests),
        "budget": budget,
    })
    activities = [
        {
            "type": "real_place", "name": "Promenade Beach",
            "title": "Promenade Beach",
            "description": "Beach visit and coastal walk.",
            "category": "beaches", "budget_inr": 200,
        },
        {
            "type": "real_place", "name": "Pondicherry Museum",
            "title": "Pondicherry Museum",
            "description": "Explore local history and culture.",
            "category": "culture", "budget_inr": 150,
        },
        {
            "type": "real_place", "name": "Local Food Street",
            "title": "Local Food Street",
            "description": "Try local cuisine.",
            "category": "food", "budget_inr": 500,
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
                        "title": x["title"],
                        "description": x["description"],
                        "category": x["category"],
                        "budget_inr": x["budget_inr"],
                    }
                    for x in activities
                ],
            }
            for day in range(1, days + 1)
        ],
    }


def reset_database():
    Base.metadata.drop_all(bind=TEST_ENGINE)
    Base.metadata.create_all(bind=TEST_ENGINE)
    db = TestSessionLocal()
    a = User(
        full_name="Step 17 E2E User A",
        email="step17a@example.com",
        phone="9000000011",
        password="test-password",
        role="traveler",
    )
    b = User(
        full_name="Step 17 E2E User B",
        email="step17b@example.com",
        phone="9000000012",
        password="test-password",
        role="traveler",
    )
    db.add_all([a, b])
    db.commit()
    db.refresh(a)
    db.refresh(b)
    ids = (a.id, b.id)
    db.close()
    CALLS.clear()
    return ids


def read_static(name):
    path = STATIC_DIR / name
    return path.read_text(encoding="utf-8") if path.exists() else ""


def main():
    user_a_id, user_b_id = reset_database()
    original_generator = planner.generate_personalized_itinerary

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = (
        lambda: {"sub": "step17a@example.com"}
    )
    planner.generate_personalized_itinerary = (
        fake_generate_personalized_itinerary
    )

    checks = []
    index_source = read_static("index.html")
    js_source = read_static("app.js")

    payload = {
        "destination": "Pondicherry",
        "days": 3,
        "budget": 10000,
        "interests": ["culture", "food", "beaches"],
    }

    try:
        with TestClient(app) as client:
            checks.append((
                "E2E starts from the existing planner form",
                all(x in index_source for x in [
                    'id="plannerForm"', 'id="destination"',
                    'id="days"', 'id="budget"', 'id="interests"',
                ]),
            ))
            checks.append((
                "Frontend uses the planner preview endpoint",
                "/api/itineraries/preview" in js_source,
            ))
            checks.append((
                "Frontend carries all planner inputs",
                all(x in js_source for x in [
                    "destination", "days", "budget", "interests"
                ]),
            ))

            preview = client.post("/api/itineraries/preview", json=payload)
            data = preview.json() if preview.status_code == 200 else {}

            checks.append(("Public preview returns HTTP 200",
                           preview.status_code == 200))
            checks.append(("Preview works without Authorization",
                           "authorization" not in preview.request.headers))
            checks.append(("Preview preserves destination",
                           data.get("destination") == "Pondicherry"))
            checks.append(("Preview preserves days and budget",
                           data.get("days") == 3 and data.get("budget") == 10000))
            checks.append(("Preview preserves interests",
                           data.get("interests") == payload["interests"]))
            checks.append(("Preview passes complete request to generator",
                           any(call == payload for call in CALLS)))
            checks.append(("Preview returns three itinerary days",
                           isinstance(data.get("itinerary"), list)
                           and len(data["itinerary"]) == 3))
            checks.append(("Preview contains activities and guide sections",
                           bool(data.get("itinerary")) and all(
                               d.get("activities") and d.get("guide_sections")
                               for d in data["itinerary"]
                           )))
            checks.append(("Preview contains planner metadata",
                           data.get("planner_version") == "V11"
                           and data.get("data_source")
                           == "OpenStreetMap + personalized recommendation engine"))

            save = client.post("/api/itineraries", json=payload)
            saved = save.json() if save.status_code == 200 else {}

            checks.append(("Authenticated save returns HTTP 200",
                           save.status_code == 200))
            checks.append(("Saved itinerary belongs to user A",
                           saved.get("user_id") == user_a_id))
            checks.append(("Saved response preserves planner inputs",
                           saved.get("destination") == "Pondicherry"
                           and saved.get("days") == 3
                           and saved.get("budget") == 10000
                           and saved.get("interests") == payload["interests"]))
            checks.append(("Saved response exposes complete planner contract",
                           {
                               "id", "user_id", "destination", "days", "budget",
                               "interests", "location", "planner_version",
                               "data_source", "real_places_found",
                               "selected_real_places", "itinerary", "created_at",
                           }.issubset(saved.keys())))
            checks.append(("Saved response contains generated itinerary",
                           isinstance(saved.get("itinerary"), list)
                           and len(saved["itinerary"]) == 3))

            trip_id = saved.get("id")
            own_list = client.get("/api/itineraries")
            own_list_data = own_list.json() if own_list.status_code == 200 else {}
            checks.append(("Owner sees saved itinerary in list",
                           own_list.status_code == 200
                           and own_list_data.get("count") == 1
                           and any(i.get("id") == trip_id for i in
                                   own_list_data.get("itineraries", []))))

            own_get = client.get(f"/api/itineraries/{trip_id}")
            own_get_data = own_get.json() if own_get.status_code == 200 else {}
            checks.append(("Owner retrieves saved itinerary",
                           own_get.status_code == 200
                           and own_get_data.get("id") == trip_id
                           and own_get_data.get("destination") == "Pondicherry"))

            app.dependency_overrides[get_current_user] = (
                lambda: {"sub": "step17b@example.com"}
            )
            other_list = client.get("/api/itineraries")
            other_get = client.get(f"/api/itineraries/{trip_id}")
            checks.append(("User B cannot see user A itinerary in list",
                           other_list.status_code == 200
                           and other_list.json().get("count") == 0))
            checks.append(("User B cannot retrieve user A itinerary",
                           other_get.status_code == 404))

            bad_days = client.post(
                "/api/itineraries/preview",
                json={**payload, "days": 0},
            )
            checks.append(("Invalid days are rejected with HTTP 422",
                           bad_days.status_code == 422))

            bad_budget = client.post(
                "/api/itineraries/preview",
                json={**payload, "budget": 0},
            )
            checks.append(("Zero budget is rejected with HTTP 422",
                           bad_budget.status_code == 422))

    finally:
        planner.generate_personalized_itinerary = original_generator
        app.dependency_overrides.clear()

    print("=" * 72)
    print("STEP 17 - PHASE 4")
    print("AI TRAVEL PLANNER END-TO-END VALIDATION")
    print("=" * 72)

    passed = 0
    for name, ok in checks:
        print(("PASS: " if ok else "FAIL: ") + name)
        passed += int(bool(ok))

    print("=" * 72)
    print(f"RESULT: {passed}/{len(checks)} tests passed")
    print("=" * 72)

    if passed == len(checks):
        print("STEP 17 PHASE 4 END-TO-END VALIDATION PASSED")
        print("AI TRAVEL PLANNER IS READY TO FREEZE")
        return 0

    print("STEP 17 PHASE 4 END-TO-END VALIDATION FAILED")
    print("Fix only the failed E2E checks before freezing the AI Travel Planner.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
