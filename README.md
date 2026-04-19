# 🎯 Lead Hunting Agent

Un système multi-agents autonome conçu pour identifier, enrichir, valider et stocker des leads B2B (PME sans site web).

## Architecture

Le système utilise **CrewAI** pour orchestrer 3 agents :
1. **Searcher** : Cherche sur Google et Google Places les businesses sans site web.
2. **Scraper** : Visite les pages via Playwright (navigateur headless) pour extraire téléphones, emails, réseaux sociaux et confirmer l'absence de site web.
3. **Validator** : Score les leads (1 à 10) selon des critères précis et sauvegarde les meilleurs (score >= 5) dans Supabase.

## Prérequis

- Python 3.11+
- [LiteLLM](https://docs.litellm.ai/) & CrewAI
- Playwright
- Un projet [Supabase](https://supabase.com/)
- Clés API : Groq (LLM), Serper.dev (Recherche web), Google Maps (Places API)

## Installation

```bash
# Activer votre environnement virtuel
source /chemin/vers/venv/bin/activate

# Installer les dépendances
pip install -r requirements.txt

# Installer le navigateur Playwright
playwright install chromium
```

## Configuration

1. Copiez `.env.example` vers `.env`
2. Remplissez vos clés API
3. Créez la table dans Supabase en exécutant le script `supabase_schema.sql` dans le SQL Editor de votre projet Supabase.

## Utilisation

### Lancer une recherche

```bash
# Lister les villes et niches disponibles
python main.py --list

# Mode Test (Mock) - Aucune clé API requise
python main.py --city "Charlotte NC" --niche "barbershop"

# Mode Production - Utilise les vraies APIs
python main.py --city "Charlotte NC" --niche "barbershop" --mode production
```

### Dashboard et Exports

Le projet inclut désormais un dashboard Streamlit interactif pour visualiser, filtrer et exporter les leads (CSV, Excel avec code couleur, JSON).

```bash
# Lancer le dashboard interactif
streamlit run dashboard.py
```
*Le dashboard sera accessible sur `http://localhost:8501`.*

À chaque exécution réussie de `main.py`, les leads générés sont également exportés automatiquement dans le dossier `results/` sous plusieurs formats :
- `leads_YYYYMMDD_HHMMSS.json`
- `leads_YYYYMMDD_HHMMSS.csv`
- `leads_YYYYMMDD_HHMMSS.xlsx`

### Logs (Traçabilité)
Un système de logs complet (`loguru`) est intégré. Les logs sont enregistrés et archivés (rotation) dans le dossier `logs/`.
