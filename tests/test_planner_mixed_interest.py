"""Regression tests for trip-wide mixed-interest daily planning."""
from app.routers.planner import _create_daily_plan


def _place(name, interest, category, lat, lon):
    tags = {
        "beaches": {"natural": "beach"},
        "food": {"amenity": "restaurant"},
        "culture": {"tourism": "museum"},
        "adventure": {"tourism": "attraction"},
    }.get(interest, {})
    return {
        "name": name,
        "category": category,
        "type": "real_place",
        "matched_interest": interest,
        "distance_from_center_km": 1.0,
        "latitude": lat,
        "longitude": lon,
        "tags": tags,
        "source": "Test data",
    }


def test_every_day_mixes_all_requested_interests_when_places_are_available():
    interests = ["beaches", "food", "culture", "adventure"]
    places = []
    for day in range(3):
        places.extend([
            _place(f"Beach {day + 1}", "beaches", "Beach", 12.0 + day * 0.01, 79.8),
            _place(f"Restaurant {day + 1}", "food", "Restaurant", 12.0 + day * 0.01, 79.81),
            _place(f"Museum {day + 1}", "culture", "Museum", 12.0 + day * 0.01, 79.82),
            _place(f"Adventure {day + 1}", "adventure", "Adventure", 12.0 + day * 0.01, 79.83),
        ])

    itinerary = _create_daily_plan(
        destination="Puducherry",
        days=3,
        interests=interests,
        budget=5000,
        places=places,
        selected_places=places,
    )

    assert len(itinerary) == 3
    for day in itinerary:
        present = {activity["interest_match"] for activity in day["activities"]}
        assert set(interests).issubset(present)
        assert day["theme"] == "Mixed-interest travel day"
        assert len(day["activities"]) >= len(interests)


def test_days_do_not_become_food_only_when_food_is_one_of_several_interests():
    interests = ["beaches", "food", "culture"]
    places = [
        _place("Beach A", "beaches", "Beach", 12.0, 79.8),
        _place("Beach B", "beaches", "Beach", 12.01, 79.8),
        _place("Beach C", "beaches", "Beach", 12.02, 79.8),
        _place("Cafe A", "food", "Cafe", 12.0, 79.81),
        _place("Cafe B", "food", "Cafe", 12.01, 79.81),
        _place("Cafe C", "food", "Cafe", 12.02, 79.81),
        _place("Temple A", "culture", "Culture", 12.0, 79.82),
        _place("Temple B", "culture", "Culture", 12.01, 79.82),
        _place("Temple C", "culture", "Culture", 12.02, 79.82),
    ]
    itinerary = _create_daily_plan(
        destination="Puducherry", days=3, interests=interests,
        budget=5000, places=places, selected_places=places,
    )
    for day in itinerary:
        present = {activity["interest_match"] for activity in day["activities"]}
        assert present == set(interests)
