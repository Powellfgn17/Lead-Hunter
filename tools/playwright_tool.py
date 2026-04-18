"""
Playwright browser scraping tool — headless browser for enrichment.
Used by Agent 2 (Scraper) to visit listings and extract contact info.
"""

import time
import random
import json
import re

from crewai.tools import tool
from config.settings import settings

# ─── Mock Data ─────────────────────────────────────────────

MOCK_SCRAPE = {
    "ChIJmock001": {
        "name": "Joe's Barbershop", "phone": "+1 704-555-0101",
        "email": "joe@email.com", "address": "123 Main St, Charlotte, NC 28202",
        "website": None, "nb_avis": 52, "rating": 4.6,
        "dernier_avis": "1 week ago",
        "reseaux_sociaux": {"facebook": "https://facebook.com/joesbarbershop",
                            "instagram": "https://instagram.com/joesbarbershop"},
        "years_active": 5.0, "is_active": True,
    },
    "ChIJmock002": {
        "name": "Smooth Fades Studio", "phone": "+1 704-555-0202",
        "email": "", "address": "456 Trade St, Charlotte, NC 28202",
        "website": None, "nb_avis": 128, "rating": 4.8,
        "dernier_avis": "3 days ago",
        "reseaux_sociaux": {"instagram": "https://instagram.com/smoothfades"},
        "years_active": 2.0, "is_active": True,
    },
    "ChIJmock004": {
        "name": "The Gentleman's Corner", "phone": "+1 704-555-0404",
        "email": "info@gentlemanscorner.com", "address": "321 Oak Ave, Charlotte, NC 28204",
        "website": None, "nb_avis": 67, "rating": 4.3,
        "dernier_avis": "1 month ago",
        "reseaux_sociaux": {"facebook": "https://facebook.com/gentlemanscorner",
                            "yelp": "https://yelp.com/biz/the-gentlemans-corner"},
        "years_active": 8.0, "is_active": True,
    },
}

MOCK_DEFAULT = {
    "name": "Mock Business", "phone": "+1 704-555-9999", "email": "",
    "address": "999 Mock St", "website": None, "nb_avis": 30,
    "rating": 4.0, "dernier_avis": "2 weeks ago",
    "reseaux_sociaux": {"facebook": "https://facebook.com/mock"},
    "years_active": 3.0, "is_active": True,
}


# ─── Extraction helpers ───────────────────────────────────

def _extract_emails(text: str) -> list[str]:
    pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
    found = re.findall(pattern, text)
    return [e for e in set(found) if not e.endswith((".png", ".jpg", ".gif"))]


def _extract_social(text: str, urls: list[str]) -> dict:
    combined = text + " " + " ".join(urls)
    social = {}
    for name, domain in [("facebook", "facebook.com"), ("instagram", "instagram.com"),
                          ("yelp", "yelp.com/biz"), ("tiktok", "tiktok.com/@")]:
        pat = rf"(?:https?://)?(?:www\.)?{re.escape(domain)}/[^\s\"'<>]+"
        m = re.findall(pat, combined)
        if m:
            social[name] = m[0]
    return social


# ─── Real scraping (async) ────────────────────────────────

async def _scrape_page(url: str) -> dict:
    from playwright.async_api import async_playwright
    result = {"url": url, "email": "", "phone": "", "website": None,
              "reseaux_sociaux": {}, "error": None}
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=settings.headless)
            ctx = await browser.new_context(user_agent=settings.user_agent)
            page = await ctx.new_page()
            await page.goto(url, timeout=settings.browser_timeout, wait_until="networkidle")
            await page.wait_for_timeout(2000)
            text = await page.inner_text("body")
            links = await page.evaluate(
                "() => Array.from(document.querySelectorAll('a')).map(a => a.href).filter(Boolean)"
            )
            result["email"] = next(iter(_extract_emails(text)), "")
            phones = re.findall(r"\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", text)
            result["phone"] = phones[0] if phones else ""
            result["reseaux_sociaux"] = _extract_social(text, links)
            skip = ["facebook.com", "instagram.com", "twitter.com", "yelp.com",
                    "google.com", "youtube.com", "tiktok.com", "linkedin.com"]
            own = [l for l in links if not any(d in l for d in skip)
                   and "maps." not in l and "mailto:" not in l and "tel:" not in l]
            result["website"] = own[0] if own else None
            await browser.close()
    except Exception as e:
        result["error"] = str(e)
    return result


# ─── CrewAI Tool ───────────────────────────────────────────

@tool("Scrape Business Listing")
def scrape_listing(url: str, place_id: str = "") -> str:
    """
    Scrape a business listing page using a headless browser.
    Input: URL of the listing page, and optional place_id.
    Returns: JSON with extracted business data.
    """
    if settings.is_mock:
        time.sleep(0.5)
        data = MOCK_SCRAPE.get(place_id, MOCK_DEFAULT).copy()
        data.update({"url": url, "mock": True})
        return json.dumps(data, indent=2)

    delay = settings.delay_between_requests + random.uniform(0, settings.delay_jitter * 2)
    time.sleep(max(2.0, delay))

    try:
        import asyncio
        try:
            result = asyncio.run(_scrape_page(url))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(_scrape_page(url))
            loop.close()
        result["mock"] = False
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e), "url": url})
