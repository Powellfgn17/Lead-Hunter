"""
Supabase client tool — upsert leads and query the database.
Used by Agent 3 (Validator) to persist qualified leads.
"""

import json
import time
from typing import Optional

from crewai.tools import tool
from config.settings import settings


# ─── Mock storage (in-memory for testing) ──────────────────

_mock_db: list[dict] = []


def _mock_upsert(leads: list[dict]) -> dict:
    """Simulate upsert in memory."""
    inserted, updated = 0, 0
    for lead in leads:
        key = (lead.get("nom", ""), lead.get("adresse", ""))
        existing = next(
            (i for i, l in enumerate(_mock_db)
             if (l.get("nom"), l.get("adresse")) == key),
            None
        )
        if existing is not None:
            _mock_db[existing] = lead
            updated += 1
        else:
            _mock_db.append(lead)
            inserted += 1
    return {"inserted": inserted, "updated": updated, "total": len(_mock_db)}


def _mock_count(city: str = "", niche: str = "") -> int:
    """Count leads in mock DB with optional filters."""
    results = _mock_db
    if city:
        results = [l for l in results if l.get("ville", "").lower() == city.lower()]
    if niche:
        results = [l for l in results if l.get("niche", "").lower() == niche.lower()]
    return len(results)


# ─── Real Supabase client ─────────────────────────────────

def _get_client():
    """Initialize Supabase client (lazy import)."""
    from supabase import create_client
    return create_client(settings.supabase_url, settings.supabase_key)


def _real_upsert(leads: list[dict]) -> dict:
    """Upsert leads into Supabase with conflict resolution on (nom, adresse)."""
    client = _get_client()
    inserted, updated, errors = 0, 0, []

    for lead in leads:
        try:
            # Check if exists
            existing = (
                client.table("leads")
                .select("id")
                .eq("nom", lead["nom"])
                .eq("adresse", lead["adresse"])
                .execute()
            )

            if existing.data:
                # Update existing
                client.table("leads").update(lead).eq(
                    "id", existing.data[0]["id"]
                ).execute()
                updated += 1
            else:
                # Insert new
                client.table("leads").insert(lead).execute()
                inserted += 1

        except Exception as e:
            errors.append({"lead": lead.get("nom", "?"), "error": str(e)})

    return {
        "inserted": inserted,
        "updated": updated,
        "errors": errors,
        "total_in_db": _real_count(),
    }


def _real_count(city: str = "", niche: str = "") -> int:
    """Count leads in Supabase."""
    client = _get_client()
    query = client.table("leads").select("id", count="exact")
    if city:
        query = query.eq("ville", city)
    if niche:
        query = query.eq("niche", niche)
    result = query.execute()
    return result.count or 0


# ─── CrewAI Tools ──────────────────────────────────────────

@tool("Save Leads to Database")
def upsert_leads(leads_json: str) -> str:
    """
    Save validated leads to Supabase database with upsert (no duplicates).
    Input: JSON string containing an array of lead objects with fields:
           nom, adresse, telephone, email, ville, niche, score, url_maps, statut.
    Returns: JSON summary with insert/update counts.
    """
    try:
        leads = json.loads(leads_json)
        if isinstance(leads, dict):
            leads = [leads]
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Invalid JSON: {e}"})

    if not leads:
        return json.dumps({"error": "No leads provided", "inserted": 0})

    if settings.is_mock:
        time.sleep(0.3)
        result = _mock_upsert(leads)
        result["mock"] = True
        return json.dumps(result, indent=2)

    try:
        result = _real_upsert(leads)
        result["mock"] = False
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool("Get Lead Count")
def get_lead_count(city: str = "", niche: str = "") -> str:
    """
    Get the number of leads in the database, optionally filtered by city and niche.
    Input: Optional city and niche strings to filter.
    Returns: JSON with count.
    """
    if settings.is_mock:
        count = _mock_count(city, niche)
        return json.dumps({"count": count, "city": city, "niche": niche, "mock": True})

    try:
        count = _real_count(city, niche)
        return json.dumps({"count": count, "city": city, "niche": niche, "mock": False})
    except Exception as e:
        return json.dumps({"error": str(e)})
