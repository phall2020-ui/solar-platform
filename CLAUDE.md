# solar-platform

Primary ADE operational platform for portfolio monitoring and reporting.

## What it does
Ingests generation data from Juggle, SolarEdge, and Solis APIs. Syncs performance data to Notion. Sends weekly and monthly email reports via 7 GitHub Actions scheduled workflows.

## Running it
```bash
# Streamlit UI
source .venv/bin/activate
streamlit run app/main.py

# FastAPI
uvicorn api.main:app

# CLI backfill/import
python cli/<script>.py
```

## Tests
```bash
source .venv/bin/activate
pytest
```

## Structure
- `src/solar_platform/` — core library
- `app/` — Streamlit UI
- `api/` — FastAPI
- `cli/` — backfill and import scripts
- `tests/`

## Deployment
7 GitHub Actions scheduled workflows. No manual deploy needed for scheduled jobs.

## Key details
- Python 3.11+ required
- Dependencies: `pip` + `requirements.txt`
- Secrets: `.env` (python-dotenv); credentials at `~/Secrets/google/`
- Recent: curtailment module refactored; nightly curtailment pull workflow added (2026-04-11); Fylde offtaker consumption CLI script (2026-03-30)

## Known gaps
- Juggle API client not yet integrated (primary ADE monitoring source missing)
- Relationship to solar-hub still unresolved
