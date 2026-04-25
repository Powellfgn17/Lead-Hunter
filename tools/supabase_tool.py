"""
Supabase client tool — upsert leads and query the database.
Used by Agent 3 (Validator) to persist qualified leads.
"""

import json
import time
from typing import Optional

from crewai.tools import tool
from config.settings import settings
from utils.lead_normalize import to_supabase_lead_dict


# ─── Mock storage (in-memory for testing) ──────────────────

_mock_db: list[dict] = []


def _mock_upsert(leads: list[dict]) -> dict:
    """Simulate upsert in memory."""
    inserted, updated = 0, 0
    for lead in leads:
        normalized = to_supabase_lead_dict(lead)
        key = (normalized.get("nom", ""), normalized.get("adresse", ""))
        existing = next(
            (i for i, l in enumerate(_mock_db)
             if (l.get("nom"), l.get("adresse")) == key),
            None
        )
        if existing is not None:
            _mock_db[existing] = normalized
            updated += 1
        else:
            _mock_db.append(normalized)
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
    """Bulk upsert leads into Supabase with conflict resolution on (nom, adresse)."""
    client = _get_client()
    errors: list[dict] = []

    payload = []
    for lead in leads:
        try:
            normalized = to_supabase_lead_dict(lead)
            # Minimal validation for conflict keys
            if not normalized.get("nom") or not normalized.get("adresse"):
                raise ValueError("Missing required fields for upsert: nom/adresse")
            payload.append(normalized)
        except Exception as e:
            errors.append({"lead": str(lead.get("name") or lead.get("nom") or "?"), "error": str(e)})

    if not payload:
        return {"upserted": 0, "errors": errors, "total_in_db": _real_count()}

    try:
        # supabase-py supports bulk upsert with on_conflict.
        # We rely on the UNIQUE(nom, adresse) constraint declared in supabase_schema.sql.
        client.table("leads").upsert(payload, on_conflict="nom,adresse").execute()
    except Exception as e:
        return {"error": str(e), "upserted": 0, "errors": errors, "total_in_db": _real_count()}

    return {
        "upserted": len(payload),
        "errors": errors,
        "total_in_db": _real_count(),
    }


def upsert_leads_raw(leads: list[dict]) -> dict:
    """Callable version of upsert (not a CrewAI tool)."""
    if not leads:
        return {"upserted": 0, "errors": [], "total_in_db": (_mock_count() if settings.is_mock else _real_count())}
    if settings.is_mock:
        time.sleep(0.3)
        result = _mock_upsert(leads)
        result["mock"] = True
        return result
    return _real_upsert(leads)


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
