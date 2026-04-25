"""
Google Places API tool — structured business data from Maps.
Used by Agent 1 (Searcher) to get detailed place info.
"""

import time
import random
import json

import httpx
from crewai.tools import tool
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import settings


# ─── Mock Data ─────────────────────────────────────────────

MOCK_PLACES_SEARCH = [
    {
        "place_id": "ChIJmock001",
        "name": "Joe's Barbershop",
        "formatted_address": "123 Main St, Charlotte, NC 28202",
        "rating": 4.6,
        "user_ratings_total": 52,
        "business_status": "OPERATIONAL",
        "types": ["hair_care", "point_of_interest", "establishment"],
    },
    {
        "place_id": "ChIJmock002",
        "name": "Smooth Fades Studio",
        "formatted_address": "456 Trade St, Charlotte, NC 28202",
        "rating": 4.8,
        "user_ratings_total": 128,
        "business_status": "OPERATIONAL",
        "types": ["hair_care", "point_of_interest", "establishment"],
    },
    {
        "place_id": "ChIJmock003",
        "name": "Quick Cuts Express",
        "formatted_address": "789 Elm St, Charlotte, NC 28203",
        "rating": 3.9,
        "user_ratings_total": 15,
        "business_status": "OPERATIONAL",
        "types": ["hair_care", "point_of_interest", "establishment"],
    },
    {
        "place_id": "ChIJmock004",
        "name": "The Gentleman's Corner",
        "formatted_address": "321 Oak Ave, Charlotte, NC 28204",
        "rating": 4.3,
        "user_ratings_total": 67,
        "business_status": "OPERATIONAL",
        "types": ["hair_care", "beauty_salon", "establishment"],
    },
]

MOCK_PLACE_DETAILS = {
    "ChIJmock001": {
        "place_id": "ChIJmock001",
        "name": "Joe's Barbershop",
        "formatted_address": "123 Main St, Charlotte, NC 28202",
        "formatted_phone_number": "+1 704-555-0101",
        "website": None,
        "rating": 4.6,
        "user_ratings_total": 52,
        "url": "https://maps.google.com/?cid=12345",
        "business_status": "OPERATIONAL",
        "reviews": [
            {"time": 1710000000, "rating": 5, "text": "Best barber in Charlotte!"},
            {"time": 1705000000, "rating": 4, "text": "Great cuts, fair prices."},
        ],
        "opening_hours": {"open_now": True},
    },
    "ChIJmock002": {
        "place_id": "ChIJmock002",
        "name": "Smooth Fades Studio",
        "formatted_address": "456 Trade St, Charlotte, NC 28202",
        "formatted_phone_number": "+1 704-555-0202",
        "website": None,
        "rating": 4.8,
        "user_ratings_total": 128,
        "url": "https://maps.google.com/?cid=67890",
        "business_status": "OPERATIONAL",
        "reviews": [
            {"time": 1712000000, "rating": 5, "text": "Amazing experience every time."},
        ],
        "opening_hours": {"open_now": True},
    },
    "ChIJmock003": {
        "place_id": "ChIJmock003",
        "name": "Quick Cuts Express",
        "formatted_address": "789 Elm St, Charlotte, NC 28203",
        "formatted_phone_number": "+1 704-555-0303",
        "website": "https://quickcuts.com",
        "rating": 3.9,
        "user_ratings_total": 15,
        "url": "https://maps.google.com/?cid=11111",
        "business_status": "OPERATIONAL",
        "reviews": [
            {"time": 1680000000, "rating": 3, "text": "Decent but nothing special."},
        ],
        "opening_hours": {"open_now": False},
    },
    "ChIJmock004": {
        "place_id": "ChIJmock004",
        "name": "The Gentleman's Corner",
        "formatted_address": "321 Oak Ave, Charlotte, NC 28204",
        "formatted_phone_number": "+1 704-555-0404",
        "website": None,
        "rating": 4.3,
        "user_ratings_total": 67,
        "url": "https://maps.google.com/?cid=22222",
        "business_status": "OPERATIONAL",
        "reviews": [
            {"time": 1711000000, "rating": 5, "text": "Old school vibes. Love it."},
            {"time": 1709000000, "rating": 4, "text": "Good barber, but long wait times."},
        ],
        "opening_hours": {"open_now": True},
    },
}


# ─── Google API Implementation ──────────────────────────────

PLACES_BASE_URL = "https://maps.googleapis.com/maps/api/place"


@retry(
    stop=stop_after_attempt(settings.max_retries),
    wait=wait_exponential(multiplier=1, min=2, max=30),
)
def _search_places_api(query: str) -> list[dict]:
    """Search Google Places API for businesses."""
    url = f"{PLACES_BASE_URL}/textsearch/json"
    params = {
        "query": query,
        "key": settings.google_maps_api_key,
    }

    with httpx.Client(timeout=30) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        if data.get("status") != "OK":
            raise Exception(f"Places API error: {data.get('status')} - {data.get('error_message', '')}")

        return data.get("results", [])


@retry(
    stop=stop_after_attempt(settings.max_retries),
    wait=wait_exponential(multiplier=1, min=2, max=30),
)
def _get_place_details_api(place_id: str) -> dict:
    """Get detailed info for a specific place."""
    url = f"{PLACES_BASE_URL}/details/json"
    params = {
        "place_id": place_id,
        "key": settings.google_maps_api_key,
        "fields": (
            "place_id,name,formatted_address,formatted_phone_number,"
            "website,rating,user_ratings_total,url,business_status,"
            "reviews,opening_hours,types"
        ),
    }

    with httpx.Client(timeout=30) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        return data.get("result", {})


# ─── Serper Places API Implementation ──────────────────────

SERPER_BASE_URL = "https://google.serper.dev/places"
_SERPER_CACHE = {}  # Cache to avoid calling details if we already have it


def _normalize_serper_to_google(place: dict) -> dict:
    """Normalize Serper Places payload to match Google Maps format."""
    cid = str(place.get("cid", ""))
    place_id = str(place.get("placeId", "") or cid)
    return {
        "place_id": place_id,
        "name": place.get("title", ""),
        "formatted_address": place.get("address", ""),
        "formatted_phone_number": place.get("phoneNumber", ""),
        "website": place.get("website"),
        "rating": float(place.get("rating", 0)) if place.get("rating") else 0.0,
        "user_ratings_total": int(place.get("ratingCount", 0)) if place.get("ratingCount") else 0,
        "url": place.get("link", f"https://maps.google.com/?cid={cid}" if cid else ""),
        "business_status": "OPERATIONAL",
        "types": [place.get("category", "")] if place.get("category") else [],
        "reviews": [], # Serper basic search doesn't include reviews
    }


@retry(
    stop=stop_after_attempt(settings.max_retries),
    wait=wait_exponential(multiplier=1, min=2, max=30),
)
def _search_serper_places_api(query: str) -> list[dict]:
    """Search using Serper's Places endpoint."""
    headers = {
        "X-API-KEY": settings.serper_api_key,
        "Content-Type": "application/json"
    }
    payload = {"q": query}

    with httpx.Client(timeout=30) as client:
        response = client.post(SERPER_BASE_URL, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        
        normalized_results = []
        for p in data.get("places", []):
            normalized = _normalize_serper_to_google(p)
            normalized_results.append(normalized)
            # Store in cache so we don't need to fetch details later!
            if normalized["place_id"]:
                _SERPER_CACHE[normalized["place_id"]] = normalized
                
        return normalized_results


def _get_serper_details_api(place_id: str) -> dict:
    """Return place details from the Serper cache."""
    # Since search_places already gets all the info we need (website, rating, phone),
    # we just return it from our cache! Cost: 0 credit, 0 ms.
    return _SERPER_CACHE.get(str(place_id), {"error": "Place not found in cache"})


# ─── CrewAI Tools ──────────────────────────────────────────

@tool("Google Places Search")
def search_places(query: str) -> str:
    """
    Search Google Places API for businesses matching a query.
    Input: A search query like "barbershop in Charlotte NC".
    Returns: JSON array of places with name, address, rating, reviews count.
    """
    if settings.is_mock:
        time.sleep(0.3)
        return json.dumps({
            "query": query,
            "mock": True,
            "results": MOCK_PLACES_SEARCH,
            "count": len(MOCK_PLACES_SEARCH),
        }, indent=2)

    # Rate limiting
    delay = settings.delay_between_requests + random.uniform(0, settings.delay_jitter)
    time.sleep(max(1.0, delay))

    try:
        payload = places_search_raw(query)
        return json.dumps(payload, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e), "query": query})


@tool("Google Place Details")
def get_place_details(place_id: str) -> str:
    """
    Get detailed information about a specific business from Google Places.
    Input: A Google Place ID string like "ChIJxxxxx".
    Returns: JSON with name, address, phone, website, rating, reviews, hours.
    """
    if settings.is_mock:
        time.sleep(0.2)
        details = MOCK_PLACE_DETAILS.get(place_id, {
            "place_id": place_id,
            "name": f"Mock Business {place_id[-3:]}",
            "formatted_address": "Unknown Address",
            "website": None,
            "rating": 4.0,
            "user_ratings_total": 20,
            "business_status": "OPERATIONAL",
        })
        return json.dumps({"mock": True, "result": details}, indent=2)

    # Rate limiting (mandatory delay)
    delay = settings.delay_between_requests + random.uniform(0, settings.delay_jitter)
    time.sleep(max(2.0, delay))

    try:
        payload = place_details_raw(place_id)
        return json.dumps(payload, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e), "place_id": place_id})


# ─── Raw (callable) API for tool-first pipelines ───────────

def places_search_raw(query: str) -> dict:
    """Callable version of Places search (not a CrewAI tool)."""
    if settings.is_mock:
        time.sleep(0.3)
        return {
            "query": query,
            "mock": True,
            "results": MOCK_PLACES_SEARCH,
            "count": len(MOCK_PLACES_SEARCH),
        }

    delay = settings.delay_between_requests + random.uniform(0, settings.delay_jitter)
    time.sleep(max(1.0, delay))

    if settings.data_source == "serper":
        results = _search_serper_places_api(query)
    else:
        results = _search_places_api(query)

    return {
        "query": query,
        "mock": False,
        "source": settings.data_source,
        "results": results,
        "count": len(results),
    }


def place_details_raw(place_id: str) -> dict:
    """Callable version of Place details (not a CrewAI tool)."""
    if settings.is_mock:
        time.sleep(0.2)
        details = MOCK_PLACE_DETAILS.get(place_id, {
            "place_id": place_id,
            "name": f"Mock Business {place_id[-3:]}",
            "formatted_address": "Unknown Address",
            "website": None,
            "rating": 4.0,
            "user_ratings_total": 20,
            "business_status": "OPERATIONAL",
        })
        return {"mock": True, "result": details}

    delay = settings.delay_between_requests + random.uniform(0, settings.delay_jitter)
    time.sleep(max(2.0, delay))

    if settings.data_source == "serper":
        result = _get_serper_details_api(place_id)
    else:
        result = _get_place_details_api(place_id)

    return {"mock": False, "source": settings.data_source, "result": result}
