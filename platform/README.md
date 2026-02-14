# Solar Portfolio Manager

Unified Streamlit platform for solar portfolio operations, analysis, reporting, data resilience, and financial tracking.

## Current Status

- Phases **0–8 complete** (foundation through polish/launch)
- Service-layer architecture in place for future API/frontend extraction
- Advanced analysis, reporting, alerts/tickets, data quality, and financial modules are integrated

## Core Capabilities

### Portfolio & Operations
- Portfolio dashboard and plant detail pages
- Site monitor, plant management, POA import, and data explorer
- Global search, breadcrumbs, responsive layouts, and theme toggle

### Analysis
- Comparative analysis
- Clipping analysis
- Curtailment analysis
- Shading analysis
- Fouling analysis
- Thermal loss analysis
- PR trending
- Degradation analysis
- Loss waterfall

### Alerts & Tickets
- Rule-based alert evaluation
- Alert lifecycle handling
- Ticket creation and Kanban management
- Notification bridge integration

### Reporting
- Report template/schema models
- Report builder UI and report library UI
- PDF rendering and chart export
- Monthly / ExCom / O&M report templates
- Scheduling support

### Data Resilience
- Validation framework and per-reading quality scoring
- Gap detection and filling strategies
- Multi-source harmonization and source priority logic
- Sensor health monitoring
- Data quality dashboard

### Financial & Advanced Features
- Revenue tracking
- Tariff management (including CSV import)
- Budget vs actual
- Anomaly detection and forecasting
- Optional read-only FastAPI endpoints

## Project Structure

```text
.
├── app.py                     # Streamlit entrypoint
├── modules/                   # Page-level Streamlit renderers
├── services/                  # Framework-agnostic business logic
│   ├── analysis/
│   ├── alerts/
│   ├── analytics/
│   ├── data_quality/
│   ├── financial/
│   ├── ingestion/
│   ├── reporting/
│   └── database/
├── components/                # Shared UI components
├── api/                       # Optional FastAPI app
├── tests/                     # Unit, integration, e2e, benchmarks
├── scripts/                   # Deploy, backup, rollback, health checks
└── docs/                      # User/admin/runbook documentation
```

## Prerequisites

- Python 3.11+
- pip
- (Optional) Docker + Docker Compose

## Local Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Run

```bash
make dev
```

App URL: `http://localhost:8501`

Headless run:

```bash
make run
```

## Common Commands

| Task | Command |
|------|---------|
| Run app (dev) | `make dev` |
| Run app (headless) | `make run` |
| Run tests | `make test` |
| Run tests with coverage | `make test-cov` |
| Lint | `make lint` |
| Format | `make format` |
| Docker build | `make docker-build` |
| Docker up | `make docker-up` |
| Docker up (dev overrides) | `make docker-up-dev` |
| Docker down | `make docker-down` |
| Docker logs | `make docker-logs` |
| DB quick check | `make db-shell` |
| Deploy | `make deploy` |
| Rollback | `make rollback` |
| Backup DB | `make backup` |
| Health check | `make health-check` |

## API (Optional)

Read-only endpoints are available in `api/main.py`:

- `GET /health`
- `GET /api/v1/plants`
- `GET /api/v1/plants/{plant_uid}/readings`
- `GET /api/v1/portfolio/summary`

Run API (if `fastapi` + `uvicorn` are installed):

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

## Documentation

- User guide: `docs/USER_GUIDE.md`
- Admin/ops guide: `docs/ADMIN_GUIDE.md`
- Go-live checklist: `docs/GO_LIVE_CHECKLIST.md`
- Post-launch monitoring: `docs/POST_LAUNCH_MONITORING.md`
- Phase plans: `docs/plans/`

## Notes

- Primary database is DuckDB (default via project configuration/environment).
- Legacy integrations are preserved in `archive/` and bridge services where required.
- For deployment automation, use `scripts/deploy.sh`, `scripts/rollback.sh`, and `scripts/backup_db.sh`.
