"""Tests for the itinerary planner's practical daily schedule."""
from app.routers.planner import _build_day_schedule


def test_schedule_has_three_meals_and_one_main_rest_break_in_chronological_order():
    events = _build_day_schedule([
        {"name": "Heritage museum", "category": "Museum", "interest_match": "culture",
         "estimated_cost_inr": 200},
        {"name": "Old town walk", "category": "Attraction", "interest_match": "sightseeing",
         "estimated_cost_inr": 100},
        {"name": "City park", "category": "Nature", "interest_match": "nature",
         "estimated_cost_inr": 100},
        {"name": "Waterfront", "category": "Beach", "interest_match": "beaches",
         "estimated_cost_inr": 100},
    ], 1, "Example City", "budget")

    titles = [event["title"] for event in events]
    assert titles.count("Breakfast") == 1
    assert titles.count("Lunch") == 1
    assert titles.count("Dinner") == 1
    assert sum(event["kind"] == "rest" for event in events) == 1
    assert len([event for event in events if event["kind"] == "visit"]) == 4
    lunch_index = titles.index("Lunch")
    assert titles.index("Breakfast") < lunch_index
    assert events[lunch_index]["start"] == "12:45 PM"
    assert titles.index("Short rest and refresh") > lunch_index
    assert events[-1]["title"] == "Dinner"


def test_schedule_keeps_meals_and_break_when_no_places_are_found():
    events = _build_day_schedule([], 1, "Example City", "budget")
    assert [event["title"] for event in events if event["kind"] == "meal"] == [
        "Breakfast", "Lunch", "Dinner"
    ]
    assert sum(event["kind"] == "rest" for event in events) == 1
