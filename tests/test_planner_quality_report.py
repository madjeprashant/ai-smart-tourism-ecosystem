"""Tests for transparent planner coverage and budget reporting."""

from app.routers.planner import _build_planner_quality_report


def test_quality_report_flags_empty_days_and_missing_day_coverage():
    itinerary = [
        {"day": 1, "activities": [{"estimated_cost_inr": 300}]},
        {"day": 2, "activities": []},
    ]

    report = _build_planner_quality_report(itinerary, requested_days=3, budget=2000)

    assert report["requested_days"] == 3
    assert report["days_returned"] == 2
    assert report["days_with_activities"] == 1
    assert report["days_without_activities"] == [2]
    assert report["all_requested_days_returned"] is False
    assert any("does not contain every requested day" in item for item in report["warnings"])
    assert any("day(s): 2" in item for item in report["warnings"])


def test_quality_report_does_not_claim_complete_trip_budget_is_verified():
    itinerary = [
        {"day": 1, "activities": [{"estimated_cost_inr": 1200}]},
        {"day": 2, "activities": [{"estimated_cost_inr": 900}]},
    ]

    report = _build_planner_quality_report(itinerary, requested_days=2, budget=1500)

    assert report["estimated_activity_cost_inr"] == 2100
    assert report["budget_scope"] == "activity_estimates_only"
    assert report["complete_trip_budget_verified"] is False
    assert any("activity costs alone exceed" in item for item in report["warnings"])
    assert "not a confirmed total-trip cost" in report["budget_note"]


def test_quality_report_is_clear_when_days_have_activities_and_estimate_is_within_budget():
    itinerary = [
        {"day": 1, "activities": [{"estimated_cost_inr": 300}]},
        {"day": 2, "activities": [{"estimated_cost_inr": 400}]},
    ]

    report = _build_planner_quality_report(itinerary, requested_days=2, budget=2000)

    assert report["all_requested_days_returned"] is True
    assert report["days_without_activities"] == []
    assert report["estimated_activity_cost_inr"] == 700
    assert report["warnings"] == []
    assert report["complete_trip_budget_verified"] is False
