# solar-platform

Solar operations and analytics platform with a package-first architecture.

The codebase is split into a framework-agnostic core library plus thin runtime layers for UI, API, and automation tasks.

## What this repository contains

```text
solar-platform/
├── src/solar_platform/   # Core domain library (analysis, db, alerts, ingestion, reporting)
├── app/                  # Streamlit UI shell (pages, components, styles)
├── api/                  # FastAPI entrypoint and routes
├── cli/                  # Operational scripts as Python modules
├── tests/                # Pytest suite
└── docs/                 # Admin, user, and development documentation
```

## Architecture boundaries

- `src/solar_platform` is the canonical business/domain layer and should stay independent of Streamlit.
- `app` should contain presentation/UI concerns only.
- `api` should expose core capabilities via HTTP endpoints.
- `cli` should orchestrate jobs and batch tasks by importing `solar_platform` modules.

This structure allows you to run modules independently without running the full Streamlit app.

## Quick start

### 1) Create environment and install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[all]
```

### 2) Run the Streamlit app

```bash
streamlit run app/main.py --server.port 8501 --server.headless true
```

### 3) Run the API

```bash
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

### 4) Run CLI modules

```bash
python -m cli.backfill --help
python -m cli.import_solar_all --help
python -m cli.migrate_to_postgres --help
```

Note: some CLI modules are operational tasks with required environment/config and may not expose full `--help` output.

### 5) Run tests

```bash
pytest tests/ -q
```

## Developer workflow

### Add a new analysis feature

1. Implement domain logic in `src/solar_platform/<domain>/...`
2. Add tests in `tests/` close to that domain
3. Expose it in `app/pages/...`, `api/...`, or `cli/...` only if needed

### Add a new job/task script

1. Create a module in `cli/`
2. Import from `solar_platform` instead of UI modules
3. Run with `python -m cli.<module_name>`

### Keep imports clean

- Prefer `from solar_platform...` imports for core logic
- Avoid importing from `app` inside `src/solar_platform`

## Validation commands

```bash
# Full tests
python -m pytest tests/ -q --tb=line

# Core package import smoke
python - <<'PY'
import importlib
mods = [
	"solar_platform.config",
	"solar_platform.analysis",
	"solar_platform.db",
	"solar_platform.alerts",
	"solar_platform.ingestion",
	"solar_platform.reporting",
]
for m in mods:
	importlib.import_module(m)
print("Import smoke OK")
PY
```

## Legacy migration note

Active code no longer lives under the old `platform/` layout.

Use these directories for all new work:

- `src/solar_platform/`
- `app/`
- `api/`
- `cli/`
- `tests/`

## Related docs

- `docs/ADMIN_GUIDE.md`
- `docs/USER_GUIDE.md`
- `docs/development/` (implementation notes and technical plans)

## Next steps

- Merge branch `codex/copilot-triage-publish-run` into `main` after testing
- Complete Morpheus site onboarding: add Benelux/Iberia/UK sites post-acquisition, including Holcim (Obourg) once PAC is issued
- Fix `Monthly Email Queue` workflow — fails without `MONTHLY_EMAIL_RECIPIENTS` input
- Add Juggle API client to `tools/inverter-data-juggle/` (current sync relies on SolarEdge and Solis only)
- Set up alerting for GitHub Actions workflow failures — no notification currently if daily sync breaks

## Areas to improve

- **No PR vs irradiance baseline** — `copilot_audit.py` flags faults but does not compare actual yield against expected from irradiance
- **No `.env.example`** at repo root — new developers cannot discover required secrets without reading multiple files
- **No `CONTRIBUTING.md`** — multi-component architecture (core library, Streamlit app, FastAPI, CLI) is not documented for contributors
- **Metris billing not ingested** — portal access is active but no pipeline imports Metris budget vs actual data into the platform
- **One-off scripts in codebase** — `platform/reports/away_day_2026/` and similar should be archived or moved out of `main`
