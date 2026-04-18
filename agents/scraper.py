"""
Agent 2 — Scraper
Takes raw leads from Searcher, scrapes each listing with Playwright,
extracts enriched data: phone, email, social, reviews, etc.
Only passes along leads where has_website = false is CONFIRMED.
"""

from crewai import Agent, Task

from config.settings import settings
from tools.playwright_tool import scrape_listing


def create_scraper_agent() -> Agent:
    """Create the Scraper agent with browser tools."""
    return Agent(
        role="Business Data Scraper",
        goal=(
            "Visit each business listing URL and extract detailed contact information. "
            "Confirm that the business truly has NO website. "
            "Collect phone, email, social media links, review count, and recency."
        ),
        backstory=(
            "You are a meticulous data extraction specialist. You use a real headless "
            "browser to visit Google Maps listings and business pages. You know how to "
            "find hidden contact details, social media profiles, and verify that a "
            "business genuinely lacks a website (not just missing from the listing)."
        ),
        tools=[scrape_listing],
        llm=settings.llm_model,
        verbose=True,
        allow_delegation=False,
        max_iter=15,
    )


def create_scrape_task(agent: Agent, city: str, niche: str) -> Task:
    """Create the scraping task that processes raw leads."""
    return Task(
        description=f"""
You will receive a JSON array of raw business leads from the previous agent.
For each lead in the list:

1. Use the "Scrape Business Listing" tool with the lead's maps_url and place_id
2. Extract: phone, email, social media links, review count, last review date
3. CRITICAL: Confirm has_website is still false — if scraping reveals a website URL,
   set has_website to true and EXCLUDE that lead from your output
4. Only include leads where has_website remains false after scraping

Return a JSON array of enriched leads. Each must have:
- name, address, phone, email, city ("{city}"), niche ("{niche}")
- maps_url, has_website (must be false), place_id
- nb_avis: number of reviews
- rating: average rating
- dernier_avis: when the last review was posted
- reseaux_sociaux: dict of platform→URL
- years_active: estimated years in business
- website_url: empty string (confirming no website)

IMPORTANT:
- Do NOT include any lead where a website was found
- Output ONLY the JSON array
""",
        expected_output=(
            'A JSON array of enriched leads with confirmed no website. Example:\n'
            '[{{"name": "Business", "address": "123 St", "phone": "+1 555-0000", '
            '"email": "contact@email.com", "city": "' + city + '", "niche": "' + niche + '", '
            '"maps_url": "...", "has_website": false, "nb_avis": 50, "rating": 4.5, '
            '"dernier_avis": "1 week ago", "reseaux_sociaux": {{"facebook": "..."}}, '
            '"years_active": 3.0, "website_url": "", "place_id": "ChIJ..."}}]'
        ),
        agent=agent,
    )
