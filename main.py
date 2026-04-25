"""
Lead Hunting Agent — Main Orchestrator
======================================
Multi-agent system that autonomously finds local businesses without websites,
enriches their data, validates and scores them, then stores qualified leads.

Usage:
    python main.py                          # Run all cities × all niches (mock mode)
    python main.py --city "Charlotte NC" --niche "barbershop"
    python main.py --city "Lyon France" --niche "plumber" --mode production
    python main.py --list                   # Show available cities and niches
"""

import argparse
import json
import re
import sys
import time
import os
import random
from datetime import datetime
from itertools import product
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import print as rprint

from config.settings import settings
from agents.searcher import create_searcher_agent, create_search_task
from agents.scraper import create_scraper_agent, create_scrape_task
from agents.validator import create_validator_agent, create_validate_task
from utils.logger import get_logger
from utils.export import export_csv, export_excel
from utils.verifier import is_business_website
from utils.lead_normalize import normalize_lead_keys
from utils.lead_normalize import to_supabase_lead_dict

from tools.places_tool import places_search_raw, place_details_raw
from tools.playwright_tool import scrape_listing_raw
from tools.supabase_tool import upsert_leads_raw

console = Console()
log = get_logger("main")


# ─── JSON Extraction Helper ────────────────────────────────

def _extract_json(text: str):
    """
    Extract a JSON object or array from LLM output that may contain
    surrounding natural language text. Tries multiple strategies:
    1. Direct json.loads on the full text
    2. Regex extraction of JSON objects {...} or arrays [...]
    3. Returns None if nothing valid is found
    """
    if not text or not text.strip():
        return None

    raw = text.strip()

    # Strategy 1: try direct parse
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        pass

    # Strategy 2: find the largest JSON object or array in the text
    # Look for JSON objects
    best = None
    for pattern in [
        r'(\{[\s\S]*\})',   # JSON object (greedy)
        r'(\[[\s\S]*\])',   # JSON array (greedy)
    ]:
        matches = re.findall(pattern, raw)
        for match in matches:
            try:
                parsed = json.loads(match)
                # Keep the largest valid JSON found
                if best is None or len(match) > len(json.dumps(best)):
                    best = parsed
            except (json.JSONDecodeError, TypeError):
                continue

    return best


def _extract_leads_from_output(text: str) -> list[dict]:
    """
    Extract individual lead dicts from LLM output, even if the output
    is not a clean JSON summary. Looks for objects with 'nom' or 'name' keys.
    """
    parsed = _extract_json(text)
    if parsed is None:
        return []

    # If it's a summary dict with qualified_leads
    if isinstance(parsed, dict):
        leads = parsed.get("qualified_leads", [])
        if leads:
            return leads
        # Maybe it's a single lead
        if "nom" in parsed or "name" in parsed:
            return [parsed]
        return []

    # If it's an array of leads
    if isinstance(parsed, list):
        return [l for l in parsed if isinstance(l, dict)]  

    return []


# ─── CLI ───────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="🎯 Lead Hunting Agent — Find businesses without websites",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--city", type=str, help="Target city (e.g. 'Charlotte NC')")
    parser.add_argument("--niche", type=str, help="Target niche (e.g. 'barbershop')")
    parser.add_argument(
        "--mode", type=str, choices=["mock", "production"], default=None,
        help="Override MODE from .env"
    )
    parser.add_argument("--list", action="store_true", help="List available cities and niches")
    parser.add_argument(
        "--strategy",
        type=str,
        choices=["crewai", "tool-first"],
        default=None,
        help="Pipeline strategy: crewai (LLM-driven) or tool-first (deterministic, zero hallucination).",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Run all city×niche combinations (use with caution in production)"
    )
    return parser.parse_args()


def show_config_list():
    """Display available cities and niches."""
    console.print("\n[bold cyan]📍 Available Cities:[/bold cyan]")
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("City", style="white")
    table.add_column("Country", style="dim")
    for c in settings.cities:
        table.add_row(c["name"], c["country"])
    console.print(table)

    console.print("\n[bold cyan]🏷️  Available Niches:[/bold cyan]")
    for n in settings.niches:
        console.print(f"  • {n}")
    console.print()


# ─── Pipeline ─────────────────────────────────────────────

def _now_ms() -> int:
    return int(time.time() * 1000)


def _safe_json_loads(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:
        return {"error": "invalid_json", "raw": text[:5000]}


def _is_recent_review(dernier_avis: str) -> bool:
    """
    Heuristic: treat reviews within ~6 months as "recent".
    Works with typical strings like "3 days ago", "1 week ago", "2 months ago".
    """
    if not isinstance(dernier_avis, str):
        return False
    s = dernier_avis.lower().strip()
    if not s:
        return False
    if "day" in s or "days" in s or "week" in s or "weeks" in s:
        return True
    if "month" in s or "months" in s:
        # If it says e.g. "7 months ago" consider it not recent.
        m = re.search(r"(\d+)\s*month", s)
        if m:
            try:
                return int(m.group(1)) <= 6
            except ValueError:
                return False
        return True
    return False


def _score_lead_deterministic(lead: dict) -> tuple[int, dict]:
    """
    Deterministic scoring (no LLM) matching the Validator criteria.
    """
    breakdown = {}
    score = 0

    # Recent reviews
    recent = _is_recent_review(lead.get("dernier_avis", ""))
    breakdown["recent_reviews"] = 2 if recent else 0
    score += breakdown["recent_reviews"]

    # >10 reviews
    nb_avis = lead.get("nb_avis", 0) or 0
    more_10 = isinstance(nb_avis, (int, float)) and nb_avis > 10
    breakdown["more_than_10_reviews"] = 1 if more_10 else 0
    score += breakdown["more_than_10_reviews"]

    # Phone
    phone = (lead.get("phone") or lead.get("telephone") or "").strip()
    breakdown["phone_available"] = 1 if phone else 0
    score += breakdown["phone_available"]

    # Email
    email = (lead.get("email") or "").strip()
    breakdown["email_available"] = 2 if email else 0
    score += breakdown["email_available"]

    # Socials
    socials = lead.get("reseaux_sociaux", {}) or {}
    breakdown["present_on_social_media"] = 1 if isinstance(socials, dict) and len(socials) > 0 else 0
    score += breakdown["present_on_social_media"]

    # No website (must be verified true)
    verified_status = lead.get("verified_status")
    no_website = verified_status == "no_website" or lead.get("verified") is True
    breakdown["no_website"] = 2 if no_website else 0
    score += breakdown["no_website"]

    # Active > 1 year
    years_active = lead.get("years_active", 0) or 0
    active_1y = isinstance(years_active, (int, float)) and years_active >= 1.0
    breakdown["business_active_more_than_1_year"] = 1 if active_1y else 0
    score += breakdown["business_active_more_than_1_year"]

    # Clamp to [1,10]
    score = max(1, min(10, int(score)))
    return score, breakdown


def run_pipeline_tool_first(city: str, niche: str) -> dict:
    """
    ZERO HALLUCINATION / ZERO FALSE POSITIVE pipeline:
    - Fetch deterministic data via tools (Serper/Places, Playwright)
    - Filter no-website in code
    - Verify independently (Serper). If cannot verify => reject (unknown)
    - Score deterministically in code
    - Save only verified leads to DB (bulk upsert)

    Returns a single JSON-ready dict "deliverable" with status + evidence.
    """
    start_ms = _now_ms()
    evidence = {"strategy": "tool-first", "timings_ms": {}, "counts": {}}
    errors: list[dict] = []

    console.print(Panel(
        f"[bold white]🏙️  City:[/bold white] {city}\n"
        f"[bold white]🏷️  Niche:[/bold white] {niche}\n"
        f"[bold white]⚙️  Mode:[/bold white] {'🟡 MOCK' if settings.is_mock else '🟢 PRODUCTION'}\n"
        f"[bold white]🧰 Strategy:[/bold white] TOOL-FIRST (zero hallucination)",
        title="[bold cyan]🎯 Starting Lead Hunt[/bold cyan]",
        border_style="cyan",
    ))

    # 1) Places search (deterministic)
    t0 = _now_ms()
    query = f"{niche} in {city}"
    places_payload = places_search_raw(query)
    evidence["timings_ms"]["places_search"] = _now_ms() - t0
    if places_payload.get("error"):
        return {
            "city": city,
            "niche": niche,
            "status": "tool_error",
            "duration": round((_now_ms() - start_ms) / 1000, 1),
            "qualified": 0,
            "rejected": 0,
            "errors": [{"stage": "places_search", "error": places_payload.get("error"), "query": query}],
            "evidence": evidence,
            "leads": [],
        }

    results = places_payload.get("results", []) or []
    evidence["counts"]["places_results_total"] = len(results)
    evidence["counts"]["query"] = query
    evidence["counts"]["places_source"] = places_payload.get("source") or places_payload.get("mock")

    # 2) Fetch details and filter website == None/empty (in code)
    t1 = _now_ms()
    candidates: list[dict] = []
    has_site = 0
    non_business_website = 0
    details_errors = 0
    for r in results:
        place_id = str(r.get("place_id", "") or "")
        if not place_id:
            continue
        details_payload = place_details_raw(place_id)
        if details_payload.get("error"):
            details_errors += 1
            errors.append({"stage": "place_details", "place_id": place_id, "error": details_payload.get("error")})
            continue
        det = details_payload.get("result", {}) or {}
        if isinstance(det, dict) and det.get("error"):
            details_errors += 1
            errors.append({"stage": "place_details", "place_id": place_id, "error": det.get("error")})
            continue

        website = (det.get("website") or r.get("website") or "").strip()
        if is_business_website(website):
            has_site += 1
            continue
        if website:
            non_business_website += 1

        lead = {
            "name": det.get("name", ""),
            "address": det.get("formatted_address", ""),
            "phone": det.get("formatted_phone_number", "") or "",
            "city": city,
            "niche": niche,
            "maps_url": det.get("url", "") or f"https://maps.google.com/?cid={place_id}",
            "place_id": place_id,
            "has_website": False,
            "website_url": "",
            "rating": det.get("rating", 0.0) or 0.0,
            "nb_avis": det.get("user_ratings_total", 0) or 0,
            # dernier_avis/reseaux/email/years_active filled by scraping below if available
            "dernier_avis": "",
            "reseaux_sociaux": {},
            "email": "",
            "years_active": 0.0,
            "source": "tool-first",
        }
        candidates.append(lead)

    evidence["timings_ms"]["place_details_and_filter"] = _now_ms() - t1
    evidence["counts"]["places_with_website"] = has_site
    evidence["counts"]["places_with_non_business_website"] = non_business_website
    evidence["counts"]["candidates_no_website_from_places"] = len(candidates)
    evidence["counts"]["place_details_errors"] = details_errors

    if not candidates:
        return {
            "city": city,
            "niche": niche,
            "status": "no_results",
            "duration": round((_now_ms() - start_ms) / 1000, 1),
            "qualified": 0,
            "rejected": 0,
            "errors": errors,
            "evidence": evidence,
            "leads": [],
        }

    # 3) Playwright verification (source of truth)
    # Serper is discovery-only. Truth about website comes from Maps scraping.
    t2 = _now_ms()
    verified: list[dict] = []
    rejected_truth: list[dict] = []
    scrape_errors = 0
    for lead in candidates:
        maps_url = lead.get("maps_url", "")
        place_id = lead.get("place_id", "")
        scrape_payload = scrape_listing_raw(maps_url, place_id=place_id)
        if scrape_payload.get("error"):
            scrape_errors += 1
            errors.append({"stage": "scrape_listing", "place_id": place_id, "error": scrape_payload.get("error")})
            # ZERO FALSE POSITIVE rule:
            # if truth source fails, status is unknown and lead is rejected.
            lead["verified"] = False
            lead["verified_status"] = "unknown"
            lead["verified_website"] = ""
            lead["rejection_reason"] = "Playwright verification failed (unknown website status)"
            rejected_truth.append(lead)
            continue

        # Merge enrichment fields
        lead["email"] = scrape_payload.get("email", "") or lead.get("email", "")
        lead["phone"] = scrape_payload.get("phone", "") or lead.get("phone", "")
        lead["reseaux_sociaux"] = scrape_payload.get("reseaux_sociaux", {}) or {}
        lead["dernier_avis"] = scrape_payload.get("dernier_avis", "") or lead.get("dernier_avis", "")
        lead["years_active"] = scrape_payload.get("years_active", 0.0) or 0.0

        website_candidate = (scrape_payload.get("website") or "").strip()
        if is_business_website(website_candidate):
            lead["verified"] = False
            lead["verified_status"] = "has_website"
            lead["verified_website"] = website_candidate
            lead["has_website"] = True
            lead["rejection_reason"] = f"Website found by Playwright verification: {website_candidate}"
            rejected_truth.append(lead)
        else:
            lead["verified"] = True
            lead["verified_status"] = "no_website"
            lead["verified_website"] = ""
            verified.append(lead)

    evidence["timings_ms"]["scrape_listing"] = _now_ms() - t2
    evidence["counts"]["scrape_errors"] = scrape_errors

    # 4) Truth decision summary (from Playwright)
    evidence["timings_ms"]["independent_verification"] = 0
    evidence["counts"]["verified"] = len(verified)
    evidence["counts"]["rejected"] = len(rejected_truth)

    if not verified:
        return {
            "city": city,
            "niche": niche,
            "status": "no_results",
            "duration": round((_now_ms() - start_ms) / 1000, 1),
            "qualified": 0,
            "rejected": len(rejected_truth),
            "errors": errors,
            "evidence": evidence,
            "false_positives": len(rejected_truth),
            "false_positive_details": rejected_truth,
            "leads": [],
        }

    # 5) Deterministic scoring + threshold
    t4 = _now_ms()
    scored: list[dict] = []
    rejected_scoring: list[dict] = []
    for lead in verified:
        score, breakdown = _score_lead_deterministic(lead)
        lead["score"] = score
        lead["score_breakdown"] = breakdown
        lead["statut"] = "nouveau"
        if score >= settings.min_lead_score:
            scored.append(lead)
        else:
            lead["rejection_reason"] = f"Score below threshold ({settings.min_lead_score})"
            rejected_scoring.append(lead)

    evidence["timings_ms"]["scoring"] = _now_ms() - t4
    evidence["counts"]["scored_kept"] = len(scored)
    evidence["counts"]["scored_rejected"] = len(rejected_scoring)

    if not scored:
        return {
            "city": city,
            "niche": niche,
            "status": "no_results",
            "duration": round((_now_ms() - start_ms) / 1000, 1),
            "qualified": 0,
            "rejected": len(rejected_truth) + len(rejected_scoring),
            "errors": errors,
            "evidence": evidence,
            "false_positives": len(rejected_truth),
            "false_positive_details": rejected_truth + rejected_scoring,
            "leads": [],
        }

    # 6) Save to DB (bulk upsert). Only after verification + scoring.
    t5 = _now_ms()
    evidence["timings_ms"]["db_upsert"] = _now_ms() - t5
    db_result = upsert_leads_raw([to_supabase_lead_dict(l) for l in scored])
    if db_result.get("error"):
        errors.append({"stage": "db_upsert", "error": db_result.get("error")})

    duration_s = round((_now_ms() - start_ms) / 1000, 1)
    return {
        "city": city,
        "niche": niche,
        "status": "completed",
        "duration": duration_s,
        "qualified": len(scored),
        "rejected": len(rejected_truth) + len(rejected_scoring),
        "errors": errors,
        "evidence": evidence,
        "db": db_result,
        "leads": scored,
        "false_positives": len(rejected_truth),
        "false_positive_details": rejected_truth,
    }


def run_pipeline(city: str, niche: str) -> dict:
    """
    Run the full 3-agent pipeline for a single city + niche combination.
    Returns a summary dict with results.
    """
    from crewai import Crew, Process

    start = time.time()

    console.print(Panel(
        f"[bold white]🏙️  City:[/bold white] {city}\n"
        f"[bold white]🏷️  Niche:[/bold white] {niche}\n"
        f"[bold white]⚙️  Mode:[/bold white] {'🟡 MOCK' if settings.is_mock else '🟢 PRODUCTION'}",
        title="[bold cyan]🎯 Starting Lead Hunt[/bold cyan]",
        border_style="cyan",
    ))

    # ── Create Agents ──────────────────────────────────────
    console.print("\n[bold yellow]▶ Creating agents...[/bold yellow]")

    searcher = create_searcher_agent()
    scraper = create_scraper_agent()
    validator = create_validator_agent()

    # ── Create Tasks (sequential chain) ────────────────────
    search_task = create_search_task(searcher, city, niche)
    scrape_task = create_scrape_task(scraper, city, niche)
    validate_task = create_validate_task(validator, city, niche)

    # Chain: scrape_task depends on search_task output
    scrape_task.context = [search_task]
    # validate_task depends on scrape_task output
    validate_task.context = [scrape_task]

    # ── Assemble Crew ──────────────────────────────────────
    crew = Crew(
        agents=[searcher, scraper, validator],
        tasks=[search_task, scrape_task, validate_task],
        process=Process.sequential,
        verbose=True,
    )

    # ── Run ────────────────────────────────────────────────
    console.print("\n[bold green]🚀 Launching crew...[/bold green]\n")

    try:
        result = crew.kickoff()
    except Exception as e:
        console.print(f"\n[bold red]❌ Pipeline error: {e}[/bold red]")
        return {
            "city": city,
            "niche": niche,
            "status": "error",
            "error": str(e),
            "duration": round(time.time() - start, 1),
        }

    duration = round(time.time() - start, 1)

    # ── Parse result ───────────────────────────────────────
    raw_text = result.raw if hasattr(result, "raw") else str(result)

    summary = {
        "city": city,
        "niche": niche,
        "status": "completed",
        "duration": duration,
    }

    # Try to extract structured JSON from the LLM output
    parsed = _extract_json(raw_text)

    if isinstance(parsed, dict) and "total_qualified" in parsed:
        # Clean summary format from validator
        summary["result"] = parsed
        summary["qualified"] = parsed.get("total_qualified", 0)
        summary["rejected"] = parsed.get("total_rejected", 0)
        summary["leads"] = parsed.get("qualified_leads", [])
    else:
        # Fallback: extract any lead objects from the output
        leads = _extract_leads_from_output(raw_text)
        summary["qualified"] = len(leads)
        summary["rejected"] = 0
        summary["leads"] = leads
        if parsed is not None:
            summary["result"] = parsed

    # Always keep raw output for debugging
    summary["raw_output"] = raw_text

    # ── Independent Verification (anti-hallucination) ──────
    # Re-check each lead via Serper API directly — no LLM involved.
    # This catches false positives where the model said "no website"
    # but the business actually has one.
    raw_leads = summary.get("leads", [])
    if raw_leads and not settings.is_mock:
        console.print("\n[bold yellow]🔍 Vérification indépendante des leads (anti-hallucination)...[/bold yellow]")
        verified_leads, false_positives = filter_verified_leads(raw_leads)

        if false_positives:
            console.print(
                f"[bold red]🚫 {len(false_positives)} faux positif(s) détecté(s) et éliminé(s):[/bold red]"
            )
            for fp in false_positives:
                console.print(
                    f"  ✗ [red]{fp.get('name', '?')}[/red] → {fp.get('verified_website', '?')}"
                )

        summary["leads"] = verified_leads
        summary["qualified"] = len(verified_leads)
        summary["false_positives"] = len(false_positives)
        summary["false_positive_details"] = false_positives

    # ── Display summary ────────────────────────────────────
    qualified = summary.get('qualified', '?')
    rejected = summary.get('rejected', '?')
    leads_found = summary.get('leads', [])

    console.print(Panel(
        f"[bold white]⏱️  Duration:[/bold white] {duration}s\n"
        f"[bold white]✅ Qualified:[/bold white] {qualified}\n"
        f"[bold white]❌ Rejected:[/bold white] {rejected}\n"
        f"[bold white]📋 Leads:[/bold white] {len(leads_found)} extracted",
        title=f"[bold green]✅ Completed: {city} × {niche}[/bold green]",
        border_style="green",
    ))

    # Show leads table if any were found
    if leads_found:
        lead_table = Table(show_header=True, header_style="bold green")
        lead_table.add_column("#", style="dim", width=3)
        lead_table.add_column("Nom", style="white")
        lead_table.add_column("Ville", style="cyan")
        lead_table.add_column("Score", justify="right", style="bold yellow")
        lead_table.add_column("Téléphone", style="dim")
        lead_table.add_column("Email", style="dim")

        for idx, lead in enumerate(leads_found, 1):
            n = normalize_lead_keys(lead)
            name = n.get("name", "?")
            ville = n.get("city", "?")
            score = str(lead.get("score", "?"))
            phone = lead.get("telephone", lead.get("phone", "")) or n.get("phone", "")
            email = lead.get("email", "")
            lead_table.add_row(str(idx), name, ville, score, phone, email)

        console.print(lead_table)

    return summary


# ─── Main ──────────────────────────────────────────────────

def main():
    args = parse_args()

    # Override mode if specified
    if args.mode:
        settings.mode = args.mode
        os.environ["MODE"] = args.mode

    # Show banner
    console.print(Panel(
        "[bold white]Autonomous Multi-Agent Lead Hunting System[/bold white]\n"
        "[dim]Searcher → Scraper → Validator → Supabase[/dim]",
        title="[bold cyan]🎯 LEAD HUNTER v1.0[/bold cyan]",
        border_style="bright_blue",
        padding=(1, 2),
    ))

    # List mode
    if args.list:
        show_config_list()
        return

    # Validate environment
    missing = settings.validate()
    if missing:
        console.print(f"\n[bold red]❌ Missing environment variables: {', '.join(missing)}[/bold red]")
        console.print("[dim]Copy .env.example to .env and fill in your keys.[/dim]\n")
        sys.exit(1)

    strategy = args.strategy or ("tool-first" if not settings.is_mock else "crewai")
    console.print(f"\n[dim]Mode: {'🟡 MOCK (no real API calls)' if settings.is_mock else '🟢 PRODUCTION'}[/dim]")
    console.print(f"[dim]Strategy: {strategy}[/dim]")

    # Determine which city/niche combinations to run
    if args.all:
        pairs = list(product(
            [c["name"] for c in settings.cities],
            settings.niches,
        ))
        console.print(f"\n[bold yellow]⚠️  Running ALL {len(pairs)} combinations[/bold yellow]")
    elif args.city and args.niche:
        pairs = [(args.city, args.niche)]
    elif args.city:
        pairs = [(args.city, n) for n in settings.niches]
        console.print(f"\n[cyan]Running {len(pairs)} niches for {args.city}[/cyan]")
    elif args.niche:
        pairs = [(c["name"], args.niche) for c in settings.cities]
        console.print(f"\n[cyan]Running {len(pairs)} cities for {args.niche}[/cyan]")
    else:
        # Default: first city × first niche (safe for testing)
        city = settings.cities[0]["name"]
        niche = settings.niches[0]
        pairs = [(city, niche)]
        console.print(f"\n[dim]No args — defaulting to: {city} × {niche}[/dim]")

    # Run pipeline for each pair
    results = []
    total = len(pairs)

    for i, (city, niche) in enumerate(pairs, 1):
        console.print(f"\n[bold]{'='*60}[/bold]")
        console.print(f"[bold cyan]  Run {i}/{total}[/bold cyan]")
        console.print(f"[bold]{'='*60}[/bold]")

        if strategy == "tool-first":
            summary = run_pipeline_tool_first(city, niche)
        else:
            summary = run_pipeline(city, niche)
        results.append(summary)

        # Brief pause between runs to avoid rate limits
        if i < total:
            wait = 5 if settings.is_mock else 15
            console.print(f"\n[dim]Waiting {wait}s before next run...[/dim]")
            time.sleep(wait)

    # ── Final Summary ──────────────────────────────────────
    console.print(f"\n\n[bold]{'='*60}[/bold]")
    console.print("[bold cyan]  📊 FINAL SUMMARY[/bold cyan]")
    console.print(f"[bold]{'='*60}[/bold]\n")

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("City", style="white")
    table.add_column("Niche", style="white")
    table.add_column("Status", style="white")
    table.add_column("Qualified", justify="right")
    table.add_column("Duration", justify="right", style="dim")

    for r in results:
        status_icon = "✅" if r["status"] == "completed" else "❌"
        qual = str(r.get("qualified", "?"))
        table.add_row(
            r["city"], r["niche"],
            f"{status_icon} {r['status']}",
            qual,
            f"{r['duration']}s",
        )

    console.print(table)

    # Save results to results/ directory
    results_dir = settings.project_root / "results"
    results_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Save global summary (all runs)
    summary_file = results_dir / f"run_{timestamp}.json"
    # Strip raw_output from saved file to keep it clean
    clean_results = []
    for r in results:
        clean = {k: v for k, v in r.items() if k != "raw_output"}
        clean_results.append(clean)

    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(clean_results, f, indent=2, default=str, ensure_ascii=False)

    # Save individual leads as a flat CSV-ready JSON
    all_leads = []
    for r in results:
        for lead in r.get("leads", []):
            lead["_run_city"] = r["city"]
            lead["_run_niche"] = r["niche"]
            lead["_run_timestamp"] = timestamp
            all_leads.append(lead)

    if all_leads:
        # JSON
        leads_file = results_dir / f"leads_{timestamp}.json"
        with open(leads_file, "w", encoding="utf-8") as f:
            json.dump(all_leads, f, indent=2, default=str, ensure_ascii=False)

        # CSV
        csv_file = export_csv(all_leads, results_dir / f"leads_{timestamp}.csv")

        # Excel
        xlsx_file = export_excel(all_leads, results_dir / f"leads_{timestamp}.xlsx")

        console.print(f"\n[bold green]📁 {len(all_leads)} leads exportés :[/bold green]")
        console.print(f"  [dim]JSON  → {leads_file}[/dim]")
        console.print(f"  [dim]CSV   → {csv_file}[/dim]")
        console.print(f"  [dim]Excel → {xlsx_file}[/dim]")

        log.info(f"{len(all_leads)} leads exported to JSON/CSV/Excel in {results_dir}")
    else:
        console.print("\n[yellow]⚠️  Aucun lead qualifié à exporter.[/yellow]")

    console.print(f"\n[dim]Run summary saved to {summary_file}[/dim]")
    console.print(f"[dim]Dashboard : streamlit run dashboard.py[/dim]\n")

    log.info(f"Run complete: {len(results)} pipelines, {len(all_leads)} total leads")


if __name__ == "__main__":
    main()
