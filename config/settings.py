"""
Centralized configuration for the Lead Hunting Agent.
Loads environment variables and config files.
"""

import json
import os
from pathlib import Path
from dataclasses import dataclass, field
from dotenv import load_dotenv

# Load .env from project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


@dataclass
class Settings:
    """Application-wide settings loaded from environment and config files."""

    # --- Mode ---
    mode: str = os.getenv("MODE", "mock")
    data_source: str = os.getenv("DATA_SOURCE", "serper")  # serper or google

    # --- API Keys ---
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    serper_api_key: str = os.getenv("SERPER_API_KEY", "")
    google_maps_api_key: str = os.getenv("GOOGLE_MAPS_API_KEY", "")
    supabase_url: str = os.getenv("SUPABASE_URL", "")
    supabase_key: str = os.getenv("SUPABASE_KEY", "")

    # --- LLM Config ---
    llm_model: str = "groq/llama-3.3-70b-versatile"
    llm_temperature: float = 0.1  # Low temp for deterministic outputs
    llm_max_tokens: int = 4096

    # --- Rate Limiting ---
    delay_between_requests: float = 2.0  # seconds between API calls
    delay_jitter: float = 1.0  # random jitter ±1s to avoid detection
    max_retries: int = 3
    retry_backoff: float = 5.0  # seconds base backoff

    # --- Scoring ---
    min_lead_score: int = 5  # Leads below this are eliminated
    max_lead_score: int = 10

    # --- Playwright ---
    headless: bool = True
    browser_timeout: int = 30000  # ms
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    # --- Paths ---
    project_root: Path = field(default_factory=lambda: _PROJECT_ROOT)

    @property
    def is_mock(self) -> bool:
        return self.mode.lower() == "mock"

    @property
    def cities(self) -> list[dict]:
        """Load cities from config file."""
        path = self.project_root / "config" / "cities.json"
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    @property
    def niches(self) -> list[str]:
        """Load niches from config file."""
        path = self.project_root / "config" / "niches.json"
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def validate(self) -> list[str]:
        """Check that required keys are set. Returns list of missing keys."""
        if self.is_mock:
            return []

        missing = []
        if not self.groq_api_key:
            missing.append("GROQ_API_KEY")
        if not self.serper_api_key:
            missing.append("SERPER_API_KEY")
            
        if self.data_source == "google" and not self.google_maps_api_key:
            missing.append("GOOGLE_MAPS_API_KEY")

        if not self.supabase_url:
            missing.append("SUPABASE_URL")
        if not self.supabase_key:
            missing.append("SUPABASE_KEY")
        return missing


# Singleton instance
settings = Settings()
