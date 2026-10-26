"""Regression coverage for destination-specific, fast itinerary generation."""

from pathlib import Path

from app.routers import planner


def test_mysuru_uses_named_places_without_waiting_for_live_provider(monkeypatch):
    def unexpected_live_lookup(**kwargs):
        raise AssertionError("covered Mysuru interests should use the curated guide")

    monkeypatch.setattr(planner, "_get_places", unexpected_live_lookup)
    result = planner.generate_personalized_itinerary(
        destination="mysuru",
        days=2,
        interests=["famous places", "temples", "history"],
        budget=5000,
    )

    assert result["days"] == 2
    assert len(result["itinerary"]) == 2
    names = {
        activity["name"]
        for day in result["itinerary"]
        for activity in day["activities"]
    }
    assert names.intersection({
        "Mysuru Palace", "Chamundeshwari Temple", "Jaganmohan Palace Art Gallery",
        "St. Philomena's Cathedral", "Chamundi Hill",
    })
    assert all(day["activities"] for day in result["itinerary"])
    assert result["data_source"].startswith("Curated destination guide")


def test_kochi_uses_named_places_for_sightseeing_and_history(monkeypatch):
    def unexpected_live_lookup(**kwargs):
        raise AssertionError("covered Kochi interests should use the curated guide")

    monkeypatch.setattr(planner, "_get_places", unexpected_live_lookup)
    result = planner.generate_personalized_itinerary(
        destination="Kochi",
        days=2,
        interests=["sightseeing", "history", "culture"],
        budget=6000,
    )

    names = {
        activity["name"]
        for day in result["itinerary"]
        for activity in day["activities"]
    }
    assert names.intersection({
        "Fort Kochi", "Mattancherry Palace", "Paradesi Synagogue",
        "Kerala Folklore Museum", "Chinese Fishing Nets",
    })
    assert all(day["activities"] for day in result["itinerary"])


def test_destination_without_places_is_not_fabricated_by_frontend():
    project_root = Path(__file__).resolve().parents[1]
    js = (project_root / "app" / "static" / "app.js").read_text(encoding="utf-8")
    assert "!Array.isArray(day.activities) || day.activities.length === 0" in js
    assert "No named attractions found for this day" in js


def test_interest_normalisation_handles_sentence_punctuation():
    assert planner._normalise_interest("famous places") == "sightseeing"
    assert planner._normalise_interest("history.") == "history"
    assert planner._normalise_interest("temples!") == "temples"
