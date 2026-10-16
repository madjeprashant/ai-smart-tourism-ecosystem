"""Travel Explorer provider fallback validation.

The final provider policy is:
    Geoapify -> OpenStreetMap -> no data

All external HTTP calls are mocked in these tests.
"""
from __future__ import annotations


def _configure(monkeypatch, tmp_path, **env):
    monkeypatch.setenv("TRAVEL_PROVIDER_MODE", "auto")
    monkeypatch.setenv("TRAVEL_QUOTA_STORAGE_PATH", str(tmp_path / "quota.json"))
    for key, value in env.items():
        monkeypatch.setenv(key, str(value))


def test_geoapify_quota_is_configurable_and_starts_at_zero(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path, GEOAPIFY_DAILY_LIMIT=3)
    from app.services import quota_manager

    status = quota_manager.get_status("geoapify")
    assert status["used"] == 0
    assert status["limit"] == 3
    assert status["remaining"] == 3


def test_geoapify_quota_consumption_stops_at_daily_limit(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path, GEOAPIFY_DAILY_LIMIT=2)
    from app.services import quota_manager

    assert quota_manager.consume("geoapify") is True
    assert quota_manager.consume("geoapify") is True
    assert quota_manager.consume("geoapify") is False
    assert quota_manager.get_status("geoapify")["remaining"] == 0


def test_maps_uses_geoapify_when_available(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path, GEOAPIFY_DAILY_LIMIT=2)
    from app.services import maps_service

    monkeypatch.setattr(
        maps_service.geoapify_service,
        "geocode",
        lambda *args, **kwargs: [
            {"latitude": 12.9716, "longitude": 77.5946}
        ],
    )

    result = maps_service.get_map_data("Bengaluru")

    assert result["provider"] == "Geoapify"
    assert result["fallback"] is False
    assert result["live"] is True
    assert result["coordinates"]["latitude"] == 12.9716


def test_maps_falls_back_to_osm_when_geoapify_fails(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path, GEOAPIFY_DAILY_LIMIT=2)
    from app.services import maps_service

    monkeypatch.setattr(
        maps_service.geoapify_service,
        "geocode",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("Geoapify unavailable")
        ),
    )
    monkeypatch.setattr(
        maps_service.osm_service,
        "geocode",
        lambda destination: {
            "latitude": 12.9716,
            "longitude": 77.5946,
        },
    )

    result = maps_service.get_map_data("Bengaluru")

    assert result["provider"] == "OpenStreetMap"
    assert result["fallback"] is True
    assert result["status"] == "fallback"
    assert result["coordinates"]["latitude"] == 12.9716


def test_restaurants_fall_back_to_osm_when_geoapify_fails(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    from app.services import restaurants_service

    monkeypatch.setattr(
        restaurants_service.geoapify_service,
        "geocode",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("Geoapify unavailable")
        ),
    )
    monkeypatch.setattr(
        restaurants_service.osm_service,
        "nearby",
        lambda destination, category: [
            {
                "id": "osm-1",
                "name": "OSM Restaurant",
                "latitude": 12.97,
                "longitude": 77.59,
                "type": "restaurant",
                "source": "OpenStreetMap",
            }
        ],
    )

    result = restaurants_service.get_restaurants("Bengaluru")

    assert result["provider"] == "OpenStreetMap"
    assert result["fallback"] is True
    assert result["restaurants"][0]["source"] == "OpenStreetMap"


def test_hotels_fall_back_to_osm_when_geoapify_fails(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    from app.services import hotels_service

    monkeypatch.setattr(
        hotels_service.geoapify_service,
        "geocode",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("Geoapify unavailable")
        ),
    )
    monkeypatch.setattr(
        hotels_service.osm_service,
        "nearby",
        lambda destination, category: [
            {
                "id": "osm-h1",
                "name": "OSM Hotel",
                "latitude": 12.97,
                "longitude": 77.59,
                "type": "hotel",
                "source": "OpenStreetMap",
            }
        ],
    )

    result = hotels_service.get_hotels("Bengaluru")

    assert result["provider"] == "OpenStreetMap"
    assert result["fallback"] is True
    assert result["hotels"][0]["source"] == "OpenStreetMap"


def test_maps_returns_no_data_when_geoapify_and_osm_fail(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    from app.services import maps_service

    monkeypatch.setattr(
        maps_service.geoapify_service,
        "geocode",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("Geoapify unavailable")
        ),
    )
    monkeypatch.setattr(
        maps_service.osm_service,
        "geocode",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("OSM unavailable")
        ),
    )

    result = maps_service.get_map_data("Unknown destination")

    assert result["provider"] == "OpenStreetMap"
    assert result["fallback"] is True
    assert result["status"] == "no_data"
    assert result["coordinates"] == {
        "latitude": None,
        "longitude": None,
    }


def test_restaurants_return_no_data_when_osm_is_empty(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    from app.services import restaurants_service

    monkeypatch.setattr(
        restaurants_service.geoapify_service,
        "geocode",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("Geoapify unavailable")
        ),
    )
    monkeypatch.setattr(
        restaurants_service.osm_service,
        "nearby",
        lambda destination, category: [],
    )

    result = restaurants_service.get_restaurants("Unknown destination")

    assert result["provider"] == "OpenStreetMap"
    assert result["status"] == "no_data"
    assert result["restaurants"] == []


def test_hotels_return_no_data_when_osm_is_empty(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    from app.services import hotels_service

    monkeypatch.setattr(
        hotels_service.geoapify_service,
        "geocode",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("Geoapify unavailable")
        ),
    )
    monkeypatch.setattr(
        hotels_service.osm_service,
        "nearby",
        lambda destination, category: [],
    )

    result = hotels_service.get_hotels("Unknown destination")

    assert result["provider"] == "OpenStreetMap"
    assert result["status"] == "no_data"
    assert result["hotels"] == []


def test_provider_mode_defaults_to_auto(monkeypatch):
    monkeypatch.delenv("TRAVEL_PROVIDER_MODE", raising=False)
    from app.services.provider_manager import mode

    assert mode() == "auto"


def test_geoapify_geocode_prefers_india_for_ambiguous_destination(monkeypatch):
    from app.services import geoapify_service

    calls = []

    def fake_get(url, *, params, timeout=10):
        calls.append(params.copy())
        return {
            "results": [{
                "name": "Kochi",
                "formatted": "Kochi, Kerala, India",
                "lat": 9.9312,
                "lon": 76.2673,
                "country": "India",
                "state": "Kerala",
                "city": "Kochi",
                "place_id": "india-kochi",
            }]
        }

    monkeypatch.setattr(geoapify_service, "_get", fake_get)
    result = geoapify_service.geocode("Kochi")

    assert calls[0]["filter"] == "countrycode:in"
    assert result[0]["country"] == "India"
    assert result[0]["latitude"] == 9.9312


def test_geoapify_geocode_can_fall_back_worldwide(monkeypatch):
    from app.services import geoapify_service

    calls = []

    def fake_get(url, *, params, timeout=10):
        calls.append(params.copy())
        if params.get("filter") == "countrycode:in":
            return {"results": []}
        return {
            "results": [{
                "name": "Paris",
                "formatted": "Paris, France",
                "lat": 48.8566,
                "lon": 2.3522,
                "country": "France",
                "city": "Paris",
            }]
        }

    monkeypatch.setattr(geoapify_service, "_get", fake_get)
    result = geoapify_service.geocode("Paris")

    assert calls[0]["filter"] == "countrycode:in"
    assert "filter" not in calls[1]
    assert result[0]["country"] == "France"


def test_osm_geocode_prefers_india_for_ambiguous_destination(monkeypatch):
    from app.services import osm_service

    calls = []

    def fake_get(url, *, params=None):
        calls.append(params.copy())
        return [{
            "lat": "9.9312",
            "lon": "76.2673",
            "display_name": "Kochi, Kerala, India",
        }]

    monkeypatch.setattr(osm_service, "_http_get_json", fake_get)
    result = osm_service.geocode("Kochi")

    assert calls[0]["countrycodes"] == "in"
    assert result["latitude"] == 9.9312
    assert result["longitude"] == 76.2673


def test_osm_tries_fallback_overpass_provider(monkeypatch):
    from app.services import osm_service

    calls = []

    def fake_post(url, *, data):
        calls.append(url)

        if url == "https://overpass-api.de/api/interpreter":
            raise RuntimeError("primary Overpass unavailable")

        if url == "https://maps.mail.ru/osm/tools/overpass/api/interpreter":
            return {
                "elements": [
                    {
                        "type": "node",
                        "id": 123,
                        "lat": 12.9716,
                        "lon": 77.5946,
                        "tags": {
                            "name": "Fallback Restaurant",
                            "amenity": "restaurant",
                        },
                    }
                ]
            }

        raise AssertionError(f"Unexpected Overpass URL: {url}")

    monkeypatch.setattr(
        osm_service,
        "geocode",
        lambda destination: {
            "latitude": 12.9716,
            "longitude": 77.5946,
            "display_name": "Bengaluru, India",
        },
    )
    monkeypatch.setattr(osm_service, "_http_post_json", fake_post)

    result = osm_service.nearby("Bengaluru", "restaurant")

    assert calls == [
        "https://overpass-api.de/api/interpreter",
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    ]
    assert len(result) == 1
    assert result[0]["name"] == "Fallback Restaurant"
    assert result[0]["source"] == "OpenStreetMap"


def test_geoapify_area_result_uses_place_boundary_for_restaurants(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path, GEOAPIFY_DAILY_LIMIT=2)
    from app.services import restaurants_service

    calls = []

    monkeypatch.setattr(
        restaurants_service.geoapify_service,
        "geocode",
        lambda *args, **kwargs: [{
            "latitude": 10.35,
            "longitude": 76.27,
            "formatted": "Kerala, India",
            "place_type": "state",
            "is_area": True,
            "place_id": "kerala-place-id",
        }],
    )

    def fake_places(*args, **kwargs):
        calls.append(kwargs.copy())
        return [{
            "id": "geo-restaurant-1",
            "name": "Kerala Restaurant",
            "latitude": 10.1,
            "longitude": 76.3,
            "type": "real_place",
            "source": "Geoapify",
        }]

    monkeypatch.setattr(restaurants_service.geoapify_service, "places", fake_places)

    result = restaurants_service.get_restaurants("Kerala")

    assert result["provider"] == "Geoapify"
    assert result["restaurants"]
    assert calls[0]["place_id"] == "kerala-place-id"

def test_geoapify_area_result_uses_place_boundary_for_hotels(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path, GEOAPIFY_DAILY_LIMIT=2)
    from app.services import hotels_service

    calls = []

    monkeypatch.setattr(
        hotels_service.geoapify_service,
        "geocode",
        lambda *args, **kwargs: [{
            "latitude": 10.35,
            "longitude": 76.27,
            "formatted": "Kerala, India",
            "place_type": "state",
            "is_area": True,
            "place_id": "kerala-place-id",
        }],
    )

    def fake_places(*args, **kwargs):
        calls.append(kwargs.copy())
        return [{
            "id": "geo-hotel-1",
            "name": "Kerala Hotel",
            "address": "Kerala, India",
            "latitude": 10.1,
            "longitude": 76.3,
            "type": "hotel",
            "source": "Geoapify",
        }]

    monkeypatch.setattr(hotels_service.geoapify_service, "places", fake_places)

    result = hotels_service.get_hotels("Kerala")

    assert result["provider"] == "Geoapify"
    assert result["hotels"]
    assert calls[0]["place_id"] == "kerala-place-id"

def test_osm_region_search_expands_beyond_city_radius(monkeypatch):
    from app.services import osm_service

    monkeypatch.setattr(
        osm_service,
        "geocode",
        lambda destination: {
            "latitude": 10.35,
            "longitude": 76.27,
            "display_name": "Kerala, India",
            "place_type": "state",
            "is_area": True,
        },
    )

    captured = {}

    def fake_post(url, *, data):
        captured["query"] = data
        return {"elements": []}

    monkeypatch.setattr(osm_service, "_http_post_json", fake_post)

    result = osm_service.nearby("Kerala", "restaurant")

    assert result == []
    assert "around:50000,10.35,76.27" in captured["query"]

def test_maps_exposes_area_context_for_state_destination(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path, GEOAPIFY_DAILY_LIMIT=2)
    from app.services import maps_service

    monkeypatch.setattr(
        maps_service.geoapify_service,
        "geocode",
        lambda *args, **kwargs: [{
            "latitude": 10.35,
            "longitude": 76.27,
            "formatted": "Kerala, India",
            "place_type": "state",
            "is_area": True,
            "bounds": {
                "south": 8.2,
                "west": 74.8,
                "north": 12.8,
                "east": 77.4,
            },
        }],
    )

    result = maps_service.get_map_data("Kerala")

    assert result["destination_context"]["is_area"] is True
    assert result["destination_context"]["place_type"] == "state"
    assert result["destination_context"]["bounds"]["south"] == 8.2


def test_geoapify_places_can_search_inside_place_boundary(monkeypatch):
    from app.services import geoapify_service

    captured = {}

    def fake_get(url, *, params, timeout=10):
        captured["params"] = params.copy()
        return {"features": []}

    monkeypatch.setattr(geoapify_service, "_get", fake_get)

    result = geoapify_service.places(
        10.35,
        76.27,
        categories="catering.restaurant",
        place_id="kerala-place-id",
    )

    assert result == []
    assert captured["params"]["filter"] == "place:kerala-place-id"


def test_geoapify_restaurant_results_exclude_explicit_accommodation_category():
    from app.services import geoapify_service

    results = geoapify_service.filter_by_category(
        [
            {
                "id": "restaurant-1",
                "name": "Cafe One",
                "categories": ["catering.restaurant"],
            },
            {
                "id": "hotel-restaurant-1",
                "name": "Hotel Restaurant",
                "categories": [
                    "catering.restaurant",
                    "accommodation.hotel",
                ],
            },
        ],
        category="restaurant",
    )

    assert [item["id"] for item in results] == ["restaurant-1"]


def test_geoapify_hotel_results_exclude_explicit_catering_category():
    from app.services import geoapify_service

    results = geoapify_service.filter_by_category(
        [
            {
                "id": "hotel-1",
                "name": "Hotel One",
                "categories": ["accommodation.hotel"],
            },
            {
                "id": "restaurant-1",
                "name": "Restaurant One",
                "categories": ["accommodation.hotel", "catering.restaurant"],
            },
        ],
        category="hotel",
    )

    assert [item["id"] for item in results] == ["hotel-1"]


def test_osm_restaurant_results_exclude_accommodation_tag(monkeypatch):
    from app.services import osm_service

    monkeypatch.setattr(
        osm_service,
        "geocode",
        lambda destination: {
            "latitude": 10.35,
            "longitude": 76.27,
            "display_name": "Kerala, India",
        },
    )
    monkeypatch.setattr(
        osm_service,
        "_http_post_json",
        lambda url, data: {
            "elements": [
                {
                    "type": "node",
                    "id": 1,
                    "lat": 10.35,
                    "lon": 76.27,
                    "tags": {"name": "Restaurant", "amenity": "restaurant"},
                },
                {
                    "type": "node",
                    "id": 2,
                    "lat": 10.36,
                    "lon": 76.28,
                    "tags": {
                        "name": "Hotel Restaurant",
                        "amenity": "restaurant",
                        "tourism": "hotel",
                    },
                },
            ]
        },
    )

    result = osm_service.nearby("Kerala", "restaurant")

    assert [item["name"] for item in result] == ["Restaurant"]
