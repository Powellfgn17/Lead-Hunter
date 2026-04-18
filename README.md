# 🎯 Lead Hunting Agent

Autonomous Multi-Agent System built with [CrewAI](https://crewai.com/).
It automatically finds local businesses without websites, enriches their data, scores them, and saves the qualified leads to a Supabase database.

## 🚀 How it works

1. **Searcher Agent:** Takes a city and niche, searches Google and Places API, finds businesses without websites.
2. **Scraper Agent:** Opens a headless browser (Playwright), visits listings, extracts phone/email/socials, and double-verifies the absence of a website.
3. **Validator Agent:** Scores the lead (1-10) based on recent reviews, contact info, and activity. Eliminates weak leads and saves the rest to Supabase.

## ⚙️ Installation

```bash
# Create a virtual environment and install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## 🔑 Configuration

Copy `.env.example` to `.env` and fill in your keys:
- `GROQ_API_KEY` (LLM)
- `SERPER_API_KEY` (Google Search)
- `GOOGLE_MAPS_API_KEY` (Places API)
- `SUPABASE_URL` & `SUPABASE_KEY` (Database)

Execute `supabase_schema.sql` in your Supabase SQL Editor to create the tables.

## 💻 Usage

```bash
# List available cities and niches
python main.py --list

# Run a specific city and niche (Mock mode by default)
python main.py --city "Charlotte NC" --niche "barbershop"

# Run in production (real API calls & DB inserts)
python main.py --city "Charlotte NC" --niche "barbershop" --mode production

# Run all niches for a city
python main.py --city "Lyon France" --mode production
```
