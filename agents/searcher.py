"""
Agent 1 — Searcher
Receives city + niche, searches Google and Places API,
identifies businesses without websites, returns raw lead list.
"""

from crewai import Agent, Task

from config.settings import settings
from tools.serper_tool import search_google
from tools.places_tool import search_places, get_place_details


def create_searcher_agent() -> Agent:
    """Create the Searcher agent with search tools."""
    return Agent(
        role="Lead Researcher",
        goal=(
            "Find local businesses in a given city and niche that do NOT have a website. "
            "Use Google Search and Google Places API to identify potential leads. "
            "Focus on businesses that appear active but lack an online presence."
        ),
        backstory=(
            "You are an expert business researcher specializing in identifying "
            "local SMBs that could benefit from a web presence. You know how to "
            "craft effective search queries and interpret Google Maps/Places data "
            "to find businesses without websites."
        ),
        tools=[search_google, search_places, get_place_details],
        llm=settings.llm_model,
        verbose=True,
        allow_delegation=False,
        max_iter=10,
    )


def create_search_task(agent: Agent, city: str, niche: str) -> Task:
    """Create the search task for a specific city and niche."""
    return Task(
        description=f"""
Search for "{niche}" businesses in "{city}" that do NOT have a website.

Follow these steps:
1. Use Google Search with query: "{niche} in {city} -site:*.com"
2. Use Google Places Search with query: "{niche} in {city}"
3. For each result from Places, use Place Details to check if website field is null/empty
4. ONLY include businesses where website is null, empty, or missing
5. Skip any business that has a website URL in their listing

Return a JSON array of raw leads. Each lead must have:
- name: business name
- maps_url: Google Maps URL
- address: full address
- city: "{city}"
- niche: "{niche}"
- has_website: false (only include if false)
- phone: phone number if available
- place_id: Google Place ID

IMPORTANT: Output ONLY the JSON array, no additional text.
""",
        expected_output=(
            'A JSON array of business objects without websites. Example:\n'
            '[{{"name": "Business Name", "maps_url": "https://maps.google.com/...", '
            '"address": "123 Main St", "city": "' + city + '", "niche": "' + niche + '", '
            '"has_website": false, "phone": "+1 555-0000", "place_id": "ChIJ..."}}]'
        ),
        agent=agent,
    )
