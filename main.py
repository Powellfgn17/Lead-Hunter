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
import sys
import time
import os
from datetime import datetime
from itertools import product

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import print as rprint

from config.settings import settings
from agents.searcher import create_searcher_agent, create_search_task
from agents.scraper import create_scraper_agent, create_scrape_task
from agents.validator import create_validator_agent, create_validate_task

console = Console()


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
    summary = {
        "city": city,
        "niche": niche,
        "status": "completed",
        "duration": duration,
        "raw_output": str(result),
    }

    # Try to parse the validator's JSON output
    try:
        if hasattr(result, "raw"):
            parsed = json.loads(result.raw)
        else:
            parsed = json.loads(str(result))
        summary["result"] = parsed
        summary["qualified"] = parsed.get("total_qualified", 0)
        summary["rejected"] = parsed.get("total_rejected", 0)
    except (json.JSONDecodeError, TypeError):
        summary["result"] = str(result)
        summary["qualified"] = "unknown"

    # ── Display summary ────────────────────────────────────
    console.print(Panel(
        f"[bold white]⏱️  Duration:[/bold white] {duration}s\n"
        f"[bold white]✅ Qualified:[/bold white] {summary.get('qualified', '?')}\n"
        f"[bold white]❌ Rejected:[/bold white] {summary.get('rejected', '?')}",
        title=f"[bold green]✅ Completed: {city} × {niche}[/bold green]",
        border_style="green",
    ))

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

    console.print(f"\n[dim]Mode: {'🟡 MOCK (no real API calls)' if settings.is_mock else '🟢 PRODUCTION'}[/dim]")

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

    # Save results to file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = settings.project_root / f"results_{timestamp}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    console.print(f"\n[dim]Results saved to {output_file}[/dim]\n")


if __name__ == "__main__":
    main()
