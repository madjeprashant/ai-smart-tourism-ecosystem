"""Live weather integration for the VoyageAI tourism platform.

Step 7 replaces the old placeholder weather endpoint with a real, API-key-free
integration using OpenStreetMap Nominatim for geocoding and Open-Meteo for
current conditions + a short forecast.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

from fastapi import APIRouter, HTTPException, Query


router = APIRouter(
    prefix="/api",
    tags=["Weather"],
)


NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
USER_AGENT = "AI-Smart-Tourism-Ecosystem/1.0 (student project)"


WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def _http_get_json(url: str, timeout: int = 10) -> Any:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _geocode_destination(destination: str) -> dict | None:
    """Resolve a worldwide destination into coordinates using Nominatim."""
    params = urllib.parse.urlencode(
        {
            "q": destination.strip(),
            "format": "jsonv2",
            "limit": 1,
            "addressdetails": 1,
        }
    )

    results = _http_get_json(f"{NOMINATIM_URL}?{params}", timeout=6)
    if not isinstance(results, list) or not results:
        return None

    result = results[0]
    try:
        latitude = float(result["lat"])
        longitude = float(result["lon"])
    except (KeyError, TypeError, ValueError):
        return None

    address = result.get("address") or {}
    display_name = str(result.get("display_name") or destination).strip()

    return {
        "name": str(result.get("name") or destination).strip(),
        "display_name": display_name,
        "latitude": latitude,
        "longitude": longitude,
        "country": str(address.get("country") or "").strip(),
    }


def _weather_label(code: int | None) -> str:
    if code is None:
        return "Unknown conditions"
    return WEATHER_CODES.get(int(code), "Unknown conditions")


def _build_weather_payload(destination: str, geo: dict, data: dict) -> dict:
    current = data.get("current") or {}
    daily = data.get("daily") or {}

    current_code = current.get("weather_code")
    current_weather = {
        "temperature_c": current.get("temperature_2m"),
        "feels_like_c": current.get("apparent_temperature"),
        "humidity_percent": current.get("relative_humidity_2m"),
        "wind_speed_kmh": current.get("wind_speed_10m"),
        "wind_direction_degrees": current.get("wind_direction_10m"),
        "precipitation_mm": current.get("precipitation"),
        "rain_mm": current.get("rain"),
        "is_day": current.get("is_day"),
        "weather_code": current_code,
        "condition": _weather_label(current_code),
        "observed_at": current.get("time"),
    }

    dates = daily.get("time") or []
    max_temps = daily.get("temperature_2m_max") or []
    min_temps = daily.get("temperature_2m_min") or []
    codes = daily.get("weather_code") or []
    precipitation = daily.get("precipitation_probability_max") or []
    sunrise = daily.get("sunrise") or []
    sunset = daily.get("sunset") or []

    forecast = []
    for index, day in enumerate(dates):
        code = codes[index] if index < len(codes) else None
        forecast.append(
            {
                "date": day,
                "temperature_max_c": max_temps[index] if index < len(max_temps) else None,
                "temperature_min_c": min_temps[index] if index < len(min_temps) else None,
                "precipitation_probability_percent": precipitation[index] if index < len(precipitation) else None,
                "weather_code": code,
                "condition": _weather_label(code),
                "sunrise": sunrise[index] if index < len(sunrise) else None,
                "sunset": sunset[index] if index < len(sunset) else None,
            }
        )

    return {
        "destination": destination.strip(),
        "resolved_location": geo["display_name"],
        "country": geo["country"],
        "coordinates": {
            "latitude": geo["latitude"],
            "longitude": geo["longitude"],
        },
        "timezone": data.get("timezone"),
        "current": current_weather,
        "forecast": forecast,
        "data_source": "Open-Meteo weather forecast + OpenStreetMap Nominatim geocoding",
        "live": True,
    }


@router.get("/weather")
def weather(
    destination: str = Query(
        default="Bengaluru",
        min_length=2,
        max_length=120,
        description="City or travel destination",
    )
):
    """Return live current weather and a three-day forecast."""
    destination = destination.strip()

    try:
        geo = _geocode_destination(destination)
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail="Weather location lookup is temporarily unavailable. Please try again.",
        ) from error

    if not geo:
        raise HTTPException(
            status_code=404,
            detail=f"Could not find a location for '{destination}'. Try a city or destination name.",
        )

    params = urllib.parse.urlencode(
        {
            "latitude": geo["latitude"],
            "longitude": geo["longitude"],
            "current": ",".join(
                [
                    "temperature_2m",
                    "relative_humidity_2m",
                    "apparent_temperature",
                    "is_day",
                    "precipitation",
                    "rain",
                    "weather_code",
                    "wind_speed_10m",
                    "wind_direction_10m",
                ]
            ),
            "daily": ",".join(
                [
                    "weather_code",
                    "temperature_2m_max",
                    "temperature_2m_min",
                    "precipitation_probability_max",
                    "sunrise",
                    "sunset",
                ]
            ),
            "forecast_days": 3,
            "timezone": "auto",
        }
    )

    try:
        data = _http_get_json(f"{OPEN_METEO_URL}?{params}", timeout=10)
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail="The live weather service is temporarily unavailable. Please try again.",
        ) from error

    if not isinstance(data, dict) or "current" not in data:
        raise HTTPException(
            status_code=503,
            detail="The weather service returned an unexpected response.",
        )

    return _build_weather_payload(destination, geo, data)
