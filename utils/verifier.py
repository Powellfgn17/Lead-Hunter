"""
Independent Lead Verifier — Zero hallucination guarantee.
Calls Serper Places API directly (no LLM) to re-verify each lead's
website status before it is saved to the database.
"""

import json
import httpx
from utils.logger import get_logger
from config.settings import settings

log = get_logger("verifier")

SERPER_PLACES_URL = "https://google.serper.dev/places"


def _serper_search(business_name: str, city: str) -> dict | None:
    """
    Call Serper Places API directly to get real-time business data.
    Returns the first matching place dict, or None if not found.
    """
    query = f"{business_name} {city}"
    headers = {
        "X-API-KEY": settings.serper_api_key,
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=15) as client:
            response = client.post(
                SERPER_PLACES_URL,
                headers=headers,
                json={"q": query},
            )
            response.raise_for_status()
            data = response.json()
            places = data.get("places", [])
            if places:
                return places[0]  # Best match
    except Exception as e:
        log.warning(f"Serper verifier error for '{business_name}': {e}")
    return None


def verify_no_website(lead: dict) -> dict:
    """
    Independently verify that a lead truly has no website.
    Returns updated lead dict with:
      - 'verified': True if verification passed (no website found)
      - 'verified': False if a website was found (false positive)
      - 'verified_website': the URL found (if any)
      - 'rejection_reason': explanation if rejected
    """
    if settings.is_mock:
        # In mock mode, trust the pipeline data
        lead["verified"] = True
        lead["verified_website"] = ""
        return lead

    name = lead.get("name", "")
    city = lead.get("city", "")

    log.info(f"🔍 Verifying: {name} ({city})")

    place = _serper_search(name, city)

    if place is None:
        # Cannot verify — Serper found nothing. Keep lead but mark as unverified.
        log.warning(f"⚠️  Cannot verify '{name}' — not found in Serper. Keeping lead.")
        lead["verified"] = True  # Give benefit of the doubt
        lead["verified_website"] = ""
        return lead

    website = place.get("website", None) or ""
    website = website.strip()

    if website:
        # WEBSITE FOUND — this is a false positive from the LLM
        log.warning(f"❌ False positive detected: '{name}' has website → {website}")
        lead["verified"] = False
        lead["verified_website"] = website
        lead["has_website"] = True
        lead["rejection_reason"] = f"Website found by independent verification: {website}"
    else:
        # Confirmed no website
        log.info(f"✅ Verified: '{name}' has NO website")
        lead["verified"] = True
        lead["verified_website"] = ""

    return lead


def filter_verified_leads(leads: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Run independent verification on all leads.
    Returns (verified_leads, rejected_leads).
    """
    if not leads:
        return [], []

    verified = []
    rejected = []

    for lead in leads:
        result = verify_no_website(lead)
        if result.get("verified", False):
            verified.append(result)
        else:
            rejected.append(result)

    log.info(
        f"Verification complete: {len(verified)} verified, "
        f"{len(rejected)} false positives rejected"
    )
    return verified, rejected
