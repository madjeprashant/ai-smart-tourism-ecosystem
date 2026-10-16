"""Regression tests for daily theme balancing in the Trip Planner."""

from app.routers.planner import _build_day_theme_plan


def _place(name, *, category, tags):
    return {
        "name": name,
        "category": category,
        "type": "real_place",
        "tags": tags,
    }


def test_unavailable_theme_does_not_create_empty_day():
    """A 3-day request should use an available requested theme instead of an empty day."""
    interests = ["beaches", "food", "adventure", "culture"]
    places = [
        _place("Kovalam Beach", category="Beach", tags={"natural": "beach"}),
        _place("Cherai Beach", category="Beach", tags={"natural": "beach"}),
        _place("Local Restaurant", category="Restaurant", tags={"amenity": "restaurant"}),
        _place("Local Cafe", category="Cafe", tags={"amenity": "cafe"}),
        _place("Boat House", category="Adventure", tags={"tourism": "attraction"}),
    ]

    plan = _build_day_theme_plan(interests, 3, places)

    assert len(plan) == 3
    assert [day["primary"] for day in plan] == ["beaches", "food", "adventure"]


def test_unavailable_theme_can_remain_no_data_only_when_not_enough_themes_exist():
    """If fewer themes have real places than requested days, preserve explicit no-data behavior."""
    interests = ["culture", "food"]
    places = [
        _place("Local Restaurant", category="Restaurant", tags={"amenity": "restaurant"}),
    ]

    plan = _build_day_theme_plan(interests, 3, places)

    assert len(plan) == 3
    assert plan[0]["primary"] == "food"
    assert plan[1]["primary"] == "culture"
