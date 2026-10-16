"""Trip Planner provider integration.

Final provider policy:
    Geoapify -> OpenStreetMap -> no data
"""
from app.routers import planner


def test_planner_uses_geoapify_before_osm(monkeypatch):
    geoapify_places = [{
        "name": "Geoapify Restaurant",
        "category": "Restaurant",
        "type": "real_place",
        "latitude": 12.95,
        "longitude": 77.58,
        "tags": {"amenity": "restaurant"},
        "source": "Geoapify",
        "provider": "Geoapify",
    }]

    monkeypatch.setattr(
        planner,
        "_get_geoapify_places",
        lambda *args, **kwargs: geoapify_places,
    )
    monkeypatch.setattr(
        planner,
        "_http_post_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("OSM should not be called when Geoapify returns places")
        ),
    )

    result = planner._get_places(
        latitude=12.9716,
        longitude=77.5946,
        interests=["food"],
        destination="Bengaluru",
    )

    assert result
    assert result[0]["source"] == "Geoapify"


def test_planner_falls_back_to_osm_when_geoapify_returns_nothing(monkeypatch):
    monkeypatch.setattr(planner, "_get_geoapify_places", lambda *args, **kwargs: [])

    fake_osm = {
        "elements": [{
            "tags": {"name": "OSM Restaurant", "amenity": "restaurant"},
            "lat": 12.97,
            "lon": 77.59,
        }]
    }
    monkeypatch.setattr(planner, "_http_post_json", lambda *args, **kwargs: fake_osm)

    result = planner._get_places(
        latitude=12.9716,
        longitude=77.5946,
        interests=["food"],
        destination="Bengaluru",
    )

    assert result
    assert result[0]["name"] == "OSM Restaurant"
    assert result[0]["source"] == "OpenStreetMap"


def test_generic_place_labels_are_disabled_by_default(monkeypatch):
    monkeypatch.delenv("PLANNER_ALLOW_GENERIC_FALLBACK", raising=False)

    result = planner._create_daily_plan(
        destination="Bengaluru",
        days=1,
        interests=["food"],
        budget=5000,
        places=[],
        destination_lat=12.9716,
        destination_lon=77.5946,
        selected_places=[],
        geographic_groups=[[]],
    )

    assert result[0]["activities"] == []
    assert result[0]["availability_note"]
