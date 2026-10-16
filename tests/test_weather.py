"""
STEP 14 - PHASE 4
WEATHER MODULE END-TO-END VALIDATION

Validates the complete existing Weather flow through the FastAPI application:
    HTTP request -> /api/weather -> Nominatim geocoding -> Open-Meteo data
    -> normalized weather response -> frontend compatibility.

External HTTP calls are mocked so the test is deterministic.

Run from the project root:
    python -m tests.test_weather_step14_phase4
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.routers import weather as weather_module


GEO_BENGALURU = {
    "name": "Bengaluru",
    "display_name": "Bengaluru, Karnataka, India",
    "lat": "12.9716",
    "lon": "77.5946",
    "address": {"country": "India"},
}

GEO_PARIS = {
    "name": "Paris",
    "display_name": "Paris, Ile-de-France, France",
    "lat": "48.8566",
    "lon": "2.3522",
    "address": {"country": "France"},
}

WEATHER_DATA = {
    "timezone": "Asia/Kolkata",
    "current": {
        "time": "2026-09-07T12:00",
        "temperature_2m": 27.4,
        "relative_humidity_2m": 68,
        "apparent_temperature": 28.1,
        "is_day": 1,
        "precipitation": 0.0,
        "rain": 0.0,
        "weather_code": 1,
        "wind_speed_10m": 9.5,
        "wind_direction_10m": 180,
    },
    "daily": {
        "time": ["2026-09-07", "2026-09-08", "2026-09-09"],
        "weather_code": [1, 2, 3],
        "temperature_2m_max": [28.0, 29.0, 27.0],
        "temperature_2m_min": [20.0, 21.0, 20.0],
        "precipitation_probability_max": [20, 35, 45],
        "sunrise": [
            "2026-09-07T06:10",
            "2026-09-08T06:10",
            "2026-09-09T06:09",
        ],
        "sunset": [
            "2026-09-07T18:25",
            "2026-09-08T18:25",
            "2026-09-09T18:24",
        ],
    },
}


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    static = root / "app" / "static"

    index_path = static / "index.html"
    js_path = static / "app.js"

    index = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
    app_js = js_path.read_text(encoding="utf-8") if js_path.exists() else ""

    checks = []
    original_http_get_json = weather_module._http_get_json
    client = TestClient(app)

    # ------------------------------------------------------------------
    # 1. Successful complete API flow
    # ------------------------------------------------------------------
    calls = []

    def fake_success_http(url: str, timeout: int = 10):
        calls.append((url, timeout))

        if weather_module.NOMINATIM_URL in url:
            if "Paris" in url:
                return [GEO_PARIS]
            return [GEO_BENGALURU]

        if weather_module.OPEN_METEO_URL in url:
            return WEATHER_DATA

        raise AssertionError(f"Unexpected external URL: {url}")

    try:
        weather_module._http_get_json = fake_success_http

        response = client.get("/api/weather?destination=Bengaluru")

        checks.append((
            "End-to-end weather request returns HTTP 200",
            response.status_code == 200,
        ))

        body = response.json() if response.status_code == 200 else {}

        checks.append((
            "End-to-end response is a JSON object",
            isinstance(body, dict),
        ))

        checks.append((
            "End-to-end response contains the requested destination",
            body.get("destination") == "Bengaluru",
        ))

        checks.append((
            "End-to-end response contains resolved location",
            body.get("resolved_location") == "Bengaluru, Karnataka, India",
        ))

        checks.append((
            "End-to-end response contains coordinates",
            body.get("coordinates") == {
                "latitude": 12.9716,
                "longitude": 77.5946,
            },
        ))

        checks.append((
            "End-to-end response contains current weather",
            isinstance(body.get("current"), dict)
            and body["current"].get("temperature_c") == 27.4
            and body["current"].get("condition"),
        ))

        checks.append((
            "End-to-end response contains three forecast days",
            isinstance(body.get("forecast"), list)
            and len(body["forecast"]) == 3,
        ))

        checks.append((
            "End-to-end response contains the weather data source",
            body.get("data_source")
            == "Open-Meteo weather forecast + OpenStreetMap Nominatim geocoding",
        ))

        checks.append((
            "End-to-end response is marked live",
            body.get("live") is True,
        ))

        checks.append((
            "End-to-end flow calls Nominatim and Open-Meteo",
            len(calls) == 2
            and weather_module.NOMINATIM_URL in calls[0][0]
            and weather_module.OPEN_METEO_URL in calls[1][0],
        ))

        # ------------------------------------------------------------------
        # 2. Destination changes propagate through the complete flow
        # ------------------------------------------------------------------
        calls.clear()

        paris_response = client.get("/api/weather?destination=Paris")
        paris_body = paris_response.json() if paris_response.status_code == 200 else {}

        checks.append((
            "End-to-end flow accepts another destination",
            paris_response.status_code == 200
            and paris_body.get("destination") == "Paris",
        ))

        checks.append((
            "End-to-end geocoding changes with the destination",
            paris_body.get("resolved_location") == "Paris, Ile-de-France, France"
            and paris_body.get("country") == "France",
        ))

        checks.append((
            "End-to-end coordinates match the resolved destination",
            paris_body.get("coordinates") == {
                "latitude": 48.8566,
                "longitude": 2.3522,
            },
        ))

        # ------------------------------------------------------------------
        # 3. Unknown destination flow
        # ------------------------------------------------------------------
        def fake_not_found_http(url: str, timeout: int = 10):
            if weather_module.NOMINATIM_URL in url:
                return []
            raise AssertionError("Open-Meteo must not run after failed geocoding")

        weather_module._http_get_json = fake_not_found_http

        not_found_response = client.get(
            "/api/weather?destination=UnknownPlace_987654321"
        )

        checks.append((
            "End-to-end unknown destination returns HTTP 404",
            not_found_response.status_code == 404,
        ))

        not_found_body = not_found_response.json()

        checks.append((
            "End-to-end unknown destination returns useful detail",
            isinstance(not_found_body.get("detail"), str)
            and "Could not find a location" in not_found_body["detail"],
        ))

        # ------------------------------------------------------------------
        # 4. External service failure flow
        # ------------------------------------------------------------------
        def fake_nominatim_failure(url: str, timeout: int = 10):
            if weather_module.NOMINATIM_URL in url:
                raise RuntimeError("simulated Nominatim failure")
            raise AssertionError("Open-Meteo must not run")

        weather_module._http_get_json = fake_nominatim_failure

        nominatim_failure = client.get(
            "/api/weather?destination=Bengaluru"
        )

        checks.append((
            "End-to-end Nominatim failure returns HTTP 503",
            nominatim_failure.status_code == 503,
        ))

        def fake_open_meteo_failure(url: str, timeout: int = 10):
            if weather_module.NOMINATIM_URL in url:
                return [GEO_BENGALURU]
            if weather_module.OPEN_METEO_URL in url:
                raise RuntimeError("simulated Open-Meteo failure")
            raise AssertionError(f"Unexpected URL: {url}")

        weather_module._http_get_json = fake_open_meteo_failure

        open_meteo_failure = client.get(
            "/api/weather?destination=Bengaluru"
        )

        checks.append((
            "End-to-end Open-Meteo failure returns HTTP 503",
            open_meteo_failure.status_code == 503,
        ))

        # ------------------------------------------------------------------
        # 5. Request validation flow
        # ------------------------------------------------------------------
        short_response = client.get("/api/weather?destination=A")

        checks.append((
            "End-to-end short destination is rejected with HTTP 422",
            short_response.status_code == 422,
        ))

        long_response = client.get(
            "/api/weather?destination=" + ("A" * 121)
        )

        checks.append((
            "End-to-end oversized destination is rejected with HTTP 422",
            long_response.status_code == 422,
        ))

        # ------------------------------------------------------------------
        # 6. Frontend/API integration compatibility
        # ------------------------------------------------------------------
        checks.append((
            "Frontend files remain available for the complete application flow",
            index_path.exists() and js_path.exists(),
        ))

        checks.append((
            "Frontend preserves the existing planner destination control",
            'id="destination"' in index,
        ))

        checks.append((
            "Frontend preserves the existing planner API flow",
            "/api/itineraries/preview" in app_js,
        ))

        checks.append((
            "Frontend preserves the shared API helper",
            "const api = async" in app_js and "fetch(url" in app_js,
        ))

        checks.append((
            "Weather remains an API capability without an invented frontend call",
            "/api/weather" not in app_js,
        ))

    finally:
        weather_module._http_get_json = original_http_get_json

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------
    print("=" * 72)
    print("PHASE 4 - STEP 14")
    print("WEATHER MODULE END-TO-END VALIDATION")
    print("=" * 72)

    passed = 0

    for name, result in checks:
        if result:
            print(f"PASS: {name}")
            passed += 1
        else:
            print(f"FAIL: {name}")

    print("=" * 72)
    print(f"RESULT: {passed}/{len(checks)} tests passed")
    print("=" * 72)

    if passed == len(checks):
        print("STEP 14 PHASE 4 END-TO-END VALIDATION PASSED")
    else:
        print("STEP 14 PHASE 4 END-TO-END VALIDATION FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
