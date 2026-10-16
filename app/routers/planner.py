import json
import os
import re
import unicodedata
import urllib.parse
import urllib.request
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..schemas import PlannerRequest
from ..security import get_current_user
from ..database import get_db
from ..models import Trip
from ..crud import get_user_by_email
from ..services import geoapify_service, osm_service, provider_manager, quota_manager


router = APIRouter(
    prefix="/api",
    tags=["Planner"]
)


# Generic fallback activities. These are used only when online
# location data is unavailable or too limited.
ACTIVITY_POOLS = {
    "beaches": [
        "Beach visit",
        "Sunset by the beach",
        "Water activity",
        "Beach photography",
    ],
    "food": [
        "Local food tour",
        "Popular local restaurant",
        "Street food experience",
        "Traditional cuisine tasting",
    ],
    "sightseeing": [
        "City sightseeing",
        "Popular tourist attraction",
        "Local sightseeing",
        "City landmark visit",
    ],
    "history": [
        "Historical monument visit",
        "Heritage site visit",
        "Museum visit",
        "Heritage walk",
    ],
    "adventure": [
        "Adventure activity",
        "Outdoor experience",
        "Nature trail",
        "Local adventure activity",
    ],
    "nature": [
        "Nature sightseeing",
        "Scenic viewpoint",
        "Park or garden visit",
        "Nature walk",
    ],
    "shopping": [
        "Local market visit",
        "Shopping street",
        "Souvenir shopping",
        "Local handicraft market",
    ],
    "culture": [
        "Cultural experience",
        "Local art and culture visit",
        "Traditional performance",
        "Cultural landmark",
    ],
    "nightlife": [
        "Evening entertainment",
        "Popular evening area",
        "Night market",
        "Relaxed evening experience",
    ],
}

# Reliable named recommendations for popular, broad destinations. These are
# used alongside live OSM data, preventing the planner from showing vague
# labels such as “Beach visit” when a state-wide OSM search is incomplete.
CURATED_DESTINATION_PLACES = {
    "kerala": {
        "beaches": [
            ("Kovalam Beach", "Beach", {"natural": "beach"}),
            ("Varkala Cliff Beach", "Beach", {"natural": "beach"}),
            ("Cherai Beach", "Beach", {"natural": "beach"}),
        ],
        "food": [
            ("Kashi Art Café, Varkala", "Cafe", {"amenity": "cafe"}),
            ("Grand Pavilion, Kochi", "Restaurant", {"amenity": "restaurant"}),
            ("Paragon Restaurant, Kozhikode", "Restaurant", {"amenity": "restaurant"}),
        ],
        "adventure": [
            ("Alappuzha Backwater Cruise", "Adventure", {"tourism": "attraction"}),
            ("Periyar Wildlife Sanctuary", "Adventure", {"tourism": "attraction"}),
            ("Munnar Tea Garden Trail", "Adventure", {"tourism": "attraction"}),
        ],
    },
    "puducherry": {
        "beaches": [
            ("Promenade Beach", "Beach", {"natural": "beach"}),
            ("Paradise Beach", "Beach", {"natural": "beach"}),
            ("Auroville Beach", "Beach", {"natural": "beach"}),
        ],
        "food": [
            ("Surguru Spot Restaurant", "Restaurant", {"amenity": "restaurant"}),
            ("Coromandel Café", "Cafe", {"amenity": "cafe"}),
            ("Baker Street, White Town", "Cafe", {"amenity": "cafe"}),
        ],
        "adventure": [
            ("Chunnambar Boat House", "Adventure", {"tourism": "attraction"}),
            ("Pondicherry Scuba Diving Centre", "Adventure", {"tourism": "attraction"}),
            ("Auroville Cycling Trail", "Adventure", {"tourism": "attraction"}),
        ],
        "culture": [
            ("Sri Aurobindo Ashram", "Culture", {"tourism": "attraction"}),
            ("French War Memorial", "Monument", {"historic": "memorial"}),
            ("Immaculate Conception Cathedral", "Culture", {"amenity": "place_of_worship"}),
        ],
        "sightseeing": [
            ("Manakula Vinayagar Temple", "Attraction", {"tourism": "attraction"}),
            ("Basilica of the Sacred Heart of Jesus", "Attraction", {"tourism": "attraction"}),
            ("Puducherry Museum", "Museum", {"tourism": "museum"}),
            ("Botanical Garden, Puducherry", "Garden", {"leisure": "garden"}),
            ("French War Memorial", "Monument", {"historic": "memorial"}),
        ],
    },
    "bengaluru": {
        "sightseeing": [
            ("Bengaluru Palace", "Attraction", {"tourism": "attraction"}),
            ("Lalbagh Botanical Garden", "Garden", {"leisure": "garden"}),
            ("Cubbon Park", "Park", {"leisure": "park"}),
            ("Visvesvaraya Industrial and Technological Museum", "Museum", {"tourism": "museum"}),
            ("Vidhana Soudha", "Attraction", {"tourism": "attraction"}),
            ("Bannerghatta Biological Park", "Attraction", {"tourism": "attraction"}),
        ],
        "temples": [
            ("Bull Temple (Dodda Basavana Gudi)", "Temple", {"amenity": "place_of_worship", "religion": "hindu"}),
            ("ISKCON Temple Bengaluru", "Temple", {"amenity": "place_of_worship", "religion": "hindu"}),
            ("Gavi Gangadhareshwara Temple", "Temple", {"amenity": "place_of_worship", "religion": "hindu"}),
            ("Banashankari Amma Temple", "Temple", {"amenity": "place_of_worship", "religion": "hindu"}),
            ("Dodda Ganesha Temple", "Temple", {"amenity": "place_of_worship", "religion": "hindu"}),
        ],
    },
    "mangaluru": {
        "sightseeing": [
            ("Mangalore Clock Tower", "Monument", {"historic": "monument"}),
            ("St. Aloysius Chapel", "Attraction", {"tourism": "attraction", "historic": "building"}),
            ("Sultan Battery", "Historic place", {"historic": "fort"}),
            ("Pilikula Nisargadhama", "Nature", {"leisure": "nature_reserve"}),
        ],
        "beaches": [
            ("Panambur Beach", "Beach", {"natural": "beach"}),
            ("Tannirbhavi Beach", "Beach", {"natural": "beach"}),
        ],
        "culture": [
            ("Kudroli Gokarnath Temple", "Culture", {"amenity": "place_of_worship", "religion": "hindu"}),
            ("Kadri Manjunath Temple", "Culture", {"amenity": "place_of_worship", "religion": "hindu"}),
            ("Mangaladevi Temple", "Culture", {"amenity": "place_of_worship", "religion": "hindu"}),
        ],
        "temples": [
            ("Kudroli Gokarnath Temple", "Temple", {"amenity": "place_of_worship", "religion": "hindu"}),
            ("Kadri Manjunath Temple", "Temple", {"amenity": "place_of_worship", "religion": "hindu"}),
            ("Mangaladevi Temple", "Temple", {"amenity": "place_of_worship", "religion": "hindu"}),
        ],
    },
}

# Approximate coordinates for curated landmarks. They let daily grouping and
# transfer estimates distinguish far-apart city areas (for example, ISKCON and
# Bannerghatta in Bengaluru) instead of treating every curated place as colocated.
CURATED_PLACE_COORDINATES = {
    "Promenade Beach": (11.9340, 79.8350),
    "Paradise Beach": (11.8810, 79.8200),
    "Auroville Beach": (11.9940, 79.8440),
    "Chunnambar Boat House": (11.8770, 79.8050),
    "Pondicherry Scuba Diving Centre": (11.9340, 79.8350),
    "Auroville Cycling Trail": (12.0050, 79.8100),
    "Sri Aurobindo Ashram": (11.9347, 79.8345),
    "French War Memorial": (11.9355, 79.8355),
    "Immaculate Conception Cathedral": (11.9320, 79.8310),
    "Manakula Vinayagar Temple": (11.9360, 79.8340),
    "Basilica of the Sacred Heart of Jesus": (11.9260, 79.8310),
    "Puducherry Museum": (11.9320, 79.8330),
    "Botanical Garden, Puducherry": (11.9280, 79.8270),
    "Bengaluru Palace": (12.9988, 77.5921),
    "Lalbagh Botanical Garden": (12.9507, 77.5848),
    "Cubbon Park": (12.9763, 77.5929),
    "Visvesvaraya Industrial and Technological Museum": (12.9753, 77.5963),
    "Vidhana Soudha": (12.9797, 77.5907),
    "Bannerghatta Biological Park": (12.8007, 77.5770),
    "Bull Temple (Dodda Basavana Gudi)": (12.9431, 77.5687),
    "ISKCON Temple Bengaluru": (13.0109, 77.5511),
    "Gavi Gangadhareshwara Temple": (12.9435, 77.5666),
    "Banashankari Amma Temple": (12.9177, 77.5733),
    "Dodda Ganesha Temple": (12.9427, 77.5682),
    "Mangalore Clock Tower": (12.8708, 74.8425),
    "St. Aloysius Chapel": (12.8705, 74.8430),
    "Sultan Battery": (12.8774, 74.8146),
    "Pilikula Nisargadhama": (12.9810, 74.8910),
    "Panambur Beach": (12.9496, 74.7943),
    "Tannirbhavi Beach": (12.8730, 74.8230),
    "Kudroli Gokarnath Temple": (12.8808, 74.8335),
    "Kadri Manjunath Temple": (12.8915, 74.8631),
    "Mangaladevi Temple": (12.8610, 74.8445),
}


INTEREST_TAGS = {
    "beaches": [
        ('["natural"="beach"]', "Beach"),
        ('["leisure"="beach_resort"]', "Beach resort"),
    ],
    "food": [
        ('["amenity"="restaurant"]', "Restaurant"),
        ('["amenity"="cafe"]', "Cafe"),
        ('["amenity"="fast_food"]', "Food"),
    ],
    "sightseeing": [
        ('["tourism"="attraction"]', "Attraction"),
        ('["tourism"="viewpoint"]', "Viewpoint"),
        ('["tourism"="museum"]', "Museum"),
        ('["tourism"="gallery"]', "Gallery"),
        ('["historic"="monument"]', "Monument"),
        ('["historic"="memorial"]', "Memorial"),
        ('["amenity"="place_of_worship"]', "Place of worship"),
    ],
    "history": [
        ('["historic"]', "Historic place"),
        ('["tourism"="museum"]', "Museum"),
        ('["tourism"="monument"]', "Monument"),
    ],
    "adventure": [
        ('["leisure"="sports_centre"]', "Sports centre"),
        ('["sport"]', "Sport"),
        ('["tourism"="attraction"]', "Adventure attraction"),
    ],
    "nature": [
        ('["leisure"="park"]', "Park"),
        ('["leisure"="garden"]', "Garden"),
        ('["natural"="peak"]', "Scenic place"),
        ('["tourism"="viewpoint"]', "Viewpoint"),
    ],
    "shopping": [
        ('["shop"]', "Shop"),
        ('["amenity"="marketplace"]', "Market"),
    ],
    "culture": [
        ('["tourism"="museum"]', "Museum"),
        ('["amenity"="place_of_worship"]', "Cultural place"),
        ('["tourism"="gallery"]', "Gallery"),
        ('["historic"]', "Cultural landmark"),
    ],
    "nightlife": [
        ('["amenity"="bar"]', "Bar"),
        ('["amenity"="pub"]', "Pub"),
        ('["amenity"="nightclub"]', "Nightlife"),
    ],
}


def _normalise_interest(interest: str) -> str:
    """Normalise user interest names and common aliases."""
    value = interest.strip().lower()
    aliases = {
        "beach": "beaches", "sea": "beaches", "water": "beaches",
        "restaurants": "food", "restaurant": "food", "cuisine": "food",
        "cafe": "food", "cafes": "food", "coffee": "food",
        "heritage": "history", "historical": "history",
        "temple": "temples", "mandir": "temples", "mandirs": "temples",
        "attractions": "sightseeing", "tourist attractions": "sightseeing",
        "tourist places": "sightseeing", "famous places": "sightseeing",
        "famous attractions": "sightseeing", "places to visit": "sightseeing",
        "landmarks": "sightseeing", "arts": "culture",
        "boat activity": "adventure", "boating": "adventure",
        "water sports": "adventure", "watersports": "adventure",
    }
    return aliases.get(value, value)


def _destination_guide_key(destination: str) -> str:
    """Normalise common city aliases to the curated guide key."""
    key = destination.strip().lower()
    aliases = {
        "pondicherry": "puducherry", "pondy": "puducherry",
        "bangalore": "bengaluru", "bengaluru, india": "bengaluru",
        "mangalore": "mangaluru", "mangaluru, india": "mangaluru",
    }
    return aliases.get(key, key)


def _curated_places_for_destination(destination: str) -> list[dict]:
    """Return named local recommendations when this guide covers a place."""
    key = _destination_guide_key(destination)
    guide = CURATED_DESTINATION_PLACES.get(key, {})
    return [
        {"name": name, "category": category, "type": "real_place", "tags": tags,
         "latitude": CURATED_PLACE_COORDINATES.get(name, (None, None))[0],
         "longitude": CURATED_PLACE_COORDINATES.get(name, (None, None))[1],
         "source": "Curated travel guide"}
        for items in guide.values()
        for name, category, tags in items
    ]


def _default_destination_interests(destination: str) -> list[str]:
    """Infer a balanced highlights plan when the traveller leaves interests blank."""
    curated = _curated_places_for_destination(destination)
    candidates = list(dict.fromkeys(
        ["sightseeing", "culture", "nature", "beaches", "temples"]
        + list(CURATED_DESTINATION_PLACES.get(_destination_guide_key(destination), {}).keys())
    ))
    available = [
        interest for interest in candidates
        if any(_interest_matches_place(interest, place) > 0 for place in curated)
    ]
    if not available:
        return ["sightseeing", "culture", "nature"]
    # Temples and beaches are explicit destination highlights; keep them early
    # so broad sightseeing results cannot consume their daily slots.
    priority = {name: index for index, name in enumerate(
        ["temples", "beaches", "culture", "nature", "adventure", "history", "sightseeing"]
    )}
    return sorted(available, key=lambda item: priority.get(item, 99))


def _local_meal_description(destination: str, meal: str) -> str:
    """Suggest destination-relevant food within the existing three meal slots."""
    city = _destination_guide_key(destination)
    suggestions = {
        "mangaluru": {
            "breakfast": "Try a local breakfast such as neer dosa or goli baje.",
            "lunch": "Look for Mangalorean meals, kori rotti or a local seafood thali.",
            "dinner": "Try a well-rated local restaurant for Mangalorean coastal dishes.",
        },
        "bengaluru": {
            "breakfast": "Try Bengaluru-style idli, dosa or a local darshini breakfast.",
            "lunch": "Look for Karnataka meals or a local South Indian thali.",
            "dinner": "Try a well-rated local restaurant or a regional Karnataka dish.",
        },
        "puducherry": {
            "breakfast": "Try local Tamil breakfast or a bakery in the French Quarter.",
            "lunch": "Look for Tamil coastal dishes or a local seafood meal.",
            "dinner": "Try a well-rated local Tamil or French-influenced restaurant.",
        },
        "kerala": {
            "breakfast": "Try appam, puttu or another local Kerala breakfast.",
            "lunch": "Look for a Kerala meals or sadya served at a local restaurant.",
            "dinner": "Try a well-rated local restaurant for Kerala coastal cuisine.",
        },
    }
    return suggestions.get(city, {}).get(
        meal,
        f"Choose a well-reviewed local {meal} option and ask about the destination's specialties.",
    )


def _http_get_json(url: str, timeout: int = 12) -> Any:
    """Small dependency-free HTTP GET helper."""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "AI-Smart-Tourism-Ecosystem/1.0 (student project)"
        },
    )

    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _http_post_json(
    url: str,
    data: str,
    timeout: int = 35,
) -> Any:
    """POST JSON response helper for Overpass API queries."""
    request = urllib.request.Request(
        url,
        data=data.encode("utf-8"),
        method="POST",
        headers={
            "User-Agent": "AI-Smart-Tourism-Ecosystem/1.0 (student project)",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )

    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))



def _osm_secondary_places(destination: str, interest: str) -> list[dict]:
    """Use the existing Travel Explorer OSM service as a resilient second OSM path."""
    try:
        category = "restaurant" if interest == "food" else "poi"
        raw = osm_service.nearby(destination, category)
    except Exception:
        return []

    normalized = []
    for item in raw or []:
        name = str(item.get("name") or "").strip()
        lat = item.get("latitude")
        lon = item.get("longitude")
        if not name or lat is None or lon is None:
            continue
        tags = {}
        item_type = str(item.get("type") or "").lower()
        if item_type in {"restaurant", "cafe", "fast_food", "food_court"}:
            tags["amenity"] = item_type
        elif item_type in {"museum", "attraction", "gallery", "viewpoint"}:
            tags["tourism"] = item_type
        normalized.append({
            "id": item.get("id"),
            "name": name,
            "category": _detect_category(tags) if tags else _detect_category({"tourism": item_type}),
            "type": "real_place",
            "latitude": lat,
            "longitude": lon,
            "address": item.get("address", ""),
            "tags": tags,
            "source": "OpenStreetMap",
            "provider": "OpenStreetMap",
        })
    return normalized


def _geocode_destination(destination: str) -> dict | None:
    """Resolve the user's destination to the most likely settlement."""
    raw = destination.strip()
    if not raw:
        return None

    aliases = {
        "pondicherry": "Puducherry",
        "pondy": "Puducherry",
        "mysore": "Mysuru",
        "bangalore": "Bengaluru",
        "mangalore": "Mangaluru",
    }
    preferred_name = aliases.get(raw.lower(), raw)

    # One focused India query keeps the planner responsive. The previous
    # three sequential geocoder searches could consume 36 seconds before
    # itinerary generation even started.
    queries = [f"{preferred_name}, India"]

    candidates = []
    for query in queries:
        params = urllib.parse.urlencode({
            "q": query,
            "format": "jsonv2",
            "addressdetails": 1,
            "limit": 8,
            "countrycodes": "in",
        })
        try:
            results = _http_get_json(
                f"https://nominatim.openstreetmap.org/search?{params}",
                timeout=4,
            )
        except Exception:
            continue
        if not isinstance(results, list):
            continue

        for result in results:
            try:
                lat = float(result["lat"])
                lon = float(result["lon"])
            except (KeyError, TypeError, ValueError):
                continue

            address = result.get("address", {}) or {}
            name = str(result.get("name") or "").strip()
            display = str(result.get("display_name") or "").strip()
            result_type = str(result.get("type") or "").lower()
            result_class = str(result.get("class") or "").lower()
            importance = float(result.get("importance") or 0)
            target = preferred_name.lower()
            address_values = " ".join(str(v).lower() for v in address.values())

            score = 0.0
            if name.lower() == target: score += 150
            if name.lower() == raw.lower(): score += 120
            if target in display.lower(): score += 30
            if target in address_values: score += 30
            if result_type in {"city", "town", "municipality"}: score += 140
            elif result_type in {"village", "suburb"}: score += 60
            elif result_class == "place": score += 40
            if address.get("country_code", "").lower() == "in": score += 20
            score += importance * 20

            candidates.append({
                "score": score,
                "display_name": display or raw,
                "latitude": lat,
                "longitude": lon,
                "name": name,
                "type": result_type,
            })

    if not candidates:
        return None
    best = max(candidates, key=lambda item: item["score"])
    return {
        "display_name": best["display_name"],
        "latitude": best["latitude"],
        "longitude": best["longitude"],
        "matched_name": best["name"] or preferred_name,
        "place_type": best["type"],
    }


def _build_overpass_query(
    latitude: float,
    longitude: float,
    interests: list[str],
    radius: int = 20000,
) -> str:
    """Build one Overpass query for all selected interests."""

    filters = []

    for interest in interests:
        key = _normalise_interest(interest)

        for tag, _label in INTEREST_TAGS.get(key, []):
            filters.extend(
                [
                    f'nwr(around:{radius},{latitude},{longitude}){tag};'
                ]
            )

    # If no recognised interests were selected, retrieve common
    # tourism places so that arbitrary destinations still work.
    if not filters:
        filters = [
            f'nwr(around:{radius},{latitude},{longitude})["tourism"="attraction"];',
            f'nwr(around:{radius},{latitude},{longitude})["tourism"="museum"];',
            f'nwr(around:{radius},{latitude},{longitude})["leisure"="park"];',
            f'nwr(around:{radius},{latitude},{longitude})["amenity"="restaurant"];',
        ]

    return "[out:json][timeout:20];(" + "".join(filters) + ");out center tags;"


def _get_geoapify_places(destination: str, interests: list[str]) -> list[dict[str, Any]]:
    """Retrieve named planner places from Geoapify when available."""
    if not destination or not quota_manager.can_consume("geoapify"):
        return []
    try:
        geocoded = geoapify_service.geocode(destination, limit=1)
        if not geocoded:
            return []

        location = geocoded[0]
        latitude = float(location["latitude"])
        longitude = float(location["longitude"])

        category_map = {
            "food": ["catering.restaurant", "catering.cafe"],
            "culture": ["tourism.attraction"],
            "history": ["tourism.attraction"],
            "temples": ["religion.place_of_worship"],
            "sightseeing": ["tourism.attraction"],
            "nature": ["tourism.attraction"],
            "shopping": ["catering.cafe"],
            "adventure": ["tourism.attraction"],
            "nightlife": ["catering.restaurant", "catering.cafe"],
            "beaches": ["tourism.attraction"],
        }

        categories = []
        for interest in interests or []:
            categories.extend(category_map.get(str(interest).strip().lower(), []))

        if not categories:
            categories = ["tourism.attraction", "tourism.sights"]

        places = geoapify_service.places(
            latitude,
            longitude,
            categories=",".join(dict.fromkeys(categories)),
            radius=12000,
            limit=40,
        )
        quota_manager.consume("geoapify")

        normalized = []
        seen = set()
        for item in places or []:
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            try:
                lat = float(item["latitude"])
                lon = float(item["longitude"])
            except (KeyError, TypeError, ValueError):
                continue

            key = (name.lower(), round(lat, 5), round(lon, 5))
            if key in seen:
                continue
            seen.add(key)

            raw_categories = [str(value).lower() for value in (item.get("categories") or [])]
            tags = {}
            if any(value == "catering.restaurant" or value.startswith("catering.restaurant.") for value in raw_categories):
                tags["amenity"] = "restaurant"
            elif any(value == "catering.cafe" or value.startswith("catering.cafe.") for value in raw_categories):
                tags["amenity"] = "cafe"
            elif any(value == "tourism.attraction" or value.startswith("tourism.attraction.") for value in raw_categories):
                tags["tourism"] = "attraction"
            if any(value.startswith("religion.place_of_worship") for value in raw_categories):
                tags["amenity"] = "place_of_worship"
                if any("hindu" in value for value in raw_categories):
                    tags["religion"] = "hindu"

            normalized.append({
                "id": item.get("id") or f"geoapify-{len(normalized) + 1}",
                "name": name,
                "category": str((item.get("categories") or ["poi"])[0]),
                "type": "real_place",
                "latitude": lat,
                "longitude": lon,
                "address": item.get("address") or "",
                "tags": tags,
                "source": "Geoapify",
                "provider": "Geoapify",
            })

        return normalized
    except Exception:
        return []


def _get_places(
    latitude: float,
    longitude: float,
    interests: list[str],
    destination: str | None = None,
) -> list[dict]:
    """Retrieve named planner places using Geoapify -> OpenStreetMap -> no data."""
    endpoints = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
    ]
    radius = 12000

    interest_filters = {
        "food": [
            '["amenity"="restaurant"]',
            '["amenity"="cafe"]',
            '["amenity"="fast_food"]',
            '["amenity"="food_court"]',
        ],
        "culture": [
            '["tourism"="museum"]',
            '["tourism"="gallery"]',
            '["tourism"="artwork"]',
            '["amenity"="arts_centre"]',
            '["amenity"="place_of_worship"]',
            '["historic"]',
        ],
        "temples": [
            '["amenity"="place_of_worship"]',
        ],
        "history": [
            '["historic"]',
            '["tourism"="museum"]',
            '["tourism"="monument"]',
        ],
        "sightseeing": [
            '["tourism"="attraction"]',
            '["tourism"="viewpoint"]',
            '["tourism"="monument"]',
            '["tourism"="museum"]',
            '["tourism"="gallery"]',
            '["historic"]',
        ],
        "nature": [
            '["leisure"="park"]',
            '["leisure"="garden"]',
            '["leisure"="nature_reserve"]',
            '["natural"="wood"]',
            '["natural"="water"]',
            '["tourism"="viewpoint"]',
        ],
        "shopping": [
            '["shop"]',
            '["amenity"="marketplace"]',
        ],
        "adventure": [
            '["leisure"="sports_centre"]',
            '["leisure"="stadium"]',
            '["tourism"="attraction"]',
        ],
        "nightlife": [
            '["amenity"="bar"]',
            '["amenity"="pub"]',
            '["amenity"="nightclub"]',
        ],
        "beaches": [
            '["natural"="beach"]',
        ],
    }

    normalised = list(dict.fromkeys(
        _normalise_interest(item)
        for item in interests
        if item and item.strip()
    ))

    # Keep Geoapify as the quick path for food-only lookups, where its
    # categories are specific. For sightseeing, culture, nature and beaches,
    # also query OSM so semantic tags (beach, museum, worship, park) are
    # available to the interest matcher instead of treating every result as
    # the same generic attraction.
    geoapify_places = []
    if destination:
        geoapify_places = _get_geoapify_places(destination, interests)
        if geoapify_places and set(normalised).issubset({"food", "nightlife"}):
            return geoapify_places[:240]

    filters = []
    for interest in normalised:
        filters.extend(interest_filters.get(interest, []))

    if not filters:
        filters = [
            '["tourism"="attraction"]',
            '["tourism"="museum"]',
            '["tourism"="viewpoint"]',
            '["historic"]',
            '["amenity"="restaurant"]',
            '["amenity"="cafe"]',
            '["leisure"="park"]',
        ]

    filters = list(dict.fromkeys(filters))

    statements = [
        f'nwr(around:{radius},{latitude},{longitude}){tag_filter};'
        for tag_filter in filters
    ]
    query = "[out:json][timeout:18];(" + "".join(statements) + ");out center tags;"

    elements = []
    for endpoint in endpoints:
        try:
            data = _http_post_json(
                endpoint,
                data=urllib.parse.urlencode({"data": query}),
                timeout=18,
            )
            elements = data.get("elements", [])
            if elements:
                break
        except Exception:
            continue

    places = []
    seen = set()

    for element in elements:
        tags = element.get("tags", {}) or {}
        name = str(tags.get("name", "")).strip()
        if not name:
            continue

        center = element.get("center", {}) or {}
        place_lat = element.get("lat", center.get("lat"))
        place_lon = element.get("lon", center.get("lon"))
        if place_lat is None or place_lon is None:
            continue

        key = (
            name.casefold(),
            round(float(place_lat), 5),
            round(float(place_lon), 5),
        )
        if key in seen:
            continue
        seen.add(key)

        places.append({
            "name": name,
            "category": _detect_category(tags),
            "type": "real_place",
            "latitude": place_lat,
            "longitude": place_lon,
            "tags": tags,
            "source": "OpenStreetMap",
            "provider": "OpenStreetMap",
        })

    places.sort(
        key=lambda item: _haversine_km(
            latitude,
            longitude,
            item.get("latitude"),
            item.get("longitude"),
        ) or 9999.0
    )

    # Prefer OSM's detailed tags when both providers identify the same POI.
    combined = places + geoapify_places
    deduplicated = []
    for place in combined:
        if not _is_duplicate_place(place, deduplicated):
            deduplicated.append(place)
    return deduplicated[:240]


def _normalise_place_name(name: str) -> str:
    """Create a comparison-friendly place name."""
    text = unicodedata.normalize("NFKD", str(name or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    return re.sub(r"\s+", " ", text)


def _is_duplicate_place(place: dict, existing: list[dict]) -> bool:
    """Detect exact-name, translated-name and same-site OSM duplicates."""
    name_key = _normalise_place_name(place.get("name", ""))
    lat = place.get("latitude")
    lon = place.get("longitude")
    category = str(place.get("category", "")).lower()

    for old in existing:
        old_key = _normalise_place_name(old.get("name", ""))

        if name_key and old_key and name_key == old_key:
            return True

        distance = _haversine_km(
            lat, lon,
            old.get("latitude"), old.get("longitude"),
        )
        if distance is None:
            continue

        old_category = str(old.get("category", "")).lower()

        # Beaches/promendades are especially prone to multilingual OSM
        # duplicates representing the same waterfront. Use a larger
        # same-category radius for those records.
        beachish = {
            "beach", "beaches", "beach resort", "waterfront",
            "seafront", "shore", "coast",
        }
        if category in beachish and old_category in beachish and distance <= 0.45:
            return True

        if distance <= 0.08:
            related = (
                category == old_category
                or category in {"tourist place", "attraction", "culture", "historic place"}
                or old_category in {"tourist place", "attraction", "culture", "historic place"}
            )
            if related:
                return True

    return False


def _detect_category(tags: dict) -> str:
    """Convert OSM tags into a useful tourism category."""

    tourism = tags.get("tourism", "")
    amenity = tags.get("amenity", "")
    leisure = tags.get("leisure", "")
    natural = tags.get("natural", "")
    historic = tags.get("historic", "")
    shop = tags.get("shop", "")

    name = str(tags.get("name") or "").lower()

    if natural == "beach":
        return "Beach"

    if any(term in name for term in (
        "beach", "promenade", "waterfront", "seafront", "shore", "coast"
    )):
        return "Beach"

    if tourism == "museum":
        return "Museum"

    if tourism == "viewpoint":
        return "Viewpoint"

    if tourism == "monument":
        return "Monument"

    if tourism == "attraction":
        return "Attraction"

    if tourism in {"gallery", "artwork"}:
        return "Culture"

    if historic:
        return "Historic place"

    if amenity == "restaurant":
        return "Restaurant"

    if amenity == "cafe":
        return "Cafe"

    if amenity in {"fast_food", "food_court"}:
        return "Food"

    if amenity == "marketplace":
        return "Market"

    if amenity in {"bar", "pub", "nightclub"}:
        return "Nightlife"

    if shop:
        return "Shopping"

    if leisure in {"park", "garden", "nature_reserve"}:
        return "Nature"

    if leisure in {"sports_centre", "stadium"}:
        return "Adventure"

    return "Tourist place"


def _haversine_km(
    lat1: float | None,
    lon1: float | None,
    lat2: float | None,
    lon2: float | None,
) -> float | None:
    """Return approximate great-circle distance in kilometres."""

    if None in (lat1, lon1, lat2, lon2):
        return None

    from math import asin, cos, radians, sin, sqrt

    earth_radius = 6371.0

    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)

    a = (
        sin(d_lat / 2) ** 2
        + cos(radians(lat1))
        * cos(radians(lat2))
        * sin(d_lon / 2) ** 2
    )

    return round(
        earth_radius * 2 * asin(sqrt(a)),
        2,
    )


def _interest_matches_place(
    interest: str,
    place: dict,
) -> int:
    """
    Strictly score a place for one interest.

    The important rule is that a place should not receive a positive
    score merely because it is a generic tourist attraction. For example,
    a temple must not be selected for a food day and a beach day must not
    be filled with temples or museums.
    """

    interest = _normalise_interest(interest)
    category = str(place.get("category", "")).lower()
    tags = place.get("tags", {}) or {}

    tourism = tags.get("tourism", "")
    amenity = tags.get("amenity", "")
    leisure = tags.get("leisure", "")
    natural = tags.get("natural", "")
    historic = tags.get("historic", "")
    shop = tags.get("shop", "")
    name = str(place.get("name", "")).lower()

    score = 0

    if interest == "beaches":
        # STRICT: only actual beach/coast/waterfront places.
        if natural == "beach":
            score = 150
        elif "beach" in category:
            score = 120
        elif any(term in name for term in (
            "beach", "promenade", "waterfront", "seafront",
            "shore", "coast",
        )):
            score = 105
        else:
            return 0

    elif interest == "food":
        # STRICT: only food establishments.
        if amenity == "restaurant":
            score = 120
        elif amenity == "cafe":
            score = 105
        elif amenity in {"food_court", "fast_food"}:
            score = 75
        elif category in {"restaurant", "cafe", "food"}:
            score = 65
        else:
            return 0

        # Prefer local food over international/chain fast food.
        chain_terms = (
            "kfc", "domino", "domino's", "mcdonald", "subway",
            "pizza hut", "burger king", "starbucks", "papa john",
            "papa john's", "wendy's", "dunkin",
        )
        if any(term in name for term in chain_terms):
            score -= 35

        local_terms = (
            "local", "traditional", "south indian", "indian",
            "tiffin", "thali", "udupi", "mess", "bhojanalaya",
            "restaurant", "cafe", "café",
        )
        if any(term in name for term in local_terms):
            score += 8

    elif interest == "temples":
        religion = str(tags.get("religion") or "").lower()
        denomination = str(tags.get("denomination") or "").lower()
        temple_terms = ("temple", "mandir", "basavana gudi", "ganesha gudi")
        if (amenity == "place_of_worship" and religion in {"hindu", "hinduism"}) or any(
            term in name or term in category for term in temple_terms
        ) or "hindu" in denomination:
            score = 145
        else:
            return 0

    elif interest == "sightseeing":
        # Attractions, viewpoints, monuments and museums are valid
        # sightseeing places. Worship/historic places can also qualify.
        if tourism in {"attraction", "viewpoint", "monument"}:
            score = 120
        elif tourism in {"museum", "gallery"}:
            score = 105
        elif historic:
            score = 95
        elif category in {
            "attraction", "viewpoint", "monument",
            "historic place", "museum", "tourist place",
        }:
            score = 80
        else:
            return 0

    elif interest == "history":
        if historic:
            score = 130
        elif tourism in {"museum", "monument"}:
            score = 115
        elif category in {"historic place", "museum", "monument"}:
            score = 95
        else:
            return 0

    elif interest == "culture":
        if tourism in {"museum", "gallery", "artwork"}:
            score = 120
        elif amenity == "place_of_worship":
            score = 110
        elif historic:
            score = 105
        elif category in {"culture", "museum", "historic place"}:
            score = 90
        else:
            return 0

    elif interest == "nature":
        if natural or leisure in {"park", "garden", "nature_reserve"}:
            score = 120
        elif tourism == "viewpoint":
            score = 105
        elif category in {"nature", "viewpoint"}:
            score = 90
        else:
            return 0

    elif interest == "shopping":
        if shop:
            score = 120
        elif amenity == "marketplace":
            score = 110
        elif category in {"shopping", "market"}:
            score = 90
        else:
            return 0

    elif interest == "adventure":
        if leisure in {"sports_centre", "stadium"}:
            score = 110
        elif tags.get("sport"):
            score = 105
        elif tourism == "attraction":
            score = 80
        elif category == "adventure":
            score = 75
        else:
            return 0

    elif interest == "nightlife":
        if amenity in {"bar", "pub", "nightclub"}:
            score = 120
        elif category == "nightlife":
            score = 100
        else:
            return 0

    return max(score, 0)


def _interest_compatibility(primary: str, secondary: str) -> bool:
    """Allow only sensible secondary interests for a day's theme."""
    if primary == secondary:
        return True

    compatible_pairs = {
        frozenset({"culture", "sightseeing"}),
        frozenset({"history", "culture"}),
        frozenset({"history", "sightseeing"}),
        frozenset({"nature", "adventure"}),
        frozenset({"beaches", "nature"}),
        frozenset({"beaches", "adventure"}),
        frozenset({"shopping", "food"}),
        frozenset({"nightlife", "food"}),
    }

    return frozenset({primary, secondary}) in compatible_pairs


def _build_day_theme_plan(
    interests: list[str],
    days: int,
    places: list[dict],
) -> list[dict]:
    """
    Build a balanced primary/secondary interest plan.

    Important design rule:
    - Distinctive themes such as beaches and food get their own day when
      possible.
    - Culture + sightseeing are paired because they naturally overlap.
    - With 4 interests and 3 days, no interest is silently discarded.
    """
    normalised = list(dict.fromkeys(
        _normalise_interest(item)
        for item in interests
        if item and item.strip()
    ))

    if not normalised:
        normalised = ["sightseeing", "food", "nature"]

    if days <= 0:
        return []

    available = set(normalised)

    # Only promote an interest to a primary day when at least one real
    # place currently matches that interest. This prevents a valid
    # multi-day request from producing an empty day simply because the
    # selected provider returned no POIs for one requested theme.
    # The planner still keeps strict interest matching: it never invents
    # a place or substitutes an unrelated category just to fill a day.
    available_with_places = {
        interest
        for interest in normalised
        if any(_interest_matches_place(interest, place) > 0 for place in places)
    }

    # Best-practice layout for the common tourism case:
    # 4 interests -> 3 days, with culture + sightseeing combined, but only
    # when those themes actually have matching real places available.
    if days == 3 and {"beaches", "food", "culture", "sightseeing"}.issubset(available):
        if {"beaches", "food", "culture"}.issubset(available_with_places):
            return [
                {"primary": "beaches", "secondary": []},
                {"primary": "culture", "secondary": ["sightseeing"]},
                {"primary": "food", "secondary": []},
            ]

    # If a requested theme has no usable real places, do not assign an
    # otherwise empty day to it. Prefer another requested theme that has
    # actual provider data; unavailable themes can still be paired as
    # secondary interests where compatibility permits.

    # General case: protect distinctive themes first.
    preferred = []
    for item in ("beaches", "food", "culture", "history", "sightseeing",
                 "nature", "adventure", "shopping", "nightlife"):
        if item in available and item not in preferred:
            preferred.append(item)

    # Add any custom/unknown interest names at the end.
    for item in normalised:
        if item not in preferred:
            preferred.append(item)

    # Prefer themes with real provider results. Keep unavailable requested
    # themes in the plan only when there are not enough available themes to
    # cover the requested number of days. In that case the existing
    # no-data behavior remains explicit rather than fabricating activities.
    preferred_available = [item for item in preferred if item in available_with_places]
    preferred_unavailable = [item for item in preferred if item not in available_with_places]

    primary = preferred_available[:days]

    while len(primary) < days:
        remaining = [item for item in preferred_unavailable if item not in primary]
        if not remaining:
            remaining = preferred
        if not remaining:
            break
        primary.append(remaining[0])

    plan = [{"primary": item, "secondary": []} for item in primary]

    omitted = [item for item in normalised if item not in primary]

    # Pair omitted interests only with compatible primary themes.
    for extra in omitted:
        candidates = [
            i for i, item in enumerate(plan)
            if _interest_compatibility(item["primary"], extra)
        ]
        if not candidates:
            continue

        # Prefer a culture+sightseeing pairing.
        if extra == "sightseeing":
            culture_candidates = [
                i for i in candidates if plan[i]["primary"] == "culture"
            ]
            target = culture_candidates[0] if culture_candidates else candidates[0]
        else:
            target = min(candidates, key=lambda i: len(plan[i]["secondary"]))

        if extra not in plan[target]["secondary"]:
            plan[target]["secondary"].append(extra)

    return plan[:days]


def _place_quality_score(place: dict, interest: str) -> int:
    """
    Score whether an OSM record looks like a meaningful tourist POI.

    OSM is a rich community dataset, so a broad query can also return
    low-value objects such as gates, libraries, individual names, or
    administrative features. This layer keeps those from dominating the
    final itinerary.
    """
    tags = place.get("tags", {}) or {}
    name = str(place.get("name", "")).lower()
    tourism = tags.get("tourism", "")
    amenity = tags.get("amenity", "")
    historic = tags.get("historic", "")
    leisure = tags.get("leisure", "")

    score = 0

    if tourism in {"attraction", "viewpoint", "museum", "gallery", "artwork"}:
        score += 35

    if historic in {
        "monument", "memorial", "castle", "palace", "fort",
        "archaeological_site", "ruins", "building",
    }:
        score += 30

    if amenity == "place_of_worship":
        score += 18

    if interest == "sightseeing":
        # Explicit tourist tags are substantially better than generic
        # historic/amenity records.
        if tourism in {"attraction", "viewpoint", "museum", "gallery"}:
            score += 35
        if name in {"main gate", "gate", "library"}:
            score -= 50
        if amenity == "library":
            score -= 60

    if interest == "culture":
        if tourism in {"museum", "gallery", "artwork"}:
            score += 35
        if amenity == "place_of_worship":
            score += 25
        if name in {"main gate", "gate", "library"}:
            score -= 35
        if amenity == "library":
            score -= 60

    if interest == "food":
        if amenity == "restaurant":
            score += 25
        elif amenity == "cafe":
            score += 18
        elif amenity in {"fast_food", "food_court"}:
            score += 8

        chain_terms = (
            "kfc", "domino", "domino's", "mcdonald", "subway",
            "pizza hut", "burger king", "starbucks", "papa john",
            "papa john's", "wendy's", "dunkin",
        )
        if any(term in name for term in chain_terms):
            score -= 35

        local_terms = (
            "udupi", "tiffin", "thali", "mess", "bhojanalaya",
            "south indian", "traditional", "local", "saravana",
        )
        if any(term in name for term in local_terms):
            score += 22

    if interest == "beaches":
        # A real beach must be explicitly tagged as a beach or have a
        # strong coastal place name. A cafe/restaurant near a beach is
        # still food, not a beach.
        if tags.get("natural") == "beach":
            score += 60
        elif any(term in name for term in (
            "beach", "promenade", "waterfront", "seafront", "shore", "coast"
        )):
            score += 25
        else:
            score -= 80

    return score


def _is_low_value_place(place: dict, interest: str) -> bool:
    """Reject records that are technically valid OSM objects but poor itinerary POIs."""
    tags = place.get("tags", {}) or {}
    name = str(place.get("name", "")).strip().lower()
    amenity = tags.get("amenity", "")
    tourism = tags.get("tourism", "")
    historic = tags.get("historic", "")

    if interest in {"sightseeing", "culture"}:
        # These are normally services/facilities, not standalone tourist
        # attractions. Keep them only when OSM explicitly marks them as
        # a tourist attraction/museum.
        non_tourist_amenities = {
            "library", "school", "college", "university", "office",
            "post_office", "bank", "police", "fire_station",
            "government", "clinic", "hospital",
        }
        if amenity in non_tourist_amenities and tourism not in {
            "attraction", "museum", "gallery"
        }:
            return True

        if name in {
            "main gate", "gate", "entrance", "exit",
            "parking", "car park", "bus stop",
        } and tourism not in {"attraction", "museum", "gallery"}:
            return True

    if interest == "beaches":
        # Cafes/restaurants with beach-related names are food businesses.
        # Do not use them as the beach POI unless OSM says natural=beach
        # or the feature itself is clearly a coastal place.
        if amenity in {"restaurant", "cafe", "fast_food", "food_court"}:
            if tags.get("natural") != "beach":
                return True

    return False


def _max_distance_for_interest(interest: str) -> float:
    """Maximum preferred distance from the destination centre in km."""
    return {
        "food": 5.0,
        "beaches": 8.0,
        "culture": 8.0,
        "sightseeing": 10.0,
        "history": 10.0,
        "nature": 12.0,
        "adventure": 15.0,
        "shopping": 7.0,
        "nightlife": 7.0,
    }.get(interest, 8.0)


def _is_reasonably_close(place: dict, interest: str) -> bool:
    distance = place.get("distance_from_center_km")
    if distance is None:
        return True
    return distance <= _max_distance_for_interest(interest)


def _select_best_places(
    places: list[dict],
    interests: list[str],
    destination_lat: float | None,
    destination_lon: float | None,
    days: int,
) -> list[dict]:
    """Select real places with explicit per-interest and per-day coverage.

    Each requested interest gets an opportunity to contribute places before
    the global pool is filled. This prevents food results from consuming the
    entire selection and leaving later days empty.
    """
    normalised = list(dict.fromkeys(
        _normalise_interest(item)
        for item in interests
        if item and item.strip()
    )) or ["sightseeing", "food", "nature"]

    # Four substantial visits per day fit the schedule: two before lunch and
    # two after lunch. Reserve places across every requested interest first.
    target_total = max(1, days) * 4
    scored = {interest: [] for interest in normalised}

    for place in places:
        distance = _haversine_km(
            destination_lat,
            destination_lon,
            place.get("latitude"),
            place.get("longitude"),
        )
        for interest in normalised:
            score = _interest_matches_place(interest, place)
            if score <= 0:
                continue

            item = dict(place)
            item["matched_interest"] = interest
            item["distance_from_center_km"] = distance
            item["relevance_score"] = (
                score
                + max(0.0, 20.0 - min(distance or 20.0, 20.0))
                + (40.0 if item.get("source") == "Curated travel guide" else 0.0)
            )
            scored[interest].append(item)

    for interest in scored:
        scored[interest].sort(
            key=lambda item: item["relevance_score"],
            reverse=True,
        )

    selected = []
    used = set()

    def add_from_interest(interest: str, limit: int) -> None:
        added = 0
        for place in scored.get(interest, []):
            key = (
                place.get("name", "").strip().casefold(),
                round(float(place.get("latitude") or 0), 5),
                round(float(place.get("longitude") or 0), 5),
            )
            if not key[0] or key in used:
                continue

            duplicate = False
            for old in selected:
                if old.get("name", "").strip().casefold() == key[0]:
                    duplicate = True
                    break
                if (
                    _distance_between_places(place, old) < 0.10
                    and place.get("matched_interest") == old.get("matched_interest")
                ):
                    duplicate = True
                    break
            if duplicate:
                continue

            selected.append(place)
            used.add(key)
            added += 1
            if added >= limit or len(selected) >= target_total:
                break

    for _ in range(max(1, days)):
        for interest in normalised:
            if len(selected) >= target_total:
                break
            add_from_interest(interest, 1)

    if len(selected) < target_total:
        remaining = []
        for interest in normalised:
            remaining.extend(
                p for p in scored.get(interest, [])
                if (
                    p.get("name", "").strip().casefold(),
                    round(float(p.get("latitude") or 0), 5),
                    round(float(p.get("longitude") or 0), 5),
                ) not in used
            )

        remaining.sort(
            key=lambda item: item["relevance_score"],
            reverse=True,
        )
        for place in remaining:
            key = (
                place.get("name", "").strip().casefold(),
                round(float(place.get("latitude") or 0), 5),
                round(float(place.get("longitude") or 0), 5),
            )
            if not key[0] or key in used:
                continue
            selected.append(place)
            used.add(key)
            if len(selected) >= target_total:
                break

    return selected[:target_total]


def _distance_between_places(
    first: dict,
    second: dict,
) -> float:
    distance = _haversine_km(
        first.get("latitude"),
        first.get("longitude"),
        second.get("latitude"),
        second.get("longitude"),
    )

    return distance if distance is not None else 9999.0


def _group_places_by_day(
    places: list[dict],
    days: int,
    destination_lat: float | None,
    destination_lon: float | None,
) -> list[list[dict]]:
    """
    Group places geographically into coherent day clusters.

    The algorithm:
    1. Starts with a place close to the destination centre.
    2. Chooses additional seeds that are farthest from the existing seeds,
       creating genuinely different geographic areas for different days.
    3. Assigns remaining places to the nearest/least-loaded group.

    This keeps the planner lightweight while reducing unnecessary
    cross-city travel.
    """

    if days <= 0:
        return []

    if not places:
        return [[] for _ in range(days)]

    ordered = sorted(
        places,
        key=lambda place: (
            place.get("distance_from_center_km")
            if place.get("distance_from_center_km") is not None
            else 9999
        ),
    )

    group_count = min(days, len(ordered))
    groups = [[] for _ in range(days)]

    # First seed: closest useful place to the destination centre.
    seeds = [ordered[0]]
    remaining_seed_candidates = ordered[1:]

    # Additional seeds: choose the point farthest from the current seed set.
    # This is more geographically meaningful than simply taking ordered[:days].
    while len(seeds) < group_count:
        next_seed = max(
            remaining_seed_candidates,
            key=lambda candidate: min(
                _distance_between_places(candidate, seed)
                for seed in seeds
            ),
        )
        seeds.append(next_seed)
        remaining_seed_candidates.remove(next_seed)

    for index, seed in enumerate(seeds):
        groups[index].append(seed)

    seed_names = {
        _normalise_place_name(seed.get("name", ""))
        for seed in seeds
    }

    remaining = [
        place
        for place in ordered
        if _normalise_place_name(place.get("name", "")) not in seed_names
    ]

    # Assign each remaining place to the geographically closest group,
    # with a small penalty for overfilling a day.
    for place in remaining:
        best_group = 0
        best_value = float("inf")

        for index in range(group_count):
            group = groups[index]

            average_distance = (
                sum(
                    _distance_between_places(place, existing)
                    for existing in group
                ) / len(group)
                if group
                else 0
            )

            balance_penalty = len(group) * 2
            value = average_distance + balance_penalty

            if value < best_value:
                best_value = value
                best_group = index

        groups[best_group].append(place)

    return groups


def _theme_for_day(
    day: int,
    day_places: list[dict],
    interests: list[str],
) -> str:
    """Create a useful human-readable day theme."""

    matched = [
        place.get("matched_interest")
        for place in day_places
        if place.get("matched_interest")
    ]

    if matched:
        counts = {}

        for item in matched:
            counts[item] = counts.get(item, 0) + 1

        strongest = max(
            counts,
            key=counts.get,
        )

        return strongest.replace("_", " ").title()

    if interests:
        return interests[(day - 1) % len(interests)].replace(
            "_",
            " ",
        ).title()

    return "Explore & Relax"


def _time_slot_for_index(index: int) -> str:
    slots = [
        "Morning",
        "Afternoon",
        "Evening",
    ]

    return slots[min(index, len(slots) - 1)]


def _estimate_activity_cost(
    category: str,
    budget_level: str,
) -> int:
    """
    Conservative project-level cost estimate in INR.

    These are estimates, not live ticket prices.
    """

    base_costs = {
        "Beach": 300,
        "Museum": 250,
        "Monument": 200,
        "Historic place": 200,
        "Attraction": 300,
        "Viewpoint": 100,
        "Restaurant": 500,
        "Cafe": 250,
        "Food": 300,
        "Market": 300,
        "Shopping": 500,
        "Nature": 150,
        "Adventure": 700,
        "Nightlife": 700,
        "Culture": 250,
        "Tourist place": 250,
    }

    cost = base_costs.get(category, 250)

    if budget_level == "budget":
        return int(cost * 0.8)

    if budget_level == "premium":
        return int(cost * 1.25)

    return cost

def _budget_level(budget: float) -> str:
    """
    Simple budget classification for a student-project prototype.
    Budget is assumed to be the total trip budget.
    """
    if budget < 5000:
        return "budget"
    if budget < 15000:
        return "moderate"
    return "premium"


def _fallback_for_interest(
    interest: str,
    used: set[str],
) -> str | None:
    """Get an unused generic activity for a selected interest."""

    activities = ACTIVITY_POOLS.get(
        _normalise_interest(interest),
        [],
    )

    for activity in activities:
        if activity not in used:
            return activity

    # A multi-day trip can legitimately need more suggestions than the
    # small generic pool contains. Reuse a theme-correct activity rather
    # than leaving later days empty.
    return activities[len(used) % len(activities)] if activities else None


def _day_title(
    primary: str,
    secondary: list[str],
    activities: list[dict],
    destination: str,
) -> str:
    """Create a concise title that reflects the actual mix planned that day."""
    present = list(dict.fromkeys(
        str(item.get("interest_match") or "").strip()
        for item in activities if item.get("interest_match")
    ))
    labels = {
        "beaches": "Beach", "food": "Food", "culture": "Culture",
        "sightseeing": "Sightseeing", "history": "Heritage",
        "nature": "Nature", "shopping": "Shopping",
        "adventure": "Adventure", "nightlife": "Nightlife",
    }
    # Put the main travel experiences first; include up to three distinct themes.
    priority = ["beaches", "adventure", "culture", "history", "sightseeing", "nature", "shopping", "food", "nightlife"]
    present.sort(key=lambda value: priority.index(value) if value in priority else len(priority))
    chosen = present[:4] or [primary, *secondary][:4]
    names = [labels.get(item, item.replace("_", " ").title()) for item in chosen]
    if not names:
        return f"{destination} Highlights"
    return f"{destination} " + " & ".join(names) + " Highlights"


def _activity_description(activity: dict) -> str:
    """Generate concise guide-style text from the structured place data."""
    name = activity.get("name", "This place")
    category = str(activity.get("category", "tourist place"))
    interest = str(activity.get("interest_match", "sightseeing")).replace("_", " ")

    descriptions = {
        "beaches": f"Spend time at {name} and enjoy the coastal atmosphere. It is included because it matches your beach interest.",
        "food": f"Try local food or relax at {name}. It is included because it matches your food interest.",
        "culture": f"Explore {name} to experience the local culture and heritage.",
        "sightseeing": f"Visit {name} as one of the sightseeing highlights of the trip.",
        "history": f"Explore {name} to learn about the destination's history and heritage.",
        "nature": f"Enjoy the natural surroundings at {name} and take some time to relax.",
        "shopping": f"Explore {name} for local shopping, souvenirs, or regional products.",
        "adventure": f"Enjoy an outdoor or adventure experience at {name}.",
        "nightlife": f"Spend the evening at {name} and enjoy the local atmosphere.",
    }
    return descriptions.get(interest, f"Explore {name}, a {category.lower()} selected for your trip.")


def _recommendation_level(activity: dict) -> str:
    """Return a simple frontend-friendly recommendation label."""
    if activity.get("type") != "real_place":
        return "suggested"

    category = str(activity.get("category", "")).lower()
    interest = str(activity.get("interest_match", "")).lower()

    if interest == "beaches" and category == "beach":
        return "must_visit"

    if category in {"attraction", "museum", "viewpoint", "monument"}:
        return "must_visit"

    if interest == "food" and category == "restaurant":
        return "recommended"

    return "recommended"


def _guide_section(activity: dict) -> dict:
    """Convert an activity into a frontend-friendly travel-guide section."""
    cost = activity.get("estimated_cost_inr", 0)
    category = str(activity.get("category", "Tourist place"))
    interest = str(activity.get("interest_match", "sightseeing"))

    level = _recommendation_level(activity)
    time_slot = activity.get("time_slot", "Morning")
    best_times = {
        "Morning": "Best time: 7:00 AM–10:00 AM",
        "Afternoon": "Best time: 12:30 PM–3:30 PM",
        "Evening": "Best time: 4:30 PM–7:30 PM",
    }

    return {
        "title": activity.get("name"),
        "time": activity.get("time_slot"),
        "best_time_to_visit": best_times.get(time_slot, "Best time: check local opening hours"),
        "description": _activity_description(activity),
        "category": category,
        "budget_inr": cost,
        "distance_km": activity.get("distance_from_destination_km"),
        "latitude": activity.get("latitude"),
        "longitude": activity.get("longitude"),
        "interest_match": interest,
        "recommendation_level": level,
        "must_visit": level == "must_visit",
        "source": activity.get("source", "Curated guide"),
    }


def _create_daily_plan(
    destination: str,
    days: int,
    interests: list[str],
    budget: float,
    places: list[dict],
    destination_lat: float | None = None,
    destination_lon: float | None = None,
    selected_places: list[dict] | None = None,
    geographic_groups: list[list[dict]] | None = None,
) -> list[dict]:
    """Build a mixed-interest itinerary for every requested day.

    The traveller's interests are treated as trip-wide preferences, not as
    separate themes assigned to individual days. Each day gets a fair chance
    to include a place from every requested interest when enough distinct
    places are available. Remaining slots are filled in a round-robin order,
    while preferring places near that day's geographic cluster.
    """
    normalised = list(dict.fromkeys(
        _normalise_interest(item)
        for item in interests if item and item.strip()
    )) or ["sightseeing", "food", "nature"]
    budget_level = _budget_level(budget)

    selected = selected_places if selected_places is not None else _select_best_places(
        places, normalised, destination_lat, destination_lon, days
    )
    if geographic_groups is None:
        geographic_groups = _group_places_by_day(
            selected, days, destination_lat, destination_lon
        )

    geographic_day_names = [
        {_normalise_place_name(place.get("name", "")) for place in group}
        for group in geographic_groups
    ]

    # Build independent per-interest pools. Normalise provider labels here as
    # well as the requested interests (providers often return singular aliases).
    buckets = {interest: [] for interest in normalised}
    seen_by_interest: dict[str, set[str]] = {interest: set() for interest in normalised}
    for raw_place in selected:
        place = dict(raw_place)
        matched = _normalise_interest(str(place.get("matched_interest") or ""))
        if matched not in buckets:
            matched = next((interest for interest in normalised
                            if _interest_matches_place(interest, place) > 0), None)
        if matched is None:
            continue
        place["matched_interest"] = matched
        key = _normalise_place_name(place.get("name", ""))
        if not key or key in seen_by_interest[matched]:
            continue
        seen_by_interest[matched].add(key)
        buckets[matched].append(place)

    # Geographic anchors are already assigned to specific days. Remove those
    # place names from every interest bucket so an anchor cannot be selected a
    # second time on another day or inflate the remaining-place reservation.
    anchor_names = {
        _normalise_place_name(group[0].get("name", ""))
        for group in geographic_groups
        if group and _normalise_place_name(group[0].get("name", ""))
    }
    if anchor_names:
        for interest, bucket in buckets.items():
            buckets[interest] = [
                place for place in bucket
                if _normalise_place_name(place.get("name", "")) not in anchor_names
            ]

    for bucket in buckets.values():
        bucket.sort(key=lambda p: p.get("distance_from_center_km")
                    if p.get("distance_from_center_km") is not None else 9999)

    # Do not consume every place for the first day: distribute each interest's
    # pool across days first, then fill remaining slots in a round-robin pass.
    used_real: set[str] = set()
    fallback_used: set[str] = set()
    itinerary = []

    # Put visitor attractions first when filling a limited number of daily
    # stops. Food still gets a place each day when selected, but does not push
    # museums, beaches, culture or other sightseeing off the itinerary.
    planning_interests = sorted(normalised, key=lambda item: (item == "food", normalised.index(item)))

    for day_index in range(days):
        day_group = geographic_groups[day_index] if day_index < len(geographic_groups) else []
        preferred_names = geographic_day_names[day_index] if day_index < len(geographic_day_names) else set()
        day_places = []
        # Keep the geographic cluster's seed attraction on its assigned day.
        # Otherwise category-first selection can choose a nearby minor stop
        # and then exclude the day's main landmark as too far away.
        if day_group:
            anchor = dict(day_group[0])
            anchor_name = _normalise_place_name(anchor.get("name", ""))

            # Grouping operates on raw places, which may not carry the
            # per-interest label added while building the buckets. Infer it
            # from the requested interests so the anchor counts toward daily
            # interest coverage instead of using a generic sightseeing label.
            anchor_interest = _normalise_interest(
                str(anchor.get("matched_interest") or anchor.get("interest_match") or "")
            )
            if anchor_interest not in buckets:
                anchor_interest = next(
                    (
                        interest for interest in normalised
                        if _interest_matches_place(interest, anchor) > 0
                    ),
                    None,
                )
            if anchor_interest:
                anchor["matched_interest"] = anchor_interest

            if anchor_name:
                day_places.append(anchor)
                used_real.add(anchor_name)

        def fits_day_cluster(place: dict) -> bool:
            # Prefer each day's geographic cluster, but allow another nearby
            # matching POI when that cluster lacks a requested interest.
            # An 8 km radius leaves room for a practical urban trip while
            # rejecting cross-city jumps such as ISKCON to Bannerghatta.
            if place.get("latitude") is not None and place.get("longitude") is not None:
                for existing in day_places:
                    if existing.get("latitude") is None or existing.get("longitude") is None:
                        continue
                    if _distance_between_places(place, existing) > 8.0:
                        return False
            return True

        # First pass: one place per requested interest, preferring places in
        # this day's geographic cluster. Index-based distribution ensures
        # three beaches / restaurants / museums are spread across three days.
        for interest in planning_interests:
            bucket = buckets.get(interest, [])
            # The geographic anchor may already cover this interest. Keep
            # one stop per interest in this pass so one category cannot use
            # up places needed to give the later days the same coverage.
            if any(place.get("matched_interest") == interest for place in day_places):
                continue
            if not bucket or len(day_places) >= 4:
                continue
            bucket.sort(key=lambda p: (
                0 if _normalise_place_name(p.get("name", "")) in preferred_names else 1,
                p.get("distance_from_center_km") if p.get("distance_from_center_km") is not None else 9999,
            ))
            chosen_index = next((i for i, p in enumerate(bucket)
                                 if _normalise_place_name(p.get("name", "")) not in used_real
                                 and fits_day_cluster(p)), None)
            if chosen_index is None:
                continue
            place = bucket.pop(chosen_index)
            key = _normalise_place_name(place.get("name", ""))
            used_real.add(key)
            day_places.append(place)

        # Fill up to five stops, rotating through requested interests so no
        # single category (especially food) monopolises a day.
        remaining_days_after_today = days - day_index - 1
        while len(day_places) < 4:
            added = False
            for interest in planning_interests:
                bucket = buckets.get(interest, [])
                # A named restaurant is an optional food experience, not a
                # replacement for the three meals already in the schedule.
                if interest == "food" and any(p.get("matched_interest") == "food" for p in day_places):
                    continue
                # Reserve at least one distinct place in this category for
                # each remaining day before adding optional extra stops today.
                if len(bucket) <= remaining_days_after_today:
                    continue
                chosen_index = next((i for i, p in enumerate(bucket)
                                     if _normalise_place_name(p.get("name", "")) not in used_real
                                     and fits_day_cluster(p)), None)
                if chosen_index is None:
                    continue
                place = bucket.pop(chosen_index)
                key = _normalise_place_name(place.get("name", ""))
                used_real.add(key)
                day_places.append(place)
                added = True
                if len(day_places) >= 4:
                    break
            if not added:
                break

        activities = []
        for index, place in enumerate(day_places[:5]):
            interest = place.get("matched_interest", "sightseeing")
            category = str(place.get("category") or interest.replace("_", " ").title())
            activities.append({
                "name": place.get("name", "Explore local attraction"),
                "category": category,
                "type": "real_place",
                "interest_match": interest,
                "time_slot": _time_slot_for_index(index),
                "estimated_cost_inr": _estimate_activity_cost(category, budget_level),
                "distance_from_destination_km": place.get("distance_from_center_km"),
                "latitude": place.get("latitude"),
                "longitude": place.get("longitude"),
                "source": place.get("source"),
                "provider": place.get("provider"),
                "reason": f"Selected because it matches your {interest.replace('_', ' ')} interest.",
            })

        # Generic suggestions remain disabled unless explicitly enabled for demo mode.
        allow_generic_fallback = os.getenv("PLANNER_ALLOW_GENERIC_FALLBACK", "false").strip().lower() in {"1", "true", "yes", "on"}
        fallback_attempts = 0
        while allow_generic_fallback and len(activities) < min(3, max(1, len(normalised))) and fallback_attempts < len(normalised) * 4:
            interest = normalised[(day_index + fallback_attempts) % len(normalised)]
            fallback_attempts += 1
            fallback = _fallback_for_interest(interest, fallback_used)
            if not fallback:
                continue
            fallback_used.add(fallback)
            category = "Beach" if interest == "beaches" else interest.replace("_", " ").title()
            activities.append({
                "name": fallback, "category": category, "type": "activity",
                "interest_match": interest,
                "time_slot": _time_slot_for_index(len(activities)),
                "estimated_cost_inr": _estimate_activity_cost(category, budget_level),
                "reason": "A suggested activity for a selected interest; verify local availability.",
            })

        # Order actual places with a nearest-neighbour route to avoid needless backtracking.
        real = [item for item in activities if item.get("type") == "real_place"]
        if len(real) > 1:
            route = [real[0]]
            remaining = real[1:]
            while remaining:
                nxt = min(remaining, key=lambda item: _distance_between_places(route[-1], item))
                route.append(nxt)
                remaining.remove(nxt)
            for index, item in enumerate(route):
                item["time_slot"] = _time_slot_for_index(index)
                distance = _distance_between_places(route[index - 1], item) if index > 0 else None
                if distance is not None and distance < 9999:
                    item["distance_from_previous_km"] = round(distance, 1)
                    # Approximate transfer allowance: a modest road detour and
                    # 20 km/h urban average, rounded to five minutes.
                    item["estimated_travel_minutes"] = max(20, int((10 + distance * 3.9 + 4) // 5 * 5))
                else:
                    item["distance_from_previous_km"] = None
                    item["estimated_travel_minutes"] = None
            activities = route + [item for item in activities if item.get("type") != "real_place"]

        final_activities = activities[:4]
        present_interests = list(dict.fromkeys(
            item.get("interest_match") for item in final_activities if item.get("interest_match")
        ))
        primary = present_interests[0] if present_interests else normalised[day_index % len(normalised)]
        secondary = [item for item in present_interests if item != primary]
        itinerary.append({
            "day": day_index + 1,
            "day_title": _day_title(primary, secondary, final_activities, destination),
            "theme": "Mixed-interest travel day",
            "secondary_themes": [item.replace("_", " ").title() for item in secondary],
            "requested_interests": [item.replace("_", " ").title() for item in normalised],
            "destination": destination,
            "budget_level": budget_level,
            "activities": final_activities,
            "guide_sections": [_guide_section(item) for item in final_activities],
            "availability_note": (
                "No suitable named places were found for the selected interests. "
                "Try another nearby destination or fewer interests, or check provider/API configuration."
                if not final_activities else ""
            ),
        })

    return itinerary


def _build_day_schedule(
    activities: list[dict], day_number: int, destination: str,
    budget_level: str = "moderate",
) -> list[dict]:
    """Create a practical day timeline around sightseeing, meals and one rest break.

    Times are planning estimates, not verified opening hours. This is a
    deterministic constraint-based schedule; it does not claim to predict
    live availability.
    """
    meal_costs = {
        "budget": {"breakfast": 120, "lunch": 200, "dinner": 250},
        "moderate": {"breakfast": 180, "lunch": 300, "dinner": 350},
        "premium": {"breakfast": 300, "lunch": 500, "dinner": 600},
    }.get(budget_level, {"breakfast": 180, "lunch": 300, "dinner": 350})
    events = [
        {"start": "7:30 AM", "end": "8:15 AM", "kind": "meal", "title": "Breakfast",
         "estimated_cost_inr": meal_costs["breakfast"],
         "description": _local_meal_description(destination, "breakfast")},
    ]
    slots = [
        ("8:45 AM", "10:15 AM"),
        ("10:45 AM", "12:15 PM"),
        ("2:45 PM", "4:15 PM"),
        ("4:45 PM", "6:15 PM"),
    ]
    usable = [a for a in activities if isinstance(a, dict)]
    # Food interest shapes the three meal recommendations. Restaurants do not
    # take an afternoon sightseeing slot; use named attractions there instead.
    usable = [
        activity for activity in usable
        if str(activity.get("interest_match") or "").lower() != "food"
        and str(activity.get("category") or "").lower() not in {"restaurant", "cafe", "food"}
    ]
    for index, activity in enumerate(usable[:4]):
        category = str(activity.get("category") or "Attraction")
        slot_index = index
        if slot_index >= len(slots):
            break
        start, end = slots[slot_index]
        events.append({
            "start": start,
            "end": end,
            "kind": "visit",
            "title": str(activity.get("name") or "Explore local attraction"),
            "description": str(activity.get("description") or
                f"Explore {activity.get('name') or 'this attraction'}; allow time for local travel."),
            "place_name": activity.get("name"),
            "category": category,
            "estimated_cost_inr": int(activity.get("estimated_cost_inr", 0) or 0),
            "source": activity.get("source"),
            "latitude": activity.get("latitude"),
            "longitude": activity.get("longitude"),
            "distance_from_previous_km": activity.get("distance_from_previous_km"),
            "estimated_travel_minutes": activity.get("estimated_travel_minutes"),
        })
        # Lunch is inserted after the second morning visit.
        if index == 1:
            events.append({
                "start": "12:45 PM", "end": "1:30 PM", "kind": "meal",
                "title": "Lunch", "estimated_cost_inr": meal_costs["lunch"],
                "description": _local_meal_description(destination, "lunch") + " This is intentionally spaced after morning sightseeing.",
            })
            events.append({
                "start": "1:30 PM", "end": "2:15 PM", "kind": "rest",
                "title": "Short rest and refresh",
                "description": "Take one main break, hydrate and recharge before afternoon sightseeing.",
            })
    # Ensure meals and break are present even when fewer than two real places
    # were found. These are clearly labelled as suggestions, not verified venues.
    if not any(e["title"] == "Lunch" for e in events):
        events.extend([
            {"start": "12:45 PM", "end": "1:30 PM", "kind": "meal", "title": "Lunch",
             "estimated_cost_inr": meal_costs["lunch"],
             "description": _local_meal_description(destination, "lunch")},
            {"start": "1:30 PM", "end": "2:15 PM", "kind": "rest", "title": "Short rest and refresh",
             "description": "Take one main break before afternoon sightseeing."},
        ])
    events.append({
        "start": "7:45 PM", "end": "8:45 PM", "kind": "meal", "title": "Dinner",
        "estimated_cost_inr": meal_costs["dinner"],
        "description": _local_meal_description(destination, "dinner") + " Confirm current prices.",
    })
    # Chronological order is based on the fixed template order.
    order = {"7:30 AM": 0, "8:45 AM": 1, "10:45 AM": 2, "12:45 PM": 3,
             "1:30 PM": 4, "2:45 PM": 5, "4:45 PM": 6, "7:45 PM": 7}
    events.sort(key=lambda event: order.get(event["start"], 99))
    return events


def _build_planner_quality_report(itinerary: list[dict], requested_days: int, budget: float) -> dict:
    """Summarise itinerary coverage and activity estimates without overstating cost accuracy.

    The current MVP estimates activity costs only. It does not have dependable
    live quotes for transport, accommodation, meals, or admission tickets, so
    this report must never claim that the complete trip fits the budget.
    """
    day_numbers = {
        day.get("day") for day in itinerary
        if isinstance(day, dict) and day.get("day") is not None
    }
    days_with_activities = sum(
        1 for day in itinerary
        if isinstance(day, dict) and bool(day.get("activities"))
    )
    days_without_activities = [
        day.get("day", index + 1)
        for index, day in enumerate(itinerary)
        if isinstance(day, dict) and not day.get("activities")
    ]
    activity_estimate = sum(
        max(0, int(activity.get("estimated_cost_inr", 0) or 0))
        for day in itinerary if isinstance(day, dict)
        for activity in (day.get("activities") or [])
        if isinstance(activity, dict)
    )
    requested_days_covered = len(day_numbers) >= max(0, int(requested_days))
    warnings = []
    if not requested_days_covered:
        warnings.append("The itinerary does not contain every requested day.")
    if days_without_activities:
        warnings.append(
            "No verified activities were found for day(s): "
            + ", ".join(str(day) for day in days_without_activities)
            + ". Try another destination or broaden the selected interests."
        )
    if activity_estimate > max(0, int(budget or 0)):
        warnings.append(
            "Estimated activity costs alone exceed the supplied trip budget; "
            "transport, accommodation and other costs are not included."
        )

    return {
        "requested_days": max(0, int(requested_days)),
        "days_returned": len(day_numbers),
        "days_with_activities": days_with_activities,
        "days_without_activities": days_without_activities,
        "all_requested_days_returned": requested_days_covered,
        "estimated_activity_cost_inr": activity_estimate,
        "budget_inr": max(0, int(budget or 0)),
        "budget_scope": "activity_estimates_only",
        "complete_trip_budget_verified": False,
        "warnings": warnings,
        "budget_note": (
            "Activity costs are prototype estimates only. Transport, accommodation, "
            "meals, admission fees and live prices are not fully verified; this is "
            "not a confirmed total-trip cost."
        ),
    }


def _fit_itinerary_estimates_to_budget(itinerary: list[dict], budget: float) -> bool:
    """Scale displayed day estimates so their total stays within the trip budget."""
    if not itinerary:
        return False
    total_limit = max(0, int(budget or 0))
    base, remainder = divmod(total_limit, len(itinerary))
    adjusted = False

    def scale_group(events: list[dict], cap: int) -> None:
        costs = [max(0, int(event.get("estimated_cost_inr", 0) or 0)) for event in events]
        original_total = sum(costs)
        if original_total <= cap:
            return
        if cap <= 0 or original_total == 0:
            for event in events:
                event["estimated_cost_inr"] = 0
            return
        exact = [cost * cap / original_total for cost in costs]
        scaled = [int(value) for value in exact]
        leftover = cap - sum(scaled)
        order = sorted(range(len(events)), key=lambda i: exact[i] - scaled[i], reverse=True)
        for index in order[:leftover]:
            scaled[index] += 1
        for event, cost in zip(events, scaled):
            event["estimated_cost_inr"] = cost

    for index, day in enumerate(itinerary):
        day_cap = base + (1 if index < remainder else 0)
        schedule = day.get("schedule", [])
        if not isinstance(schedule, list):
            continue
        if sum(max(0, int(event.get("estimated_cost_inr", 0) or 0)) for event in schedule) > day_cap:
            adjusted = True
        meals = [event for event in schedule if event.get("kind") == "meal"]
        visits = [event for event in schedule if event.get("kind") != "meal"]
        meal_total = sum(max(0, int(event.get("estimated_cost_inr", 0) or 0)) for event in meals)
        if meal_total > day_cap:
            scale_group(meals, day_cap)
            scale_group(visits, 0)
        else:
            scale_group(visits, day_cap - meal_total)

        costs_by_name = {
            str(event.get("place_name")): int(event.get("estimated_cost_inr", 0) or 0)
            for event in schedule if event.get("place_name")
        }
        for activity in day.get("activities", []):
            if activity.get("name") in costs_by_name:
                activity["estimated_cost_inr"] = costs_by_name[activity["name"]]
        for section in day.get("guide_sections", []):
            if section.get("title") in costs_by_name:
                section["budget_inr"] = costs_by_name[section["title"]]
    return adjusted


def generate_personalized_itinerary(
    destination: str,
    days: int,
    interests: list[str],
    budget: float,
) -> dict:
    """
    Universal location-aware tourism planner.

    Any destination can be supplied. Real places are retrieved from
    OpenStreetMap, strictly matched to the user's interests, ranked
    with local-food preference, de-duplicated, and distributed across
    days with compatible multi-interest balancing.
    """

    location = _geocode_destination(destination)

    # Food is handled by the three scheduled meals. When food is selected,
    # include named sightseeing places so the non-meal parts of the day still
    # feature attractions instead of restaurants.
    supplied_interests = [
        _normalise_interest(item) for item in interests
        if item and item.strip() and _normalise_interest(item) != "food"
    ]
    supported_interests = {
        "sightseeing", "culture", "nature", "beaches", "temples", "adventure",
        "history", "shopping", "nightlife",
    }
    activity_interests = [item for item in supplied_interests if item in supported_interests]
    has_food_interest = any(_normalise_interest(item) == "food" for item in interests)
    if has_food_interest and "sightseeing" not in activity_interests:
        activity_interests.append("sightseeing")
    if not activity_interests:
        activity_interests = _default_destination_interests(destination)
    interest_order = {item: index for index, item in enumerate(activity_interests)}
    activity_interests.sort(key=lambda item: (item != "temples", interest_order[item]))

    places = []

    if location:
        places = _get_places(
            latitude=location["latitude"],
            longitude=location["longitude"],
            interests=activity_interests,
            destination=destination,
        )

    curated_places = _curated_places_for_destination(destination)
    if curated_places:
        # Keep live results, but add dependable named places for covered
        # destinations so the final plan never falls back to generic labels.
        places = curated_places + places

    destination_lat = location["latitude"] if location else None
    destination_lon = location["longitude"] if location else None

    # Select real places once, then group those same places geographically
    # before daily theme planning. This makes geographic grouping part of the
    # main Trip Planner generation pipeline.
    selected_places = _select_best_places(
        places=places,
        interests=activity_interests,
        destination_lat=destination_lat,
        destination_lon=destination_lon,
        days=days,
    )

    geographic_groups = _group_places_by_day(
        places=selected_places,
        days=days,
        destination_lat=destination_lat,
        destination_lon=destination_lon,
    )

    itinerary = _create_daily_plan(
        destination=destination,
        days=days,
        interests=activity_interests,
        budget=budget,
        places=places,
        destination_lat=destination_lat,
        destination_lon=destination_lon,
        selected_places=selected_places,
        geographic_groups=geographic_groups,
    )
    requested_labels = list(dict.fromkeys(
        _normalise_interest(item).replace("_", " ").title()
        for item in interests if item and item.strip()
    ))
    if not requested_labels:
        requested_labels = [item.replace("_", " ").title() for item in activity_interests]
    for day in itinerary:
        day["requested_interests"] = requested_labels
    for day in itinerary:
        day["schedule"] = _build_day_schedule(
            day.get("activities", []), day.get("day", 1), destination,
            day.get("budget_level", "moderate")
        )
    budget_estimates_adjusted = _fit_itinerary_estimates_to_budget(itinerary, budget)
    for day in itinerary:
        day["estimated_day_cost_inr"] = sum(
            max(0, int(event.get("estimated_cost_inr", 0) or 0))
            for event in day["schedule"]
        )
    estimated_trip_cost = sum(day["estimated_day_cost_inr"] for day in itinerary)
    quality_report = _build_planner_quality_report(itinerary, days, budget)

    return {
        "destination": destination,
        "location": location,
        "days": days,
        "budget": budget,
        "estimated_trip_cost_inr": estimated_trip_cost,
        "budget_estimates_adjusted": budget_estimates_adjusted,
        "interests": interests,
        "planner_version": "V13",
        "planning_method": {
            "type": "mixed_interest_constraint_based_recommendation_and_scheduling",
            "machine_learning_required": False,
            "reason": (
                "The current project does not contain a sufficiently labelled history "
                "of traveller choices or visit durations to train and validate a reliable "
                "machine-learning model. The planner uses explainable ranking and schedule constraints."
            ),
            "ranking_signals": [
                "selected-interest compatibility",
                "place quality and category validation",
                "distance from destination and nearby-place grouping",
                "duplicate-place avoidance",
                "budget-aware activity estimates",
            ],
            "schedule_constraints": [
                "breakfast in the morning",
                "sightseeing between breakfast and lunch",
                "lunch around midday",
                "one main rest break",
                "afternoon sightseeing",
                "dinner in the evening",
            ],
        },
        "quality_controls": {
            "strict_beach_validation": True,
            "local_food_priority": True,
            "max_distance_filters": True,
            "non_tourist_facility_filter": True,
            "geographic_diversity": True,
            "day_schedule_timeline": True,
            "mixed_interest_coverage_each_day": True,
            "three_meals_and_one_main_break": True,
            "constraint_based_scheduling": True,
        },
        "provider_status": {
            "geoapify_configured": bool(
                os.getenv("GEOAPIFY_API_KEY", "").strip()
            ),
            "geoapify_used": any(
                place.get("source") == "Geoapify" for place in places
            ),
            "osm_used": any(
                place.get("source") == "OpenStreetMap" for place in places
            ),
            "generic_fallback_enabled": (
                os.getenv("PLANNER_ALLOW_GENERIC_FALLBACK", "false").strip().lower()
                in {"1", "true", "yes", "on"}
            ),
        },
        "data_source": (
            "Geoapify + interest-aware recommendation + geographic grouping + constraint-based daily scheduling"
            if any(place.get("source") == "Geoapify" for place in places) and not curated_places
            else "Geoapify + curated local recommendations + OpenStreetMap fallback + constraint-based daily scheduling"
            if any(place.get("source") == "Geoapify" for place in places) and curated_places
            else "OpenStreetMap + interest-aware recommendation + geographic grouping + constraint-based daily scheduling"
            if places and not curated_places
            else "Curated local recommendations + OpenStreetMap places + constraint-based daily scheduling"
        ),
        "real_places_found": len(places),
        "selected_real_places": sum(
            1
            for day in itinerary
            for activity in day["activities"]
            if activity["type"] == "real_place"
        ),
        "quality_report": quality_report,
        "itinerary": itinerary,
    }


@router.post("/itineraries/preview")
def preview_itinerary(request: PlannerRequest):
    """Generate an itinerary for the public planner without saving a trip.

    Saving a trip remains protected by the authenticated ``/itineraries``
    route below.  The landing-page planner uses this preview so visitors can
    see a plan immediately, before the project has a login screen.
    """
    return generate_personalized_itinerary(
        destination=request.destination.strip(),
        days=request.days,
        interests=request.interests,
        budget=request.budget,
    )


@router.post("/itineraries")
def create_itinerary(
    request: PlannerRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    user = get_user_by_email(db, current_user["sub"])

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    if not request.destination or not request.destination.strip():
        raise HTTPException(
            status_code=400,
            detail="Destination cannot be empty",
        )

    if request.days <= 0:
        raise HTTPException(
            status_code=400,
            detail="Days must be greater than 0",
        )

    if request.budget < 0:
        raise HTTPException(
            status_code=400,
            detail="Budget cannot be negative",
        )

    result = generate_personalized_itinerary(
        destination=request.destination.strip(),
        days=request.days,
        interests=request.interests,
        budget=request.budget,
    )

    itinerary = result["itinerary"]

    trip = Trip(
        user_id=user.id,
        destination=request.destination.strip(),
        days=request.days,
        budget=request.budget,
        interests=json.dumps(request.interests),
        itinerary=json.dumps(itinerary),
    )

    db.add(trip)
    db.commit()
    db.refresh(trip)

    return {
        "id": trip.id,
        "user_id": trip.user_id,
        "destination": trip.destination,
        "days": trip.days,
        "budget": trip.budget,
        "interests": request.interests,
        "location": result["location"],
        "planner_version": result["planner_version"],
        "data_source": result["data_source"],
        "real_places_found": result["real_places_found"],
        "selected_real_places": result["selected_real_places"],
        "itinerary": itinerary,
        "created_at": trip.created_at,
    }
