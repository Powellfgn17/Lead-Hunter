"""
Lead normalization helpers.

Internal contract (preferred): name/address/city/niche/phone/maps_url.
We accept legacy French keys (nom/adresse/ville/telephone/url_maps) at the boundaries.
"""

from __future__ import annotations

from typing import Any, Dict


def normalize_lead_keys(lead: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy with canonical (english) keys populated when possible."""
    if not isinstance(lead, dict):
        return {}

    out = dict(lead)

    # Canonical identifiers
    out.setdefault("name", lead.get("nom") or lead.get("name") or "")
    out.setdefault("address", lead.get("adresse") or lead.get("address") or "")
    out.setdefault("city", lead.get("ville") or lead.get("city") or lead.get("_run_city") or "")
    out.setdefault("niche", lead.get("niche") or lead.get("_run_niche") or "")
    out.setdefault("phone", lead.get("telephone") or lead.get("phone") or "")
    out.setdefault("maps_url", lead.get("url_maps") or lead.get("maps_url") or "")

    # Website flags
    if "has_website" not in out:
        out["has_website"] = bool(lead.get("has_website", False))

    # Keep legacy keys in place (don’t delete); downstream exporters/DB mappers may use them.
    return out


def to_supabase_lead_dict(lead: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map a canonical lead dict to the Supabase schema fields.
    Accepts either english or french keys in input.
    """
    l = normalize_lead_keys(lead)
    return {
        "nom": lead.get("nom") or l.get("name", ""),
        "adresse": lead.get("adresse") or l.get("address", ""),
        "telephone": lead.get("telephone") or l.get("phone", ""),
        "email": lead.get("email", "") or "",
        "ville": lead.get("ville") or l.get("city", ""),
        "niche": lead.get("niche") or l.get("niche", ""),
        "score": lead.get("score", None),
        "url_maps": lead.get("url_maps") or l.get("maps_url", ""),
        "statut": lead.get("statut", "nouveau"),
        "has_website": bool(lead.get("has_website", False)),
        "nb_avis": lead.get("nb_avis", 0) or 0,
        "dernier_avis": lead.get("dernier_avis", "") or "",
        "reseaux_sociaux": lead.get("reseaux_sociaux", {}) or {},
        "source": lead.get("source", "agent"),
    }

