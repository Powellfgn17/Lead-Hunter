"""
Serper API tool — Google Search results in JSON.
Used by Agent 1 (Searcher) to find businesses without websites.
"""

import time
import random
import json
from typing import Any

import httpx
from crewai.tools import tool
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import settings


# ─── Mock Data ─────────────────────────────────────────────

MOCK_RESULTS = {
    "organic": [
        {
            "title": "Joe's Barbershop - Charlotte NC",
            "link": "https://maps.google.com/maps?cid=12345",
            "snippet": "Traditional barbershop in uptown Charlotte. Walk-ins welcome. No website listed.",
            "position": 1,
        },
        {
            "title": "Mike's Auto Repair",
            "link": "https://www.yelp.com/biz/mikes-auto-repair-charlotte",
            "snippet": "Trusted auto repair shop. 4.5 stars. 87 reviews.",
            "position": 2,
        },
        {
            "title": "Elite Cuts Barber",
            "link": "https://maps.google.com/maps?cid=67890",
            "snippet": "Premium haircuts and grooming. Appointments and walk-ins.",
            "position": 3,
        },
    ],
    "places": [
        {
            "title": "Joe's Barbershop",
            "address": "123 Main St, Charlotte, NC 28202",
            "cid": "12345",
            "rating": 4.6,
            "reviews": 52,
            "phone": "+1 704-555-0101",
            "website": None,
        },
        {
            "title": "Smooth Fades Studio",
            "address": "456 Trade St, Charlotte, NC 28202",
            "cid": "11111",
            "rating": 4.8,
            "reviews": 128,
            "phone": "+1 704-555-0202",
            "website": None,
        },
        {
            "title": "Classic Cuts",
            "address": "789 Church St, Charlotte, NC 28202",
            "cid": "22222",
            "rating": 4.2,
            "reviews": 34,
            "phone": "+1 704-555-0303",
            "website": "https://classiccuts.com",
        },
    ],
}


# ─── Real API Implementation ──────────────────────────────

@retry(
    stop=stop_after_attempt(settings.max_retries),
    wait=wait_exponential(multiplier=1, min=2, max=30),
)
def _call_serper(query: str, search_type: str = "search") -> dict:
    """Make a real Serper API call with retry logic."""
    url = f"https://google.serper.dev/{search_type}"
    headers = {
        "X-API-KEY": settings.serper_api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "q": query,
        "num": 20,  # Get more results for better coverage
    }

    with httpx.Client(timeout=30) as client:
        response = client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()


# ─── CrewAI Tool ───────────────────────────────────────────

@tool("Google Search")
def search_google(query: str) -> str:
    """
    Search Google for businesses using Serper API.
    Input: A search query string like "barbershop Charlotte NC no website".
    Returns: JSON string with organic results and places data.
    """
    if settings.is_mock:
        # Add slight delay even in mock mode to simulate real behavior
        time.sleep(0.3)
        result = {
            "query": query,
            "mock": True,
            "organic": MOCK_RESULTS["organic"],
            "places": MOCK_RESULTS["places"],
        }
        return json.dumps(result, indent=2)

    # Rate limiting with jitter
    delay = settings.delay_between_requests + random.uniform(
        -settings.delay_jitter, settings.delay_jitter
    )
    time.sleep(max(0.5, delay))

    try:
        data = _call_serper(query)
        result = {
            "query": query,
            "mock": False,
            "organic": data.get("organic", []),
            "places": data.get("places", []),
            "knowledge_graph": data.get("knowledgeGraph", {}),
        }
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e), "query": query})
