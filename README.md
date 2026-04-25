# 🎯 Lead Hunting Agent

Un système multi-agents autonome conçu pour identifier, enrichir, valider et stocker des leads B2B (PME sans site web).

## Architecture

Le système utilise **CrewAI** pour orchestrer 3 agents :
1. **Searcher** : Cherche sur Google et Google Places les businesses sans site web.
2. **Scraper** : Visite les pages via Playwright (navigateur headless) pour extraire téléphones, emails, réseaux sociaux et confirmer l'absence de site web.
3. **Validator** : Score les leads (1 à 10) selon des critères précis et sauvegarde les meilleurs (score >= 5) dans Supabase.

## Objectif “zéro faux positifs”

Deux stratégies existent :

- **`crewai`** (LLM-driven) : pipeline multi-agents classique.
- **`tool-first`** (recommandé en production) : pipeline déterministe “zéro hallucination”.
  - Découverte via Places (Serper/Google).
  - **Vérité terrain** via Playwright (scraping de la fiche Google Maps).
  - Si la vérification échoue → statut **unknown** → lead rejeté (règle “zéro faux positifs”).

## Prérequis

- Python 3.11+
- [LiteLLM](https://docs.litellm.ai/) & CrewAI
- Playwright
- Un projet [Supabase](https://supabase.com/)
- Clés API : Groq (LLM), Serper.dev (Places/Search), Google Maps (Places API, optionnel)

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

### Variables d’environnement (résumé)

- **`MODE`**: `mock` | `production`
- **`DATA_SOURCE`**: `serper` | `google`
- **`GROQ_API_KEY`**: requis en production (LLM CrewAI)
- **`SERPER_API_KEY`**: requis en production (Places via Serper + vérification indépendante)
- **`GOOGLE_MAPS_API_KEY`**: requis *uniquement* si `DATA_SOURCE=google`
- **`SUPABASE_URL`**, **`SUPABASE_KEY`**: requis en production

## Utilisation

### Lancer une recherche

```bash
# Lister les villes et niches disponibles
python main.py --list

# Par défaut (safe) : 1 ville × 1 niche (mock)
python main.py

# Mode Test (mock) - aucune clé API requise
python main.py --city "Charlotte NC" --niche "barbershop" --mode mock

# Mode Production - Utilise les vraies APIs
python main.py --city "Charlotte NC" --niche "barbershop" --mode production

# Choisir la stratégie
python main.py --city "Charlotte NC" --niche "barbershop" --mode production --strategy tool-first
python main.py --city "Charlotte NC" --niche "barbershop" --mode production --strategy crewai

# Lancer toutes les combinaisons ville×niche (attention aux coûts/quotas)
python main.py --mode production --all
```

### Dashboard et Exports

Le projet inclut désormais un dashboard Streamlit interactif pour visualiser, filtrer et exporter les leads (CSV, Excel avec code couleur, JSON).

```bash
# Lancer le dashboard interactif
streamlit run dashboard.py
```
*Le dashboard sera accessible sur `http://localhost:8501`.*

À chaque exécution réussie de `main.py`, les leads générés sont également exportés automatiquement dans le dossier `results/` sous plusieurs formats :
- `run_YYYYMMDD_HHMMSS.json` (résumé par exécution)
- `leads_YYYYMMDD_HHMMSS.json` (liste aplatie des leads)
- `leads_YYYYMMDD_HHMMSS.csv`
- `leads_YYYYMMDD_HHMMSS.xlsx`

### Logs (Traçabilité)
Un système de logs complet (`loguru`) est intégré. Les logs sont enregistrés et archivés (rotation) dans le dossier `logs/`.
