"""
Agent 3 — Validator
Receives enriched leads, validates activity, confirms no website,
scores each lead 1-10, eliminates weak leads, saves to Supabase.
"""

from crewai import Agent, Task

from config.settings import settings
from tools.supabase_tool import upsert_leads, get_lead_count


SCORING_CRITERIA = """
Score each lead from 1 to 10 using these criteria:

+2 points: Recent reviews (last review within 6 months)
+1 point:  More than 10 reviews total
+1 point:  Phone number available
+2 points: Email address available
+1 point:  Present on social media (Facebook, Yelp, Instagram, etc.)
+2 points: NO website confirmed (double-verified by Scraper)
+1 point:  Business active for more than 1 year

Maximum score: 10
Minimum score to keep: 5 (eliminate anything below)
"""


def create_validator_agent() -> Agent:
    """Create the Validator agent with database tools."""
    return Agent(
        role="Lead Quality Validator",
        goal=(
            "Validate each enriched lead, confirm the business is active, "
            "confirm website absence, score each lead from 1-10, "
            "eliminate weak leads (score < 5), and save qualified leads to Supabase."
        ),
        backstory=(
            "You are a quality assurance specialist for B2B leads. You rigorously "
            "validate each lead against strict criteria before it enters the database. "
            "You understand that bad leads waste sales time, so you only pass through "
            "high-quality, verified leads with detailed scoring breakdowns."
        ),
        tools=[upsert_leads, get_lead_count],
        llm=settings.llm_model,
        verbose=True,
        allow_delegation=False,
        max_iter=10,
    )


def create_validate_task(agent: Agent, city: str, niche: str) -> Task:
    """Create the validation task that scores and saves leads."""
    return Task(
        description=f"""
You will receive a JSON array of enriched business leads from the Scraper agent.
For each lead:

1. VALIDATE the business is active:
   - Must have reviews (nb_avis > 0)
   - Last review should be relatively recent (dernier_avis)
   - If no signs of activity, reject with reason

2. CONFIRM no website:
   - has_website must be false
   - website_url must be empty
   - If website found, reject immediately

3. SCORE using these criteria:
{SCORING_CRITERIA}

4. FILTER: Remove any lead with score < 5
   - For rejected leads, note the rejection_reason

5. SAVE qualified leads to database using the "Save Leads to Database" tool.
   Convert each qualified lead to this format for the database:
   {{
     "nom": lead name,
     "adresse": lead address,
     "telephone": lead phone,
     "email": lead email,
     "ville": "{city}",
     "niche": "{niche}",
     "score": calculated score,
     "url_maps": maps URL,
     "statut": "nouveau",
     "has_website": false,
     "nb_avis": review count,
     "dernier_avis": last review info,
     "reseaux_sociaux": social media dict
   }}

   Pass the array as a JSON string to the tool.

6. After saving, use "Get Lead Count" to verify the total.

Return a JSON summary:
{{
  "city": "{city}",
  "niche": "{niche}",
  "total_received": number of leads received,
  "total_qualified": number that passed (score >= 5),
  "total_rejected": number rejected,
  "saved_to_db": number saved,
  "qualified_leads": [array of scored leads with score_breakdown],
  "rejected_leads": [array of rejected leads with rejection_reason]
}}

IMPORTANT: Output ONLY the JSON summary.
""",
        expected_output=(
            'A JSON summary object with qualified/rejected counts and lead arrays. '
            'All qualified leads must have score >= 5 and be saved to database.'
        ),
        agent=agent,
    )
