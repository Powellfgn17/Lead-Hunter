"""
Pydantic models for strict JSON communication between agents.
Each stage of the pipeline has its own model to enforce data contracts.
"""

from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class RawLead(BaseModel):
    """Output of Agent 1 (Searcher) — minimal info from search results."""

    name: str = Field(..., description="Business name")
    maps_url: str = Field(default="", description="Google Maps URL")
    address: str = Field(default="", description="Full address")
    city: str = Field(..., description="City searched")
    niche: str = Field(..., description="Niche searched")
    has_website: bool = Field(default=False, description="Whether a website was found in listing")
    phone: str = Field(default="", description="Phone number if available from search")
    place_id: str = Field(default="", description="Google Place ID for API lookups")

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Business name cannot be empty")
        return v.strip()


class EnrichedLead(BaseModel):
    """Output of Agent 2 (Scraper) — enriched with scraped data."""

    name: str = Field(..., description="Business name")
    address: str = Field(default="", description="Full address")
    phone: str = Field(default="", description="Phone number")
    email: str = Field(default="", description="Email address if found")
    city: str = Field(..., description="City")
    niche: str = Field(..., description="Niche")
    maps_url: str = Field(default="", description="Google Maps URL")
    has_website: bool = Field(default=False, description="Confirmed website absence")
    website_url: str = Field(default="", description="Website URL if found (should be empty for good leads)")
    nb_avis: int = Field(default=0, description="Number of reviews")
    rating: float = Field(default=0.0, description="Average rating")
    dernier_avis: str = Field(default="", description="Date or text of most recent review")
    reseaux_sociaux: dict = Field(default_factory=dict, description="Social media links found")
    place_id: str = Field(default="", description="Google Place ID")
    years_active: float = Field(default=0.0, description="Estimated years in business")


class ScoredLead(BaseModel):
    """Output of Agent 3 (Validator) — validated and scored."""

    name: str
    address: str
    phone: str = ""
    email: str = ""
    city: str
    niche: str
    maps_url: str = ""
    has_website: bool = False
    nb_avis: int = 0
    dernier_avis: str = ""
    reseaux_sociaux: dict = Field(default_factory=dict)
    score: int = Field(..., ge=1, le=10, description="Lead quality score 1-10")
    score_breakdown: dict = Field(
        default_factory=dict,
        description="Detailed scoring breakdown by criteria"
    )
    statut: str = Field(default="nouveau", description="Lead status")
    rejection_reason: str = Field(default="", description="Why lead was rejected if score < 5")

    @field_validator("score")
    @classmethod
    def score_in_range(cls, v: int) -> int:
        if not 1 <= v <= 10:
            raise ValueError(f"Score must be between 1 and 10, got {v}")
        return v


class Lead(BaseModel):
    """Final lead model matching the Supabase schema — used for DB operations."""

    nom: str
    adresse: str
    telephone: str = ""
    email: str = ""
    ville: str
    niche: str
    score: int = Field(..., ge=1, le=10)
    url_maps: str = ""
    statut: str = "nouveau"
    has_website: bool = False
    nb_avis: int = 0
    dernier_avis: str = ""
    reseaux_sociaux: dict = Field(default_factory=dict)

    @classmethod
    def from_scored(cls, scored: ScoredLead) -> Lead:
        """Convert a ScoredLead to a Lead for database insertion."""
        return cls(
            nom=scored.name,
            adresse=scored.address,
            telephone=scored.phone,
            email=scored.email,
            ville=scored.city,
            niche=scored.niche,
            score=scored.score,
            url_maps=scored.maps_url,
            statut=scored.statut,
            has_website=scored.has_website,
            nb_avis=scored.nb_avis,
            dernier_avis=scored.dernier_avis,
            reseaux_sociaux=scored.reseaux_sociaux,
        )

    def to_supabase_dict(self) -> dict:
        """Convert to dict for Supabase upsert, with JSON-safe values."""
        data = self.model_dump()
        # Ensure reseaux_sociaux is JSON serializable
        if isinstance(data.get("reseaux_sociaux"), dict):
            import json
            data["reseaux_sociaux"] = json.dumps(data["reseaux_sociaux"])
        return data


class LeadList(BaseModel):
    """Wrapper for lists of leads at each stage — used as agent output."""

    leads: list[RawLead] | list[EnrichedLead] | list[ScoredLead] = Field(
        default_factory=list
    )
    city: str = ""
    niche: str = ""
    total: int = 0
    filtered_out: int = 0

    def model_post_init(self, __context) -> None:
        self.total = len(self.leads)
