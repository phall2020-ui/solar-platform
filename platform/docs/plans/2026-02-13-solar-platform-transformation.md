# Solar Monitoring & Analysis Platform — Transformation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Transform the existing AMPYR Solar Portfolio Manager from a Streamlit prototype into a professional-grade, production-ready solar monitoring and analysis platform that rivals GPM Horizon, Power Factors Unity, and AlsoEnergy PowerTrack — with live API feeds, alerting, ticketing, cumulative data resilience, and exceptional UI.

**Architecture:** FastAPI backend + React/Next.js frontend replacing Streamlit. TimescaleDB (PostgreSQL) replaces DuckDB for concurrent time-series workloads. Celery + Redis for background task scheduling, live API polling, and alert evaluation. All existing analysis modules (fouling, shading, clipping, thermal, curtailment, loss waterfall, monthly reporting) are preserved as Python services behind API endpoints.

**Tech Stack:** FastAPI, React 19 / Next.js 15, TypeScript, TimescaleDB (PostgreSQL 16), Redis, Celery, Docker, Tailwind CSS, shadcn/ui, Recharts/Plotly.js, WebSockets, Alembic, pytest, Playwright.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Competitive Positioning](#2-competitive-positioning)
3. [Platform Architecture](#3-platform-architecture)
4. [Phase 0 — Foundation & Infrastructure](#phase-0--foundation--infrastructure)
5. [Phase 1 — Data Layer & API Integrations](#phase-1--data-layer--api-integrations)
6. [Phase 2 — Core Platform & UI Shell](#phase-2--core-platform--ui-shell)
7. [Phase 3 — Analysis Engine Migration](#phase-3--analysis-engine-migration)
8. [Phase 4 — Alert & Ticketing System](#phase-4--alert--ticketing-system)
9. [Phase 5 — Reporting Engine](#phase-5--reporting-engine)
10. [Phase 6 — Data Resilience & Quality](#phase-6--data-resilience--quality)
11. [Phase 7 — Advanced Features](#phase-7--advanced-features)
12. [Phase 8 — Polish, Testing & Launch](#phase-8--polish-testing--launch)
13. [Data Model](#data-model)
14. [API Integration Specifications](#api-integration-specifications)
15. [UI/UX Design System](#uiux-design-system)
16. [Risk Register](#risk-register)

---

## 1. Executive Summary

### What We Have Today

The existing app is a **Streamlit-based internal tool** with ~15,000 lines of Python across 60+ files. It consolidates two legacy sub-projects (Solar Toolkit + Monthly Reporting) and offers:

- 7 analysis modules (fouling, shading, clipping, clipping loss, thermal, curtailment, loss waterfall)
- Monthly executive reporting with ExCom-style waterfalls
- EMIG API integration for inverter data
- SolarGIS POA import (file-based)
- Basic auth, notifications, report builder
- DuckDB single-file database (~1.28M readings rows)

**Key limitations:** Single-writer DuckDB, no live data feeds, no background scheduling, no real ticketing, no real API server, Streamlit UI constraints, brand inconsistencies, comparative_analysis.py uses wrong DB driver.

### What We're Building

A platform that matches the **feature depth of Power Factors Unity** at the **simplicity of deployment** for mid-market portfolios (1–100MW). Specifically:

| Capability | Current | Target |
|-----------|---------|--------|
| Data ingestion | Manual pull from EMIG | Live polling from EMIG, Juggle, SolarGIS, SMA, Enphase, SolarEdge, Huawei, Fronius |
| Data freshness | Hours/days (manual) | 5-minute polling, near-real-time |
| Concurrent users | 1 (DuckDB lock) | Unlimited (PostgreSQL) |
| Alert system | Manual threshold checks | Automated background evaluation every 5 min, escalation, routing |
| Ticketing | None | Full lifecycle: Event → Ticket → Assignment → Resolution → KPI |
| UI framework | Streamlit (Python) | React/Next.js (professional SPA) |
| API | Simulated endpoints | Real REST + WebSocket API |
| Data resilience | None | Cumulative approach with satellite fallback, quality scoring, gap filling |
| Mobile | No | Responsive + PWA |
| Deployment | Single container | Docker Compose (API + Worker + DB + Redis + Frontend) |

### Why Not Stay With Streamlit?

1. **DuckDB single-writer** — Cannot support multiple users or background jobs writing simultaneously
2. **No WebSockets** — Cannot push real-time updates (alerts, live data) to the browser
3. **Limited UI expressiveness** — No drag-and-drop, no complex layouts, no animations, no map interactions
4. **No REST API** — Cannot serve external integrations or mobile apps
5. **Session state fragility** — State lost on rerun, no persistent client-side state
6. **Cannot compete visually** — GPM Horizon and Power Factors have custom-built UIs; Streamlit will always look like a data app

---

## 2. Competitive Positioning

### Where We Fit

```
                    Feature Depth →
                    
    Residential     C&I / Small Utility     Utility-Scale IPP
    ┌──────────┐    ┌─────────────────┐     ┌──────────────────┐
    │ Enphase  │    │                 │     │ GPM Horizon      │
    │ SolarEdge│    │  ★ OUR TARGET  │     │ Power Factors    │
    │ Fronius  │    │   MARKET        │     │ AlsoEnergy       │
    │          │    │                 │     │ Bazefield        │
    └──────────┘    └─────────────────┘     └──────────────────┘
    
    Simple ←──────── Complexity ──────────→ Enterprise
```

### Competitive Advantages We'll Build

| Advantage | Detail | Competitors Lacking This |
|-----------|--------|--------------------------|
| **Loss analysis depth** | 7 dedicated loss modules (clipping, fouling, shading, thermal, curtailment, export limit, combined waterfall) | Most competitors bundle or omit 3+ of these |
| **UK/EU grid awareness** | Export limit loss tracking, DNO curtailment analysis, BSUoS, seasonal adjustment | Most platforms are US/Australia focused |
| **Data transparency** | Database viewer, data explorer, raw query access | All competitors are black boxes |
| **Self-serve analytics** | No consultancy needed for advanced analysis | Quintas requires consulting engagement |
| **Simple deployment** | Single docker-compose, no SCADA hardware required | GPM/PF require on-site hardware + contracts |
| **Affordable** | Target 1-50MW portfolios priced out of enterprise platforms | GPM/PF minimum ~$5k/month |
| **Automated monthly reporting** | One-click branded ExCom reports with loss attribution | Competitors require manual assembly |
| **Cumulative data resilience** | Multi-source data with quality scoring and automatic fallback | Only Solargis and Power Factors approach this |

### Feature Parity Targets (by competitor)

| Feature from Competitor | Source Platform | Our Implementation |
|------------------------|----------------|--------------------|
| Loss waterfall with drill-down | Power Factors Unity | Phase 3 — Enhanced loss waterfall |
| Event → Ticket → Resolution loop | Power Factors FSM | Phase 4 — Ticketing system |
| Map-based portfolio view | SolarEdge, Power Factors | Phase 2 — Leaflet/Mapbox fleet map |
| Predictive maintenance signals | GPM Gemini | Phase 7 — Anomaly detection (ML) |
| Gap-free irradiance data | Solargis Monitor | Phase 6 — Satellite fallback + quality scoring |
| Data quality scoring | Solargis Analyst | Phase 6 — Per-datapoint confidence |
| Multi-source harmonization | Solargis Analyst | Phase 6 — Weighted source blending |
| Tiered product modules | GPM Horizon | Phase 7 — Module-based access control |
| Automated report scheduling | AlsoEnergy, GPM | Phase 5 — Celery-scheduled PDF generation |
| Mobile field app | GPM Elite, SolarEdge GO | Phase 7 — PWA with offline mode |

---

## 3. Platform Architecture

### System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        FRONTEND (Next.js 15)                        │
│  React 19 · TypeScript · Tailwind CSS · shadcn/ui · Recharts       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │Dashboard │ │Portfolio │ │Analysis  │ │Alerts &  │ │Reports   │ │
│  │          │ │& Plants  │ │Modules   │ │Tickets   │ │& Export  │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ WebSocket Client — live data, alerts, ticket updates         │   │
│  └──────────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────┤
│                      API GATEWAY (FastAPI)                          │
│  REST endpoints · WebSocket server · JWT auth · Rate limiting      │
│  OpenAPI docs · CORS · Request validation (Pydantic v2)            │
├─────────────────────────────────────────────────────────────────────┤
│                       SERVICE LAYER (Python)                        │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐          │
│  │ Ingestion │ │ Analysis  │ │ Alert     │ │ Reporting │          │
│  │ Service   │ │ Engine    │ │ Engine    │ │ Engine    │          │
│  ├───────────┤ ├───────────┤ ├───────────┤ ├───────────┤          │
│  │ EMIG      │ │ Fouling   │ │ Threshold │ │ PDF Gen   │          │
│  │ Juggle    │ │ Shading   │ │ Anomaly   │ │ Excel Gen │          │
│  │ SolarGIS  │ │ Clipping  │ │ Trend     │ │ Scheduled │          │
│  │ SMA       │ │ Thermal   │ │ Escalation│ │ Templates │          │
│  │ Enphase   │ │ Curtail   │ │ Routing   │ │ Branding  │          │
│  │ SolarEdge │ │ Waterfall │ │           │ │           │          │
│  │ Huawei    │ │ Comparatv │ │           │ │           │          │
│  │ Fronius   │ │           │ │           │ │           │          │
│  └───────────┘ └───────────┘ └───────────┘ └───────────┘          │
├─────────────────────────────────────────────────────────────────────┤
│                    BACKGROUND WORKERS (Celery)                      │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐      │
│  │ Data Poll  │ │ Alert Eval │ │ Report Gen │ │ Data Clean │      │
│  │ (5-min)    │ │ (5-min)    │ │ (scheduled)│ │ (hourly)   │      │
│  └────────────┘ └────────────┘ └────────────┘ └────────────┘      │
│  Celery Beat scheduler · Flower monitoring dashboard               │
├─────────────────────────────────────────────────────────────────────┤
│                    DATA LAYER                                       │
│  ┌────────────────────────┐  ┌──────────┐  ┌──────────────────┐   │
│  │  TimescaleDB           │  │  Redis    │  │  Object Storage  │   │
│  │  (PostgreSQL 16)       │  │  7.x     │  │  (S3 / MinIO)    │   │
│  │                        │  │          │  │                  │   │
│  │  • readings (hyper)    │  │  • Cache  │  │  • Report PDFs   │   │
│  │  • plants              │  │  • Queue  │  │  • Chart images  │   │
│  │  • solar_data          │  │  • PubSub │  │  • File uploads  │   │
│  │  • alerts              │  │  • Sessions│  │  • Backups       │   │
│  │  • tickets             │  │          │  │                  │   │
│  │  • users               │  │          │  │                  │   │
│  │  • audit_log           │  │          │  │                  │   │
│  │  • data_quality        │  │          │  │                  │   │
│  └────────────────────────┘  └──────────┘  └──────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### Key Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Database** | TimescaleDB (PostgreSQL) | Concurrent reads/writes, time-series hypertables, continuous aggregates replace materialized views, mature ecosystem, full SQL |
| **Backend** | FastAPI | Async support, auto OpenAPI docs, Pydantic v2 validation (already used), WebSocket support, same Python ecosystem as existing analysis code |
| **Frontend** | Next.js 15 + React 19 | Server components for SEO, app router, professional UI capability, massive ecosystem, TypeScript safety |
| **UI Components** | shadcn/ui + Tailwind | Professional look without custom CSS, accessible, customizable, dark mode built-in |
| **Charts** | Recharts + Plotly.js | Recharts for standard charts (fast, React-native), Plotly.js for complex analysis (heatmaps, 3D, waterfall) |
| **Task Queue** | Celery + Redis | Proven at scale, periodic tasks via Celery Beat, result backend, Flower monitoring |
| **Caching** | Redis | Fast, supports pub/sub for WebSocket broadcasting, session store, rate limiting |
| **Object Storage** | MinIO (self-hosted S3) | Report PDFs, chart exports, file uploads. S3-compatible for cloud migration |
| **Auth** | JWT + Redis sessions | Stateless API auth, Redis for session management and token revocation |
| **Migrations** | Alembic | Versioned schema migrations (critical gap in current system) |

### Directory Structure (Target)

```
solar-platform/
├── backend/
│   ├── alembic/                    # Database migrations
│   │   ├── versions/
│   │   └── env.py
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                 # FastAPI app factory
│   │   ├── config.py               # Settings via pydantic-settings
│   │   ├── dependencies.py         # Dependency injection
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── v1/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── router.py       # API v1 router
│   │   │   │   ├── auth.py         # Auth endpoints
│   │   │   │   ├── plants.py       # Plant CRUD
│   │   │   │   ├── readings.py     # Time-series data
│   │   │   │   ├── analysis.py     # Analysis endpoints
│   │   │   │   ├── alerts.py       # Alert management
│   │   │   │   ├── tickets.py      # Ticket CRUD
│   │   │   │   ├── reports.py      # Report generation
│   │   │   │   ├── dashboards.py   # Dashboard data
│   │   │   │   ├── exports.py      # Data export
│   │   │   │   └── websocket.py    # WebSocket handler
│   │   │   └── middleware.py       # Auth, CORS, rate limiting
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── base.py             # SQLAlchemy base
│   │   │   ├── plant.py            # Plant, Device, Inverter
│   │   │   ├── reading.py          # TimescaleDB hypertable
│   │   │   ├── solar_data.py       # Monthly aggregated data
│   │   │   ├── alert.py            # Alert rules + history
│   │   │   ├── ticket.py           # Ticket + comments + attachments
│   │   │   ├── user.py             # User, Role, Permission
│   │   │   ├── report.py           # Report templates + generated
│   │   │   ├── data_quality.py     # Quality scores + gap records
│   │   │   ├── audit.py            # Audit log
│   │   │   └── notification.py     # Notifications
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── ingestion/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── base.py         # Abstract ingestion interface
│   │   │   │   ├── emig.py         # EMIG API adapter
│   │   │   │   ├── juggle.py       # Juggle API adapter
│   │   │   │   ├── solargis.py     # SolarGIS API adapter
│   │   │   │   ├── sma.py          # SMA Sunny Portal adapter
│   │   │   │   ├── enphase.py      # Enphase API adapter
│   │   │   │   ├── solaredge.py    # SolarEdge API adapter
│   │   │   │   ├── huawei.py       # Huawei FusionSolar adapter
│   │   │   │   ├── fronius.py      # Fronius Solar.web adapter
│   │   │   │   ├── generic_csv.py  # Manual CSV/Excel upload
│   │   │   │   └── coordinator.py  # Multi-source orchestration
│   │   │   ├── analysis/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── fouling.py      # ← Migrated from modules/fouling.py
│   │   │   │   ├── shading.py      # ← Migrated from modules/shading.py
│   │   │   │   ├── clipping.py     # ← Migrated from modules/clipping_analysis.py
│   │   │   │   ├── clipping_loss.py# ← Migrated from modules/clipping_loss.py
│   │   │   │   ├── thermal.py      # ← Migrated from modules/thermal_loss.py
│   │   │   │   ├── curtailment.py  # ← Migrated from modules/curtailment_analysis.py
│   │   │   │   ├── waterfall.py    # ← Migrated from modules/loss_waterfall.py
│   │   │   │   ├── comparative.py  # ← Migrated from modules/comparative_analysis.py
│   │   │   │   ├── pr_analysis.py  # NEW: Weather-normalized PR trending
│   │   │   │   └── degradation.py  # NEW: Panel degradation tracking
│   │   │   ├── alerting/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── engine.py       # Alert evaluation engine
│   │   │   │   ├── rules.py        # Rule definitions + custom rules
│   │   │   │   ├── escalation.py   # Escalation policies
│   │   │   │   └── channels.py     # Email, Slack, webhook, in-app
│   │   │   ├── ticketing/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── service.py      # Ticket lifecycle management
│   │   │   │   ├── assignment.py   # Auto-assignment logic
│   │   │   │   └── sla.py          # SLA tracking + escalation
│   │   │   ├── reporting/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── generator.py    # ← Migrated from modules/report_generator.py
│   │   │   │   ├── monthly.py      # ← Migrated from Monthly reporting/
│   │   │   │   ├── templates.py    # Report template engine
│   │   │   │   └── scheduler.py    # Celery-based scheduled reports
│   │   │   ├── data_quality/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── scorer.py       # Per-datapoint quality scoring
│   │   │   │   ├── gap_filler.py   # Interpolation + satellite fallback
│   │   │   │   ├── validator.py    # ← Enhanced from incremental_etl.py
│   │   │   │   └── harmonizer.py   # Multi-source data blending
│   │   │   ├── auth.py             # ← Migrated from services/auth_service.py
│   │   │   ├── cache.py            # Redis cache service
│   │   │   └── websocket.py        # WebSocket broadcast manager
│   │   └── tasks/
│   │       ├── __init__.py
│   │       ├── celery_app.py       # Celery configuration
│   │       ├── polling.py          # Data polling tasks (5-min)
│   │       ├── alerts.py           # Alert evaluation tasks
│   │       ├── reports.py          # Report generation tasks
│   │       ├── maintenance.py      # Cleanup, aggregation, quality checks
│   │       └── beats.py            # Celery Beat schedule definitions
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── factories.py            # Test data factories
│   │   ├── test_api/
│   │   ├── test_services/
│   │   ├── test_models/
│   │   └── test_tasks/
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── alembic.ini
├── frontend/
│   ├── src/
│   │   ├── app/                    # Next.js app router
│   │   │   ├── layout.tsx          # Root layout with sidebar
│   │   │   ├── page.tsx            # Dashboard (landing)
│   │   │   ├── portfolio/
│   │   │   │   ├── page.tsx        # Portfolio map view
│   │   │   │   └── [plantId]/
│   │   │   │       ├── page.tsx    # Plant detail
│   │   │   │       ├── readings/
│   │   │   │       ├── analysis/
│   │   │   │       └── tickets/
│   │   │   ├── analysis/
│   │   │   │   ├── fouling/
│   │   │   │   ├── shading/
│   │   │   │   ├── clipping/
│   │   │   │   ├── thermal/
│   │   │   │   ├── curtailment/
│   │   │   │   └── waterfall/
│   │   │   ├── alerts/
│   │   │   │   ├── page.tsx        # Alert dashboard
│   │   │   │   ├── rules/
│   │   │   │   └── history/
│   │   │   ├── tickets/
│   │   │   │   ├── page.tsx        # Ticket board (Kanban)
│   │   │   │   ├── [ticketId]/
│   │   │   │   └── new/
│   │   │   ├── reports/
│   │   │   │   ├── page.tsx        # Report library
│   │   │   │   ├── builder/
│   │   │   │   ├── monthly/
│   │   │   │   └── scheduled/
│   │   │   ├── data/
│   │   │   │   ├── explorer/
│   │   │   │   ├── quality/
│   │   │   │   └── import/
│   │   │   └── settings/
│   │   │       ├── profile/
│   │   │       ├── users/
│   │   │       ├── integrations/
│   │   │       └── preferences/
│   │   ├── components/
│   │   │   ├── ui/                 # shadcn/ui components
│   │   │   ├── charts/             # Chart wrapper components
│   │   │   │   ├── TimeSeriesChart.tsx
│   │   │   │   ├── WaterfallChart.tsx
│   │   │   │   ├── HeatmapChart.tsx
│   │   │   │   ├── ScatterChart.tsx
│   │   │   │   ├── GaugeChart.tsx
│   │   │   │   └── SparklineChart.tsx
│   │   │   ├── layout/
│   │   │   │   ├── Sidebar.tsx
│   │   │   │   ├── Header.tsx
│   │   │   │   ├── Breadcrumbs.tsx
│   │   │   │   └── CommandPalette.tsx  # ⌘K search
│   │   │   ├── dashboard/
│   │   │   │   ├── KPICard.tsx
│   │   │   │   ├── PortfolioMap.tsx
│   │   │   │   ├── PlantStatusGrid.tsx
│   │   │   │   └── AlertFeed.tsx
│   │   │   ├── tickets/
│   │   │   │   ├── KanbanBoard.tsx
│   │   │   │   ├── TicketCard.tsx
│   │   │   │   └── TicketDetail.tsx
│   │   │   └── data/
│   │   │       ├── DataTable.tsx
│   │   │       ├── DateRangePicker.tsx
│   │   │       ├── PlantSelector.tsx
│   │   │       └── QualityBadge.tsx
│   │   ├── hooks/
│   │   │   ├── useWebSocket.ts
│   │   │   ├── useAlerts.ts
│   │   │   ├── usePlants.ts
│   │   │   ├── useReadings.ts
│   │   │   └── useAuth.ts
│   │   ├── lib/
│   │   │   ├── api.ts              # API client (fetch wrapper)
│   │   │   ├── websocket.ts        # WebSocket manager
│   │   │   ├── utils.ts
│   │   │   └── constants.ts
│   │   └── styles/
│   │       └── globals.css         # Tailwind + custom theme
│   ├── package.json
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   ├── next.config.ts
│   └── Dockerfile
├── docker-compose.yml              # Full stack orchestration
├── docker-compose.dev.yml          # Development overrides
├── .env.example
├── Makefile                        # Common commands
└── docs/
    ├── api/                        # API documentation
    ├── architecture/               # Architecture decisions
    └── runbooks/                   # Operational guides
```

---

## Phase 0 — Foundation & Infrastructure

**Duration:** 1–2 weeks
**Goal:** Set up the development environment, project scaffolding, and CI/CD pipeline.

### Task 0.1: Project Scaffolding

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/app/config.py`
- Create: `backend/Dockerfile`
- Create: `frontend/package.json`
- Create: `frontend/next.config.ts`
- Create: `frontend/tailwind.config.ts`
- Create: `docker-compose.yml`
- Create: `docker-compose.dev.yml`
- Create: `.env.example`
- Create: `Makefile`

**Steps:**
1. Initialize FastAPI backend with `uvicorn` + `gunicorn`
2. Initialize Next.js 15 frontend with TypeScript, Tailwind CSS, shadcn/ui
3. Configure Docker Compose with services: `api`, `worker`, `beat`, `frontend`, `db` (TimescaleDB), `redis`, `minio`
4. Set up dev hot-reload: `uvicorn --reload` + `next dev`
5. Configure `.env.example` with all required environment variables

**Backend `pyproject.toml` dependencies:**
```toml
[project]
name = "solar-platform"
requires-python = ">=3.12"
dependencies = [
    # Web framework
    "fastapi>=0.115",
    "uvicorn[standard]>=0.34",
    "gunicorn>=23",
    "python-multipart>=0.0.18",
    
    # Database
    "sqlalchemy>=2.0",
    "asyncpg>=0.30",
    "alembic>=1.14",
    
    # Task queue
    "celery[redis]>=5.4",
    "flower>=2.0",
    
    # Data processing
    "pandas>=2.2",
    "numpy>=2.0",
    "pyarrow>=18",
    "pydantic>=2.10",
    "pydantic-settings>=2.7",
    
    # Solar analysis
    "pvlib>=0.13",
    
    # Visualization (server-side)
    "plotly>=6.0",
    "kaleido>=1.0",
    
    # PDF generation
    "reportlab>=4.4",
    "weasyprint>=63",
    
    # Auth
    "bcrypt>=4.2",
    "pyjwt>=2.10",
    "cryptography>=44",
    
    # Observability
    "structlog>=25",
    "sentry-sdk[fastapi]>=2.19",
    
    # HTTP clients (for API integrations)
    "httpx>=0.28",
    "aiohttp>=3.11",
    
    # Utilities
    "python-dateutil>=2.9",
    "pytz>=2024.2",
    "redis>=5.2",
    "boto3>=1.36",           # S3/MinIO
    "jinja2>=3.1",           # Report templates
]
```

### Task 0.2: Database Setup & Migrations

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/versions/001_initial_schema.py`

**Steps:**
1. Configure Alembic with async PostgreSQL connection
2. Create initial migration with all tables (see [Data Model](#data-model))
3. TimescaleDB hypertable creation for `readings` table
4. Create continuous aggregates for hourly/daily/monthly rollups
5. Seed default alert rules, admin user, and sample data

### Task 0.3: CI/CD Pipeline

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `.github/workflows/deploy.yml`

**Steps:**
1. GitHub Actions: lint (ruff + eslint), type-check (mypy + tsc), test (pytest + vitest), build (Docker)
2. Pre-commit hooks: ruff format, eslint fix
3. Deployment pipeline with staging/production environments

### Task 0.4: Data Migration Script

**Files:**
- Create: `backend/scripts/migrate_from_duckdb.py`

**Steps:**
1. Read all data from existing DuckDB `plant_registry.duckdb`
2. Transform to new schema (plants, readings, solar_data)
3. Migrate users from `users.db` SQLite
4. Migrate notifications and alert rules from `notifications.db`
5. Validate row counts and data integrity post-migration
6. Generate migration report

---

## Phase 1 — Data Layer & API Integrations

**Duration:** 3–4 weeks
**Goal:** Build the data ingestion pipeline with live API feeds and cumulative data resilience.

### Task 1.1: Data Ingestion Framework

**Files:**
- Create: `backend/app/services/ingestion/base.py`
- Create: `backend/app/services/ingestion/coordinator.py`

**Design:** Abstract `DataSource` interface that all API adapters implement:

```python
from abc import ABC, abstractmethod
from datetime import datetime
from pydantic import BaseModel

class ReadingBatch(BaseModel):
    plant_uid: str
    source: str                    # "emig", "juggle", "solargis", etc.
    readings: list[Reading]
    quality_score: float           # 0.0–1.0
    fetch_timestamp: datetime
    gaps: list[TimeRange]          # Detected gaps in the data

class Reading(BaseModel):
    timestamp: datetime
    device_id: str | None
    power_kw: float | None
    energy_kwh: float | None
    irradiance_poa_wm2: float | None
    irradiance_ghi_wm2: float | None
    ambient_temp_c: float | None
    module_temp_c: float | None
    wind_speed_ms: float | None
    voltage_v: float | None
    current_a: float | None
    frequency_hz: float | None
    export_power_kw: float | None
    grid_limit_kw: float | None
    quality_flags: dict[str, str]  # Per-field quality indicators

class DataSource(ABC):
    """Base interface for all data source adapters."""
    
    @abstractmethod
    async def fetch_readings(
        self, plant_uid: str, start: datetime, end: datetime
    ) -> ReadingBatch:
        """Fetch readings for a plant in a time range."""
    
    @abstractmethod
    async def list_plants(self) -> list[dict]:
        """List available plants/sites from this source."""
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Check if this data source is accessible."""
    
    @abstractmethod
    def source_name(self) -> str:
        """Return the canonical name of this data source."""
```

**Ingestion Coordinator** orchestrates multi-source data:
```python
class IngestionCoordinator:
    """
    Cumulative data acquisition with fallback chain.
    
    Priority order (configurable per plant):
    1. Primary source (e.g., EMIG direct API)
    2. Secondary source (e.g., Juggle aggregator)
    3. Tertiary source (e.g., SolarGIS satellite-derived)
    
    For each time interval:
    - Use highest-priority source with data
    - If gap detected, try next source in chain
    - Score each data point by source reliability
    - Flag interpolated/estimated values distinctly
    """
    
    async def ingest_plant(self, plant_uid: str) -> IngestionResult:
        """Full ingestion cycle for one plant."""
    
    async def ingest_all(self) -> list[IngestionResult]:
        """Ingest all active plants."""
    
    async def backfill(self, plant_uid: str, start: datetime, end: datetime):
        """Backfill historical data with gap detection."""
```

### Task 1.2: EMIG API Adapter

**Files:**
- Create: `backend/app/services/ingestion/emig.py`
- Migrate from: `Solar Toolkit/emig_api.py` + `services/toolkit_bridge.py`

**Steps:**
1. Async HTTP client using `httpx` (replace synchronous `requests`)
2. Implement `DataSource` interface
3. Map EMIG response fields to standard `Reading` schema
4. Handle pagination, rate limiting, and retry logic
5. Incremental fetch: track last timestamp per plant, fetch only new data

**EMIG-specific mapping:**
```python
EMIG_FIELD_MAP = {
    "apparentPower_value": "power_kw",
    "poaIrradiance_value": "irradiance_poa_wm2",
    "ambientTemperature_value": "ambient_temp_c",
    "moduleTemperature_value": "module_temp_c",
    "dcVoltage_value": "voltage_v",
    "dcCurrent_value": "current_a",
    "activePower_value": "export_power_kw",
}
```

### Task 1.3: Juggle API Adapter

**Files:**
- Create: `backend/app/services/ingestion/juggle.py`

**Steps:**
1. Research Juggle API documentation (REST endpoints, auth method, data format)
2. Implement OAuth2/API key authentication
3. Map Juggle data schema to standard `Reading` schema
4. Handle Juggle-specific data structures (device trees, virtual meters)
5. Support historical backfill and incremental polling

**Juggle capabilities to integrate:**
- Device-level time-series data (inverters, meters, weather stations)
- Virtual meter aggregation
- Alarm/event data feed
- Plant metadata and device registry sync

### Task 1.4: SolarGIS API Adapter

**Files:**
- Create: `backend/app/services/ingestion/solargis.py`

**Steps:**
1. Implement SolarGIS Monitor API integration (satellite-derived irradiance)
2. SolarGIS Forecast API for day-ahead predictions (Phase 7)
3. Map to standard Reading schema (primarily irradiance fields)
4. **Critical role:** This is the fallback irradiance source when site sensors have gaps
5. Quality scoring: satellite data gets 0.85 quality score vs 1.0 for on-site sensors

**SolarGIS data fields:**
```python
SOLARGIS_FIELD_MAP = {
    "GHI": "irradiance_ghi_wm2",
    "DNI": "irradiance_dni_wm2",  # Extended reading schema
    "DHI": "irradiance_dhi_wm2",  # Extended reading schema
    "GTI": "irradiance_poa_wm2",  # Tilted = POA equivalent
    "TEMP": "ambient_temp_c",
    "WS": "wind_speed_ms",
}
```

### Task 1.5: Inverter Platform Adapters

**Files:**
- Create: `backend/app/services/ingestion/sma.py`
- Create: `backend/app/services/ingestion/enphase.py`
- Create: `backend/app/services/ingestion/solaredge.py`
- Create: `backend/app/services/ingestion/huawei.py`
- Create: `backend/app/services/ingestion/fronius.py`

**For each adapter:**
1. OAuth2 / API key authentication per platform's developer portal
2. Map platform-specific data schema to standard `Reading` model
3. Handle platform-specific quirks:
   - **SMA:** Sunny Portal API, ennexOS transition, 5-min resolution
   - **Enphase:** Enlighten API v4, microinverter-level data, panel-level granularity
   - **SolarEdge:** Monitoring API, power optimizer-level data, module-level
   - **Huawei:** FusionSolar northbound API, iSolarCloud integration
   - **Fronius:** Solar.web API, hybrid inverter support
4. Rate limiting per platform's documented limits
5. Retry logic with exponential backoff

### Task 1.6: Generic CSV/Excel Ingestion

**Files:**
- Create: `backend/app/services/ingestion/generic_csv.py`
- Migrate from: `modules/data_explorer.py` validation logic, `modules/poa_import.py`

**Steps:**
1. Upload endpoint accepting CSV, XLSX, Parquet files
2. Auto-detect column mapping via header fuzzy matching
3. User-confirmable column mapping UI
4. Pydantic validation (enhanced from existing `SolarDataSchema`)
5. Quality scoring based on completeness and consistency
6. Merge with existing data using timestamp deduplication

### Task 1.7: Celery Polling Tasks

**Files:**
- Create: `backend/app/tasks/polling.py`
- Create: `backend/app/tasks/celery_app.py`
- Create: `backend/app/tasks/beats.py`

**Steps:**
1. Configure Celery with Redis broker and result backend
2. Periodic task: `poll_all_plants` every 5 minutes
3. Per-plant task: `poll_plant(plant_uid)` — fetches from configured sources
4. Backfill task: `backfill_plant(plant_uid, start, end)` — on-demand
5. WebSocket broadcast on new data arrival
6. Dead letter queue for failed ingestion attempts

**Celery Beat schedule:**
```python
CELERY_BEAT_SCHEDULE = {
    "poll-all-plants": {
        "task": "tasks.polling.poll_all_plants",
        "schedule": timedelta(minutes=5),
    },
    "evaluate-alerts": {
        "task": "tasks.alerts.evaluate_all_alerts",
        "schedule": timedelta(minutes=5),
    },
    "hourly-aggregation": {
        "task": "tasks.maintenance.compute_hourly_aggregates",
        "schedule": crontab(minute=5),  # 5 past every hour
    },
    "daily-quality-check": {
        "task": "tasks.maintenance.run_quality_checks",
        "schedule": crontab(hour=1, minute=0),  # 1am daily
    },
    "monthly-report-generation": {
        "task": "tasks.reports.generate_monthly_reports",
        "schedule": crontab(day_of_month=1, hour=6, minute=0),  # 1st of month, 6am
    },
}
```

---

## Phase 2 — Core Platform & UI Shell

**Duration:** 3–4 weeks
**Goal:** Build the frontend shell, authentication, navigation, and dashboard.

### Task 2.1: Authentication System

**Backend:**
- Create: `backend/app/api/v1/auth.py`
- Create: `backend/app/services/auth.py`
- Create: `backend/app/models/user.py`
- Migrate from: `services/auth_service.py`

**Frontend:**
- Create: `frontend/src/app/login/page.tsx`
- Create: `frontend/src/hooks/useAuth.ts`
- Create: `frontend/src/lib/api.ts`

**Features:**
1. JWT access tokens (15 min) + refresh tokens (7 days) stored in httpOnly cookies
2. RBAC: admin, manager, analyst, viewer (same roles as current but properly enforced)
3. Login page with branded design (no more hardcoded default credentials shown)
4. Password reset flow via email
5. Session management in Redis with token revocation
6. Audit logging for all auth events
7. SSO-ready architecture (future: Azure AD, Google Workspace)

### Task 2.2: UI Shell & Navigation

**Files:**
- Create: `frontend/src/app/layout.tsx`
- Create: `frontend/src/components/layout/Sidebar.tsx`
- Create: `frontend/src/components/layout/Header.tsx`
- Create: `frontend/src/components/layout/Breadcrumbs.tsx`
- Create: `frontend/src/components/layout/CommandPalette.tsx`

**Design principles (from competitive research):**
1. **Collapsible sidebar** with icon-only mode for maximum chart real estate
2. **Dark/light theme** toggle (default: dark — matches professional monitoring aesthetic)
3. **⌘K command palette** for power-user navigation (migrated from current Ctrl+K global search)
4. **Breadcrumb navigation** throughout: Portfolio → Plant → Analysis → Detail
5. **Notification bell** with unread badge in header
6. **User avatar menu** with role indicator

**Navigation structure:**
```
📊 Dashboard                    (landing page)
🗺️ Portfolio
   └── Plant Detail             (per-plant pages)
📈 Analysis
   ├── Fouling / Soiling
   ├── Shading
   ├── Clipping
   ├── Thermal Loss
   ├── Curtailment
   ├── Loss Waterfall
   └── Comparative
🔔 Alerts & Events
   ├── Active Alerts
   ├── Alert Rules
   └── Event History
🎫 Tickets
   ├── Board (Kanban)
   ├── My Tickets
   └── SLA Dashboard
📋 Reports
   ├── Monthly Performance
   ├── Report Builder
   ├── Scheduled Reports
   └── Report Library
🗄️ Data
   ├── Explorer
   ├── Quality Dashboard
   ├── Import
   └── Export
⚙️ Settings
   ├── Profile
   ├── Users & Roles
   ├── Integrations
   ├── Alert Configuration
   └── Preferences
```

### Task 2.3: Design System & Theme

**Files:**
- Create: `frontend/src/styles/globals.css`
- Create: `frontend/tailwind.config.ts`
- Create: `frontend/src/components/ui/` (shadcn/ui installation)

**Brand design system:**
```css
/* Unified color palette — resolves current brand inconsistency */
:root {
  /* Primary */
  --primary: 160 42% 56%;           /* #5FBFA0 — teal */
  --primary-foreground: 0 0% 100%;
  
  /* Secondary */
  --secondary: 198 53% 23%;         /* #1B4D5C — dark teal (from legacy) */
  --secondary-foreground: 0 0% 100%;
  
  /* Accent */
  --accent: 39 59% 56%;             /* #D4A84B — warm amber */
  --accent-foreground: 0 0% 10%;
  
  /* Semantic */
  --positive: 155 51% 36%;          /* #2D8B5F — green */
  --negative: 0 49% 54%;            /* #C94A4A — red */
  --warning: 39 100% 50%;           /* #FFA500 — orange */
  
  /* Background hierarchy (dark mode) */
  --background: 220 30% 7%;         /* #0B1120 — deep navy */
  --card: 220 25% 10%;              /* Slightly lighter */
  --sidebar: 220 28% 9%;            /* Sidebar background */
  --muted: 220 20% 15%;             /* Muted surfaces */
  
  /* Typography */
  --font-heading: 'Inter', sans-serif;    /* Modern, clean */
  --font-body: 'Inter', sans-serif;
  --font-mono: 'JetBrains Mono', monospace;
}
```

**Component library (shadcn/ui + custom):**
- KPICard — Large metric with trend arrow, sparkline, status color
- StatusBadge — Pill-shaped (Online/Offline/Warning/Error)
- DataTable — Sortable, filterable, paginated with row selection
- DateRangePicker — Quick presets + custom range + comparison period
- PlantSelector — Searchable multiselect with recent/favorites
- QualityBadge — Data confidence indicator (High/Medium/Low/Gap)
- ChartContainer — Wrapper with title, subtitle, actions (export, fullscreen, add-to-report)

### Task 2.4: Dashboard Page

**Files:**
- Create: `frontend/src/app/page.tsx`
- Create: `frontend/src/components/dashboard/KPICard.tsx`
- Create: `frontend/src/components/dashboard/PortfolioMap.tsx`
- Create: `frontend/src/components/dashboard/PlantStatusGrid.tsx`
- Create: `frontend/src/components/dashboard/AlertFeed.tsx`
- Create: `frontend/src/components/dashboard/GenerationChart.tsx`
- Create: `backend/app/api/v1/dashboards.py`

**Dashboard layout (inspired by Power Factors + GPM Horizon):**

```
┌──────────────────────────────────────────────────────────┐
│ PORTFOLIO OVERVIEW                      📅 Last 30 days ▼│
├──────────┬──────────┬──────────┬──────────┬──────────────┤
│ Total    │ Total PR │ Fleet    │ Active   │ Open         │
│ Gen      │          │ Avail    │ Alerts   │ Tickets      │
│ 12.4 GWh │ 82.3%   │ 98.7%   │ 3 ⚠️     │ 7            │
│ ↑ 4.2%   │ ↓ 0.8%  │ → 0.1%  │          │              │
│ vs LY    │ vs LY   │ vs LY   │          │              │
├──────────┴──────────┴──────────┴──────────┴──────────────┤
│                                                          │
│  ┌─────────────────────┐  ┌────────────────────────────┐ │
│  │  PORTFOLIO MAP       │  │  GENERATION vs BUDGET      │ │
│  │  [Leaflet/Mapbox]    │  │  [Area chart - 12 months]  │ │
│  │                      │  │                            │ │
│  │  🟢 Plant A          │  │  ████████████ Actual       │ │
│  │  🟢 Plant B          │  │  ──────────── Budget       │ │
│  │  🟡 Plant C          │  │  ╌╌╌╌╌╌╌╌╌╌╌╌ Forecast    │ │
│  │  🔴 Plant D          │  │                            │ │
│  └─────────────────────┘  └────────────────────────────┘ │
│                                                          │
│  ┌─────────────────────┐  ┌────────────────────────────┐ │
│  │  PLANT STATUS GRID   │  │  RECENT ALERTS             │ │
│  │  [Sortable table]    │  │  [Live feed - WebSocket]   │ │
│  │                      │  │                            │ │
│  │  Plant | PR | Avail  │  │  🔴 Low PR: Plant D (71%) │ │
│  │  A     | 85 | 99.2   │  │  🟡 Soiling: Plant C (4%) │ │
│  │  B     | 83 | 98.9   │  │  🟡 Curtail: Plant A       │ │
│  │  C     | 79 | 97.1   │  │                            │ │
│  │  D     | 71 | 95.3   │  │  View all alerts →         │ │
│  └─────────────────────┘  └────────────────────────────┘ │
│                                                          │
│  ┌──────────────────────────────────────────────────────┐ │
│  │  LOSS BREAKDOWN (Portfolio)          Last 30 days    │ │
│  │  [Horizontal stacked bar per plant]                  │ │
│  │                                                      │ │
│  │  Plant A: ███ Grid ██ Clip █ Soil ██ Shade           │ │
│  │  Plant B: ██ Grid █████ Clip █ Soil                  │ │
│  │  Plant C: █ Grid ██ Clip ████ Soil █████ Shade       │ │
│  └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

### Task 2.5: Portfolio & Plant Detail Pages

**Files:**
- Create: `frontend/src/app/portfolio/page.tsx`
- Create: `frontend/src/app/portfolio/[plantId]/page.tsx`
- Create: `frontend/src/components/dashboard/PortfolioMap.tsx`
- Create: `backend/app/api/v1/plants.py`

**Portfolio page:** Map-based view with plant markers colored by health status. Tabular view as alternative. Search/filter by name, capacity, status.

**Plant detail page:** Tab-based layout:
1. **Overview** — Plant KPIs, daily generation chart, current status, weather
2. **Live Data** — Real-time inverter readings (5-min updates via WebSocket)
3. **Performance** — PR trending, specific yield, budget comparison
4. **Events** — Plant-specific alerts and events timeline
5. **Tickets** — Plant-specific tickets
6. **Analysis** — Quick links to analysis modules pre-filtered by plant
7. **Data** — Raw data viewer for this plant

### Task 2.6: WebSocket Infrastructure

**Files:**
- Create: `backend/app/api/v1/websocket.py`
- Create: `backend/app/services/websocket.py`
- Create: `frontend/src/hooks/useWebSocket.ts`
- Create: `frontend/src/lib/websocket.ts`

**Channels:**
- `alerts` — New/updated alerts broadcast
- `readings:{plant_uid}` — Live data for subscribed plant
- `tickets` — Ticket status changes
- `system` — System-wide announcements

---

## Phase 3 — Analysis Engine Migration

**Duration:** 3–4 weeks
**Goal:** Migrate all 7 existing analysis modules to backend services and build corresponding frontend UIs.

### Task 3.1: Analysis Service Architecture

**Files:**
- Create: `backend/app/services/analysis/__init__.py`
- Create: `backend/app/api/v1/analysis.py`

**Common pattern for all analysis modules:**
```python
# Backend: Service + API endpoint
class AnalysisResult(BaseModel):
    plant_uid: str
    analysis_type: str
    period: DateRange
    summary: dict           # Key metrics
    chart_data: dict        # Plotly-compatible JSON
    table_data: list[dict]  # Tabular results
    quality_info: QualityInfo  # Data quality for this analysis
    computed_at: datetime

# API endpoint pattern
@router.post("/analysis/{analysis_type}")
async def run_analysis(
    analysis_type: str,
    request: AnalysisRequest,
    db: AsyncSession = Depends(get_db),
) -> AnalysisResult:
    service = get_analysis_service(analysis_type)
    return await service.analyze(request, db)
```

### Task 3.2: Fouling/Soiling Analysis Migration

**Files:**
- Create: `backend/app/services/analysis/fouling.py`
- Migrate from: `modules/fouling.py` (300 lines)
- Create: `frontend/src/app/analysis/fouling/page.tsx`

**Changes from current:**
- Replace `st.selectbox` with React PlantSelector component
- Replace `st.plotly_chart` with client-side Plotly.js rendering
- Replace DuckDB queries with PostgreSQL/TimescaleDB queries via SQLAlchemy
- Add: Soiling rate estimation (linear regression on clean periods)
- Add: Cleaning event detection and ROI calculation
- Add: Historical soiling loss trend (monthly aggregation)

### Task 3.3: Shading Analysis Migration

**Files:**
- Create: `backend/app/services/analysis/shading.py`
- Migrate from: `modules/shading.py` (639 lines)
- Create: `frontend/src/app/analysis/shading/page.tsx`

**Changes from current:**
- Replace Solar Toolkit dependency with direct pvlib sun position calculations
- Enhanced heatmap: interactive with hover detail per inverter × hour cell
- Add: Sun path diagram overlay showing horizon shading profile
- Add: Seasonal shading loss comparison (winter vs summer vs shoulder)

### Task 3.4: Clipping Analysis Migration

**Files:**
- Create: `backend/app/services/analysis/clipping.py`
- Migrate from: `modules/clipping_analysis.py` (1011 lines) + `modules/clipping_loss.py` (130 lines)
- Create: `frontend/src/app/analysis/clipping/page.tsx`

**Changes from current:**
- Merge both clipping modules into unified service
- Both detection methods preserved: Power Plateau + Power vs Irradiance Deviation
- Add: Financial impact of clipping (configurable tariff)
- Add: DC/AC ratio analysis and inverter sizing recommendation
- Replace NREL PSM3 dependency with SolarGIS API (or configurable weather source)

### Task 3.5: Thermal Loss Analysis Migration

**Files:**
- Create: `backend/app/services/analysis/thermal.py`
- Migrate from: `modules/thermal_loss.py` (300 lines)
- Create: `frontend/src/app/analysis/thermal/page.tsx`

**Changes from current:**
- Same NOCT model with configurable gamma coefficient
- Add: Temperature-corrected PR calculation
- Add: Temperature exceedance analysis (hours above threshold per month)
- Add: Comparison with SolarGIS ambient temperature for sensor validation

### Task 3.6: Curtailment Analysis Migration

**Files:**
- Create: `backend/app/services/analysis/curtailment.py`
- Migrate from: `modules/curtailment_analysis.py` (960 lines)
- Create: `frontend/src/app/analysis/curtailment/page.tsx`

**Changes from current:**
- Remove hardcoded AC capacities — read from plant registry
- Replace parquet file ingestion with database source (export limits stored in TimescaleDB)
- Add: Curtailment event timeline visualization
- Add: Revenue impact calculator with time-of-use tariffs
- Add: Curtailment prediction based on grid constraint patterns

### Task 3.7: Loss Waterfall Enhancement

**Files:**
- Create: `backend/app/services/analysis/waterfall.py`
- Migrate from: `modules/loss_waterfall.py` (486 lines) + `modules/waterfall.py` (280 lines)
- Create: `frontend/src/app/analysis/waterfall/page.tsx`
- Create: `frontend/src/components/charts/WaterfallChart.tsx`

**This is the signature visualization — make it best-in-class:**

1. **Interactive waterfall:** Click any bar to drill down into that loss category
2. **Dual mode:** Energy waterfall (kWh) and Financial waterfall (£/€/$)
3. **Comparison:** Side-by-side waterfall for two periods or two plants
4. **Standard IEC steps:** Theoretical → Grid → Availability → Inverter → Soiling → Shading → Thermal → Clipping → Degradation → Actual
5. **UK seasonal awareness preserved:** Seasonal weighting from current implementation
6. **Animated transitions** between time periods
7. **Export:** High-res PNG/SVG for reports

### Task 3.8: Comparative Analysis Migration

**Files:**
- Create: `backend/app/services/analysis/comparative.py`
- Migrate from: `modules/comparative_analysis.py` (532 lines) — **fix the sqlite3 → DuckDB bug**
- Create: `frontend/src/app/analysis/comparative/page.tsx`

**Changes from current:**
- Fix: Use PostgreSQL (not sqlite3 connecting to DuckDB!)
- All four comparison modes preserved
- Add: Weather-normalized comparison (adjust for different irradiance conditions)
- Add: Peer benchmarking with anonymous portfolio averages

### Task 3.9: New — PR Trending & Degradation Analysis

**Files:**
- Create: `backend/app/services/analysis/pr_analysis.py`
- Create: `backend/app/services/analysis/degradation.py`
- Create: `frontend/src/app/analysis/performance/page.tsx`

**New module — not in current codebase:**
1. **Weather-normalized PR trending:** Adjust PR for actual vs STC irradiance and temperature
2. **Monthly PR tracker:** Budget vs actual with variance attribution
3. **Degradation rate estimation:** Linear regression on monthly PR over multi-year period
4. **IEC 61724 compliant PR calculation** with configurable monitoring class (A/B/C)

---

## Phase 4 — Alert & Ticketing System

**Duration:** 3–4 weeks
**Goal:** Build a closed-loop alert → ticket → resolution system inspired by Power Factors Unity FSM.

### Task 4.1: Alert Engine

**Files:**
- Create: `backend/app/services/alerting/engine.py`
- Create: `backend/app/services/alerting/rules.py`
- Create: `backend/app/models/alert.py`
- Create: `backend/app/tasks/alerts.py`

**Alert types:**

| Alert Type | Description | Evaluation |
|-----------|-------------|------------|
| **Threshold** | Metric crosses a boundary (e.g., PR < 75%) | Compare latest value to threshold |
| **Trend** | Metric degrading over N days (e.g., PR dropping 2%/week) | Linear regression on rolling window |
| **Absence** | No data received for > N minutes | Check last reading timestamp |
| **Anomaly** | Statistical outlier vs historical pattern | Z-score or isolation forest |
| **Composite** | Combination of conditions (e.g., low PR AND high irradiance) | Boolean expression evaluation |
| **Scheduled** | Time-based (e.g., evening check that day's availability > 98%) | Cron-triggered evaluation |

**Alert lifecycle:**
```
OPEN → ACKNOWLEDGED → INVESTIGATING → RESOLVED → CLOSED
                    ↓
              (auto-create ticket if severity ≥ WARNING)
```

**Default alert rules (expanded from current 5):**

| Rule | Metric | Condition | Threshold | Severity |
|------|--------|-----------|-----------|----------|
| Low PR | Performance Ratio | < | 75% | WARNING |
| Very Low PR | Performance Ratio | < | 65% | CRITICAL |
| Low Availability | Availability | < | 95% | WARNING |
| Critical Availability | Availability | < | 90% | CRITICAL |
| High Soiling | Soiling Index | > | 3% | WARNING |
| High Clipping | Clipping Loss | > | 5% | INFO |
| Curtailment Active | Curtailment Event | == | true | INFO |
| Data Gap | Minutes Since Last Reading | > | 30 | WARNING |
| Data Gap Critical | Minutes Since Last Reading | > | 120 | CRITICAL |
| Inverter Offline | Inverter Status | == | offline | CRITICAL |
| PR Degradation | PR Trend (30d) | < | -2%/month | WARNING |
| Irradiance Sensor Fault | Measured vs Satellite | > | 20% deviation | WARNING |

**Celery task (runs every 5 minutes):**
```python
@celery_app.task
def evaluate_all_alerts():
    """
    1. Fetch all active alert rules
    2. For each plant with active rules:
       a. Get latest readings + computed metrics
       b. Evaluate each rule against current values
       c. If triggered:
          - Create/update alert record
          - Create notification
          - Auto-create ticket if severity >= WARNING
          - Send to configured channels (email, Slack, webhook)
       d. If previously triggered but now resolved:
          - Mark alert as RESOLVED
          - Update linked ticket
    3. Broadcast updates via WebSocket
    """
```

### Task 4.2: Alert UI

**Files:**
- Create: `frontend/src/app/alerts/page.tsx`
- Create: `frontend/src/app/alerts/rules/page.tsx`
- Create: `frontend/src/app/alerts/history/page.tsx`
- Create: `frontend/src/components/dashboard/AlertFeed.tsx`
- Create: `backend/app/api/v1/alerts.py`

**Alert dashboard layout:**
```
┌──────────────────────────────────────────────────────┐
│ ACTIVE ALERTS                   Filter: All ▼  🔍    │
├───────┬───────┬──────────────────────────────────────┤
│ 🔴 3  │ 🟡 7  │ 🔵 12  │ Total: 22 active          │
│ Crit  │ Warn  │ Info   │                            │
├───────┴───────┴──────────────────────────────────────┤
│                                                      │
│ 🔴 CRITICAL — Plant D: PR at 61.2% (thresh: 65%)    │
│    Since: 2 hours ago | Ticket: #127 (Investigating) │
│    [Acknowledge] [View Plant] [View Ticket]          │
│                                                      │
│ 🔴 CRITICAL — Plant D: Inverter INV-03 offline       │
│    Since: 3 hours ago | Ticket: #126 (Open)          │
│    [Acknowledge] [View Plant] [View Ticket]          │
│                                                      │
│ 🟡 WARNING — Plant C: Soiling at 4.2% (thresh: 3%)  │
│    Since: 1 day ago | Ticket: #125 (Scheduled)       │
│    [Acknowledge] [View Plant] [View Ticket]          │
│                                                      │
│ 🟡 WARNING — Plant A: Curtailment event active       │
│    Since: 45 minutes ago | No ticket                 │
│    [Acknowledge] [Create Ticket] [View Plant]        │
│                                                      │
└──────────────────────────────────────────────────────┘
```

### Task 4.3: Ticketing System — Backend

**Files:**
- Create: `backend/app/models/ticket.py`
- Create: `backend/app/services/ticketing/service.py`
- Create: `backend/app/services/ticketing/assignment.py`
- Create: `backend/app/services/ticketing/sla.py`
- Create: `backend/app/api/v1/tickets.py`

**Ticket data model:**
```python
class Ticket(Base):
    __tablename__ = "tickets"
    
    id: Mapped[int]                          # Auto-increment
    reference: Mapped[str]                   # Human-readable: TKT-00127
    title: Mapped[str]
    description: Mapped[str]
    
    # Classification
    category: Mapped[TicketCategory]         # PERFORMANCE, EQUIPMENT, GRID, MAINTENANCE, DATA
    priority: Mapped[TicketPriority]         # CRITICAL, HIGH, MEDIUM, LOW
    status: Mapped[TicketStatus]             # OPEN, ACKNOWLEDGED, IN_PROGRESS, ON_HOLD, RESOLVED, CLOSED
    
    # Relationships
    plant_uid: Mapped[str]                   # FK to plants
    device_id: Mapped[str | None]            # Specific device if applicable
    alert_id: Mapped[int | None]             # FK to alerts (if auto-created)
    
    # Assignment
    assigned_to: Mapped[str | None]          # User ID
    assigned_at: Mapped[datetime | None]
    
    # SLA
    sla_response_due: Mapped[datetime | None]    # When first response is due
    sla_resolution_due: Mapped[datetime | None]  # When resolution is due
    sla_responded_at: Mapped[datetime | None]
    sla_resolved_at: Mapped[datetime | None]
    sla_breached: Mapped[bool] = False
    
    # Resolution
    root_cause: Mapped[str | None]
    resolution: Mapped[str | None]
    energy_lost_kwh: Mapped[float | None]    # Estimated energy impact
    revenue_lost: Mapped[float | None]       # Estimated financial impact
    
    # Metadata
    created_by: Mapped[str]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    closed_at: Mapped[datetime | None]
    
    # Relationships
    comments: Mapped[list["TicketComment"]] = relationship()
    attachments: Mapped[list["TicketAttachment"]] = relationship()
    history: Mapped[list["TicketHistory"]] = relationship()

class TicketComment(Base):
    __tablename__ = "ticket_comments"
    
    id: Mapped[int]
    ticket_id: Mapped[int]                   # FK
    author_id: Mapped[str]
    content: Mapped[str]
    is_internal: Mapped[bool] = False        # Internal note vs visible comment
    created_at: Mapped[datetime]

class TicketAttachment(Base):
    __tablename__ = "ticket_attachments"
    
    id: Mapped[int]
    ticket_id: Mapped[int]                   # FK
    filename: Mapped[str]
    file_path: Mapped[str]                   # S3/MinIO path
    file_size: Mapped[int]
    mime_type: Mapped[str]
    uploaded_by: Mapped[str]
    uploaded_at: Mapped[datetime]

class TicketHistory(Base):
    __tablename__ = "ticket_history"
    
    id: Mapped[int]
    ticket_id: Mapped[int]                   # FK
    field: Mapped[str]                       # Which field changed
    old_value: Mapped[str | None]
    new_value: Mapped[str | None]
    changed_by: Mapped[str]
    changed_at: Mapped[datetime]
```

**SLA configuration (configurable per priority):**

| Priority | Response SLA | Resolution SLA |
|----------|-------------|----------------|
| CRITICAL | 1 hour | 4 hours |
| HIGH | 4 hours | 24 hours |
| MEDIUM | 8 hours | 72 hours |
| LOW | 24 hours | 168 hours (1 week) |

**Auto-assignment rules:**
```python
class AssignmentEngine:
    """
    Assignment priority:
    1. If plant has a designated O&M contact → assign to them
    2. If category has a default assignee → assign
    3. Round-robin among available analysts
    4. Escalate to manager if unassigned for > 1 hour
    """
```

### Task 4.4: Ticketing System — Frontend

**Files:**
- Create: `frontend/src/app/tickets/page.tsx`
- Create: `frontend/src/app/tickets/[ticketId]/page.tsx`
- Create: `frontend/src/app/tickets/new/page.tsx`
- Create: `frontend/src/components/tickets/KanbanBoard.tsx`
- Create: `frontend/src/components/tickets/TicketCard.tsx`
- Create: `frontend/src/components/tickets/TicketDetail.tsx`

**Kanban board:**
```
┌──────────────────────────────────────────────────────────┐
│ TICKETS            View: Board ▼ | Filter: All ▼  🔍    │
├──────────┬──────────┬──────────┬──────────┬──────────────┤
│ OPEN (3) │PROGRESS(2│ON HOLD(1)│RESOLVED(4│ CLOSED (12) │
│          │          │          │          │              │
│ ┌──────┐ │ ┌──────┐ │ ┌──────┐ │ ┌──────┐ │              │
│ │#127  │ │ │#124  │ │ │#119  │ │ │#123  │ │              │
│ │Low PR│ │ │Inv   │ │ │Parts │ │ │Clean │ │              │
│ │PlantD│ │ │Repair│ │ │Wait  │ │ │Done  │ │              │
│ │🔴 CRI│ │ │PlantB│ │ │PlantA│ │ │PlantC│ │              │
│ │2h ago│ │ │🟡 MED│ │ │🟡 MED│ │ │🟢 LOW│ │              │
│ └──────┘ │ └──────┘ │ └──────┘ │ └──────┘ │              │
│ ┌──────┐ │ ┌──────┐ │          │ ┌──────┐ │              │
│ │#126  │ │ │#122  │ │          │ │#121  │ │              │
│ │Inv   │ │ │Grid  │ │          │ │Therm │ │              │
│ │Offlin│ │ │Curta │ │          │ │Check │ │              │
│ │PlantD│ │ │PlantA│ │          │ │PlantB│ │              │
│ │🔴 CRI│ │ │🔵 LOW│ │          │ │🟢 LOW│ │              │
│ └──────┘ │ └──────┘ │          │ └──────┘ │              │
└──────────┴──────────┴──────────┴──────────┴──────────────┘
```

**Ticket detail page features:**
- Full ticket metadata with edit capability
- Comment thread (internal notes vs visible comments)
- File attachments (photos, PDFs, screenshots)
- Activity timeline / history
- Linked alert with current status
- Plant/device quick info panel
- SLA countdown timer
- Energy/revenue impact calculator
- Resolution form with root cause categorization

### Task 4.5: Notification Channels

**Files:**
- Create: `backend/app/services/alerting/channels.py`

**Channels:**
1. **In-app** — WebSocket push to frontend notification bell
2. **Email** — SMTP or SendGrid/SES for alert notifications
3. **Slack** — Webhook integration for team channels
4. **Webhook** — Generic HTTP POST for third-party integrations
5. **SMS** — Twilio for critical alerts (configurable)

**Notification preferences (per user):**
- Which alert severities trigger which channels
- Quiet hours (no email/SMS between 10pm–7am unless CRITICAL)
- Digest mode (batch non-critical notifications into daily summary)

---

## Phase 5 — Reporting Engine

**Duration:** 2–3 weeks
**Goal:** Enhanced reporting with automated generation, scheduling, and templates.

### Task 5.1: Report Template System

**Files:**
- Create: `backend/app/services/reporting/templates.py`
- Create: `backend/app/services/reporting/generator.py`
- Migrate from: `modules/report_generator.py` (308 lines) + `modules/report_builder.py` (512 lines) + `Monthly reporting/ui_excom_report.py` (1354 lines)

**Report types:**
1. **Monthly Owner Report** — Generation, PR, availability, loss breakdown, events, financial summary
2. **Monthly ExCom Report** — Portfolio-level with waterfall: Budget → Weather → Availability → Efficiency → Actual
3. **O&M Performance Report** — Ticket statistics, MTTR, availability by cause, maintenance schedule
4. **Investor Report** — Year-to-date performance, budget tracking, revenue projection
5. **Ad-hoc Analysis Report** — Custom assembly from analysis snapshots (current report builder pattern)
6. **Data Quality Report** — Completeness, gap analysis, sensor health

**Template engine (Jinja2 + WeasyPrint for HTML→PDF):**
```python
class ReportTemplate(Base):
    id: Mapped[int]
    name: Mapped[str]
    description: Mapped[str]
    template_html: Mapped[str]          # Jinja2 template
    default_sections: Mapped[dict]      # Section configuration
    brand_config: Mapped[dict]          # Colors, logo, fonts
    created_by: Mapped[str]
    is_system: Mapped[bool] = False     # System templates can't be deleted
```

### Task 5.2: Automated Report Scheduling

**Files:**
- Create: `backend/app/services/reporting/scheduler.py`
- Create: `backend/app/tasks/reports.py`

**Features:**
1. Schedule any report template on cron expression
2. Auto-generate on 1st of month for previous month
3. Email distribution list per report
4. Upload to S3/MinIO for archive
5. Report history with version tracking
6. Manual re-generation with date override

### Task 5.3: Report Builder UI (Enhanced)

**Files:**
- Create: `frontend/src/app/reports/builder/page.tsx`
- Create: `frontend/src/app/reports/monthly/page.tsx`
- Create: `frontend/src/app/reports/page.tsx`

**Enhanced report builder:**
- Drag-and-drop section ordering
- Live preview pane
- "Add to Report" button preserved across all analysis pages
- Section types: KPI grid, chart, table, text/commentary, page break
- Brand customization: logo, colors, header/footer
- Multi-format export: PDF, XLSX (with charts), PPTX
- Report library with search and favorites

### Task 5.4: Monthly Reporting Migration

**Files:**
- Create: `backend/app/services/reporting/monthly.py`
- Migrate from: `Monthly reporting/analysis.py` (509 lines) + `Monthly reporting/data_access.py` (764 lines) + `Monthly reporting/ui_excom_report.py` (1354 lines)

**Preserve all ExCom calculations:**
- Budget → Weather Adjusted Budget → Availability Loss → PR Loss → Actual
- Technical Loss = CalculatedExp - ActualGen
- Top/Bottom 5 ranking
- Color-coded performance bands
- Monthly heatmap

**Unify brand colors** — the legacy `brand_theme.py` colors (#1B4D5C) are merged into the unified design system.

---

## Phase 6 — Data Resilience & Quality

**Duration:** 2–3 weeks
**Goal:** Implement a cumulative data approach with fallbacks, quality scoring, and gap handling.

### Task 6.1: Data Quality Scoring

**Files:**
- Create: `backend/app/services/data_quality/scorer.py`
- Create: `backend/app/models/data_quality.py`

**Per-datapoint quality scoring:**
```python
class QualityScore(BaseModel):
    """Attached to every reading and aggregated metric."""
    
    overall: float          # 0.0–1.0 composite score
    completeness: float     # % of expected fields present
    source_reliability: float  # Based on data source hierarchy
    freshness: float        # Time since measurement vs expected interval
    plausibility: float     # Range check + rate-of-change check + physical consistency
    
    flags: list[str]        # e.g., ["interpolated", "satellite_derived", "sensor_fault_suspected"]
    source: str             # "emig", "juggle", "solargis", "interpolated", "estimated"

# Source reliability hierarchy
SOURCE_RELIABILITY = {
    "on_site_class_a": 1.00,   # IEC 61724 Class A sensor
    "emig": 0.95,              # Direct inverter API
    "solaredge": 0.95,         # Direct optimizer API
    "enphase": 0.95,           # Direct microinverter API
    "sma": 0.95,               # Direct inverter API
    "huawei": 0.95,            # Direct inverter API
    "fronius": 0.95,           # Direct inverter API
    "juggle": 0.90,            # Aggregator (adds latency, potential mapping errors)
    "solargis_satellite": 0.85,# Satellite-derived (validated but modeled)
    "interpolated": 0.70,      # Gap-filled via interpolation
    "estimated": 0.50,         # Modeled/expected value substitution
    "manual_upload": 0.80,     # User-uploaded CSV (reliability varies)
}
```

### Task 6.2: Cumulative Data Approach & Gap Filling

**Files:**
- Create: `backend/app/services/data_quality/gap_filler.py`
- Create: `backend/app/services/data_quality/harmonizer.py`

**Cumulative fallback chain (per plant, configurable):**
```
Source Priority Chain:
┌─────────────────────────┐
│ 1. Primary API (EMIG)   │ ← Best quality, device-level
│    ↓ if gap detected     │
│ 2. Secondary API (Juggle)│ ← Aggregated, slightly lower quality
│    ↓ if gap detected     │
│ 3. Satellite (SolarGIS) │ ← Always available, irradiance only
│    ↓ if no satellite     │
│ 4. Interpolation         │ ← Short gaps (<1h): linear interpolation
│    ↓ if gap too long     │
│ 5. Expected Model        │ ← PVsyst model output for the period
│    ↓ if no model         │
│ 6. Flagged Gap           │ ← Mark as missing, exclude from KPIs
└─────────────────────────┘
```

**Gap detection logic:**
```python
class GapDetector:
    """
    For each plant, based on expected data resolution (5-min, 15-min, hourly):
    1. Identify all timestamps where data is expected but missing
    2. Classify gaps: SHORT (<1h), MEDIUM (1h–24h), LONG (>24h)
    3. For SHORT gaps: auto-fill via linear interpolation
    4. For MEDIUM gaps: attempt satellite fallback, else interpolation
    5. For LONG gaps: flag and exclude from KPIs (or use expected model)
    6. All filled data points are flagged with source and quality score
    """
```

**Multi-source harmonization:**
```python
class DataHarmonizer:
    """
    When multiple sources provide data for the same timestamp:
    1. Select highest-quality source per field
    2. Cross-validate: flag if sources disagree by >10%
    3. For irradiance: prefer on-site POA sensor, fallback to satellite
    4. For power: prefer direct inverter API, fallback to meter reading
    5. Log all source selections for audit
    """
```

### Task 6.3: Data Quality Dashboard

**Files:**
- Create: `frontend/src/app/data/quality/page.tsx`
- Create: `frontend/src/components/data/QualityBadge.tsx`
- Create: `backend/app/api/v1/data_quality.py`

**Dashboard elements:**
- Per-plant data completeness heatmap (day × hour)
- Source distribution pie chart (what % from each source)
- Gap history timeline
- Quality score trend over time
- Sensor health indicators (cross-validate with satellite)
- Data freshness indicator ("last reading: 3 minutes ago")

**Quality badge displayed on every chart/KPI:**
```
┌─────────────────────────┐
│ Performance Ratio: 82.3% │
│ Quality: ████████░░ 85%  │  ← Data completeness for this metric
│ Sources: EMIG 92%, SolarGIS 8% │
└─────────────────────────┘
```

### Task 6.4: Enhanced Validation Pipeline

**Files:**
- Create: `backend/app/services/data_quality/validator.py`
- Migrate from: `services/incremental_etl.py` (350 lines)

**Validation checks (expanded from current 7 to 15):**

| Check | Description |
|-------|-------------|
| 1. Empty data | No rows returned |
| 2. Required columns | Critical fields present |
| 3. Null percentage | Per-column null rate > threshold |
| 4. Duplicate rows | Exact timestamp duplicates |
| 5. Date validity | Timestamps in valid range, monotonically increasing |
| 6. Schema validation | Pydantic model conformance |
| 7. Numeric ranges | Values within physical limits |
| 8. **Rate of change** | Detect impossible power ramps (>rated kW/sec) |
| 9. **Night-time power** | Power > 0 when sun is below horizon |
| 10. **Irradiance consistency** | GHI ≤ extraterrestrial irradiance |
| 11. **Temperature consistency** | Ambient temp within ±50°C of regional norms |
| 12. **Stuck sensor** | Same value repeated for > N intervals |
| 13. **Timezone validation** | Detect UTC/local timezone mismatches |
| 14. **Capacity exceedance** | Power > rated capacity of plant/device |
| 15. **Cross-sensor validation** | Compare irradiance sensor vs satellite data |

---

## Phase 7 — Advanced Features

**Duration:** 4–6 weeks
**Goal:** Add differentiating features that elevate the platform beyond standard monitoring.

### Task 7.1: Anomaly Detection (ML-based)

**Files:**
- Create: `backend/app/services/analysis/anomaly.py`

**Approach:**
- Isolation Forest for multivariate anomaly detection on inverter-level data
- LSTM/Prophet for PR trend forecasting and deviation alerting
- Training on per-plant historical data (minimum 6 months required)
- Alert integration: anomalies auto-create INFO/WARNING alerts
- **Not a black box:** Show which features contributed to anomaly score

### Task 7.2: Forecasting Integration

**Files:**
- Create: `backend/app/services/forecasting/`

**Features:**
- SolarGIS Forecast API integration (14-day power output forecast)
- Day-ahead generation forecast for trading/dispatch
- Budget vs forecast vs actual on dashboard
- Forecast accuracy tracking (RMSE, MAE, MBE)

### Task 7.3: Financial Module

**Files:**
- Create: `backend/app/services/financial/`
- Create: `frontend/src/app/financial/page.tsx`

**Features:**
- Revenue tracking: actual vs budget per plant
- Tariff management: PPA, FiT, merchant, time-of-use profiles
- Financial loss attribution: £/$/€ impact per loss category
- O&M cost tracking and cost-per-MWh calculation
- ROI dashboard for cleaning/maintenance decisions

### Task 7.4: PWA & Mobile Optimization

**Steps:**
1. Next.js PWA plugin with service worker
2. Offline reading cache (last 24h of data)
3. Push notifications via browser Push API
4. Responsive layouts optimized for tablet (field engineer use case)
5. "Add to Home Screen" prompt

### Task 7.5: PVsyst Model Import

**Files:**
- Create: `backend/app/services/pvsyst/`

**Features:**
- Import PVsyst report (CSV/JSON export)
- Auto-map to plant configuration
- Expected vs actual comparison with weather normalization
- Monthly variance analysis: where does the model diverge from reality?

### Task 7.6: Module-Based Access Control

**Features:**
- Configurable module access per role/user
- Tiered feature gates: Basic → Professional → Enterprise
- Usage analytics per module (which features are used most)

### Task 7.7: API for External Consumers

**Files:**
- Create: `backend/app/api/v1/external.py`

**Features:**
- API key management (enhanced from current simulated endpoints — now real!)
- Rate limiting per key (token bucket via Redis)
- OpenAPI documentation auto-generated from FastAPI
- Webhook subscriptions for alerts and events
- Data export API (readings, KPIs, reports)

---

## Phase 8 — Polish, Testing & Launch

**Duration:** 2–3 weeks
**Goal:** Testing, performance optimization, documentation, and deployment.

### Task 8.1: End-to-End Testing

**Files:**
- Create: `frontend/e2e/`
- Create: `backend/tests/`

**Testing strategy:**
- **Backend unit tests:** pytest with factory_boy for test data, 80%+ coverage target
- **Backend integration tests:** TestClient with real TimescaleDB (Docker)
- **Frontend unit tests:** Vitest + React Testing Library
- **E2E tests:** Playwright for critical flows (login, dashboard, create ticket, run analysis, generate report)
- **Load testing:** Locust for API performance benchmarks

### Task 8.2: Performance Optimization

**Targets:**
- Dashboard load: < 2s
- Analysis computation: < 5s for 1 year of 5-min data
- Chart rendering: < 500ms
- API p95 latency: < 200ms for reads, < 1s for analysis
- WebSocket reconnect: < 3s

**Strategies:**
- TimescaleDB continuous aggregates for pre-computed hourly/daily/monthly rollups
- Redis caching for dashboard KPIs (30s TTL)
- Chart data pagination (load 30 days, lazy-load more)
- React Server Components for initial page load
- Image optimization (next/image)
- Code splitting per route

### Task 8.3: Documentation

**Files:**
- Create: `docs/api/README.md`
- Create: `docs/architecture/decisions.md`
- Create: `docs/runbooks/deployment.md`
- Create: `docs/runbooks/troubleshooting.md`
- Create: `CONTRIBUTING.md`

### Task 8.4: Deployment

**Docker Compose production stack:**
```yaml
services:
  api:
    build: ./backend
    depends_on: [db, redis]
    environment:
      - DATABASE_URL=postgresql+asyncpg://...
      - REDIS_URL=redis://redis:6379/0
    ports: ["8000:8000"]
    
  worker:
    build: ./backend
    command: celery -A app.tasks.celery_app worker -l info -c 4
    depends_on: [db, redis]
    
  beat:
    build: ./backend
    command: celery -A app.tasks.celery_app beat -l info
    depends_on: [db, redis]
    
  flower:
    build: ./backend
    command: celery -A app.tasks.celery_app flower
    ports: ["5555:5555"]
    
  frontend:
    build: ./frontend
    depends_on: [api]
    ports: ["3000:3000"]
    
  db:
    image: timescale/timescaledb:latest-pg16
    volumes: ["pgdata:/var/lib/postgresql/data"]
    ports: ["5432:5432"]
    
  redis:
    image: redis:7-alpine
    volumes: ["redisdata:/data"]
    
  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    volumes: ["miniodata:/data"]
    ports: ["9000:9000", "9001:9001"]

volumes:
  pgdata:
  redisdata:
  miniodata:
```

---

## Data Model

### Entity Relationship Diagram

```
┌────────────┐     ┌──────────────┐     ┌───────────────┐
│   plants   │────<│   devices    │     │  data_sources  │
│            │     │              │     │               │
│ uid (PK)   │     │ id (PK)      │     │ id (PK)       │
│ name       │     │ plant_uid(FK)│     │ plant_uid(FK) │
│ alias      │     │ device_type  │     │ source_type   │
│ lat/lng    │     │ name         │     │ api_key_enc   │
│ capacity_dc│     │ rated_power  │     │ poll_interval │
│ capacity_ac│     │ serial_number│     │ priority      │
│ tilt       │     │ is_active    │     │ is_active     │
│ azimuth    │     └──────────────┘     └───────────────┘
│ commissione│          │                       │
│ timezone   │          │                       │
│ tariff_rate│     ┌────┴───────────────────────┘
│ om_contact │     │
└────────────┘     │
      │       ┌────┴──────────┐     ┌──────────────────┐
      │       │   readings    │     │  data_quality     │
      │       │  (hypertable) │     │  (per-reading)    │
      │       │               │     │                  │
      │       │ timestamp(PK) │────<│ reading_id (FK)  │
      │       │ plant_uid(PK) │     │ quality_score    │
      │       │ device_id     │     │ source           │
      │       │ power_kw      │     │ flags (JSONB)    │
      │       │ energy_kwh    │     │ completeness     │
      │       │ irr_poa_wm2   │     └──────────────────┘
      │       │ irr_ghi_wm2   │
      │       │ amb_temp_c    │
      │       │ mod_temp_c    │
      │       │ wind_speed_ms │
      │       │ voltage_v     │
      │       │ current_a     │
      │       │ export_kw     │
      │       │ grid_limit_kw │
      │       │ source        │
      │       │ quality_score │
      │       └───────────────┘
      │
      │       ┌───────────────┐     ┌──────────────────┐
      ├──────<│  alert_rules  │     │  alert_history   │
      │       │               │────<│                  │
      │       │ id (PK)       │     │ id (PK)          │
      │       │ plant_uid(FK) │     │ rule_id (FK)     │
      │       │ name          │     │ triggered_at     │
      │       │ metric        │     │ value            │
      │       │ condition     │     │ severity         │
      │       │ threshold     │     │ status           │
      │       │ severity      │     │ resolved_at      │
      │       │ is_active     │     │ ticket_id (FK)   │
      │       └───────────────┘     └──────────────────┘
      │
      │       ┌───────────────┐     ┌──────────────────┐
      ├──────<│   tickets     │────<│ ticket_comments  │
      │       │               │     │                  │
      │       │ id (PK)       │────<│ ticket_id (FK)   │
      │       │ reference     │     │ author_id        │
      │       │ title         │     │ content          │
      │       │ category      │     └──────────────────┘
      │       │ priority      │     ┌──────────────────┐
      │       │ status        │────<│ticket_attachments│
      │       │ plant_uid(FK) │     │                  │
      │       │ device_id     │     │ ticket_id (FK)   │
      │       │ alert_id (FK) │     │ file_path        │
      │       │ assigned_to   │     └──────────────────┘
      │       │ sla_*         │     ┌──────────────────┐
      │       │ root_cause    │────<│ ticket_history   │
      │       │ resolution    │     │                  │
      │       │ energy_lost   │     │ ticket_id (FK)   │
      │       │ revenue_lost  │     │ field            │
      │       └───────────────┘     │ old/new_value    │
      │                             └──────────────────┘
      │
      │       ┌───────────────┐
      ├──────<│  solar_data   │     (monthly aggregated — migrated from legacy)
      │       │               │
      │       │ id (PK)       │
      │       │ plant_uid(FK) │
      │       │ date          │
      │       │ pr            │
      │       │ irradiance    │
      │       │ energy        │
      │       │ availability  │
      │       │ budget_*      │
      │       │ losses_*      │
      │       └───────────────┘
      │
┌─────┴──────┐ ┌───────────────┐ ┌──────────────────┐
│   users    │ │ notifications │ │   audit_log      │
│            │ │               │ │                  │
│ id (PK)   │ │ id (PK)       │ │ id (PK)          │
│ username   │ │ user_id (FK)  │ │ user_id (FK)     │
│ email      │ │ title         │ │ action           │
│ full_name  │ │ message       │ │ details (JSONB)  │
│ password   │ │ type          │ │ ip_address       │
│ role       │ │ data (JSONB)  │ │ timestamp        │
│ permissions│ │ is_read       │ └──────────────────┘
│ is_active  │ │ created_at    │
└────────────┘ └───────────────┘
```

### TimescaleDB-Specific

```sql
-- Create hypertable for time-series readings
SELECT create_hypertable('readings', 'timestamp',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);

-- Continuous aggregates (replace materialized views)
CREATE MATERIALIZED VIEW readings_hourly
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', timestamp) AS bucket,
    plant_uid,
    AVG(power_kw) AS avg_power_kw,
    SUM(energy_kwh) AS total_energy_kwh,
    AVG(irr_poa_wm2) AS avg_irradiance,
    AVG(amb_temp_c) AS avg_ambient_temp,
    AVG(quality_score) AS avg_quality_score,
    COUNT(*) AS reading_count
FROM readings
GROUP BY bucket, plant_uid
WITH NO DATA;

-- Add refresh policy
SELECT add_continuous_aggregate_policy('readings_hourly',
    start_offset => INTERVAL '3 days',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour'
);

-- Daily aggregate
CREATE MATERIALIZED VIEW readings_daily
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', timestamp) AS bucket,
    plant_uid,
    AVG(power_kw) AS avg_power_kw,
    MAX(power_kw) AS peak_power_kw,
    SUM(energy_kwh) AS total_energy_kwh,
    AVG(irr_poa_wm2) AS avg_irradiance,
    SUM(CASE WHEN irr_poa_wm2 > 50 THEN irr_poa_wm2 / 1000.0 ELSE 0 END) AS insolation_kwh_m2,
    AVG(amb_temp_c) AS avg_ambient_temp,
    AVG(quality_score) AS avg_quality_score,
    COUNT(*) AS reading_count,
    COUNT(*) FILTER (WHERE quality_score >= 0.8) AS high_quality_count
FROM readings
GROUP BY bucket, plant_uid
WITH NO DATA;

-- Monthly aggregate
CREATE MATERIALIZED VIEW readings_monthly
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 month', timestamp) AS bucket,
    plant_uid,
    SUM(energy_kwh) AS total_energy_kwh,
    AVG(CASE WHEN irr_poa_wm2 > 50 THEN power_kw / NULLIF(irr_poa_wm2, 0) ELSE NULL END) AS avg_pr_proxy,
    SUM(CASE WHEN irr_poa_wm2 > 50 THEN irr_poa_wm2 / 1000.0 ELSE 0 END) AS total_insolation,
    AVG(quality_score) AS avg_quality_score,
    COUNT(*) AS reading_count
FROM readings
GROUP BY bucket, plant_uid
WITH NO DATA;

-- Retention policy (optional — keep 5 years of raw, 10 years of aggregates)
SELECT add_retention_policy('readings', INTERVAL '5 years');

-- Compression (after 30 days, compress raw readings)
ALTER TABLE readings SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'plant_uid',
    timescaledb.compress_orderby = 'timestamp DESC'
);
SELECT add_compression_policy('readings', INTERVAL '30 days');
```

---

## API Integration Specifications

### Unified Adapter Interface

Every data source adapter must implement:

```python
class DataSourceAdapter(Protocol):
    source_name: str
    
    async def authenticate(self) -> bool
    async def list_plants(self) -> list[PlantInfo]
    async def fetch_readings(self, plant_uid: str, start: datetime, end: datetime) -> ReadingBatch
    async def health_check(self) -> HealthStatus
    async def get_rate_limits(self) -> RateLimitInfo
```

### Platform-Specific Integration Notes

| Platform | Auth Method | Resolution | Rate Limit | Key Notes |
|----------|------------|------------|------------|-----------|
| **EMIG** | API Key (header) | 5-min | Unknown — implement conservative 60 req/min | Existing integration — async migration |
| **Juggle** | OAuth2 / API Key | Configurable | TBD — research their developer docs | Device tree navigation, virtual meters |
| **SolarGIS** | API Key | 15-min | 1000 req/day (standard plan) | Satellite irradiance — primary fallback source |
| **SMA** | OAuth2 (Sunny Portal) | 5-min | 300 req/15min | Transitioning to ennexOS API |
| **Enphase** | OAuth2 (v4 API) | 5-min | 10,000 req/day | Panel-level data via microinverters |
| **SolarEdge** | API Key | 15-min | Varies by plan | Module-level via power optimizers |
| **Huawei** | OAuth2 (Northbound) | 5-min | TBD | FusionSolar platform, SmartPVMS |
| **Fronius** | API Key | 5-min | Unknown | Solar.web API, hybrid inverter support |
| **NREL PSM3** | API Key (free) | Hourly | 1000 req/hour | Weather data for PV modeling (pvlib) |

### Data Source Configuration (per plant)

```python
class PlantDataSourceConfig(BaseModel):
    """Configurable per plant — stored in data_sources table."""
    
    plant_uid: str
    source_type: str              # "emig", "juggle", "solargis", etc.
    priority: int                 # 1 = primary, 2 = secondary, 3 = tertiary
    api_credentials: dict         # Encrypted credentials
    poll_interval_minutes: int    # Default: 5
    device_mapping: dict          # Map source device IDs to our device IDs
    field_mapping: dict | None    # Custom field mapping overrides
    is_active: bool
    last_successful_poll: datetime | None
    consecutive_failures: int = 0
    
    # Fallback behavior
    auto_fallback: bool = True    # If this source fails, try next priority
    gap_threshold_minutes: int = 30  # After this many minutes, try fallback
```

---

## UI/UX Design System

### Design Philosophy

**Inspired by:** Power Factors Unity (professional, data-dense) + Linear (clean, fast, keyboard-driven) + Vercel Dashboard (modern, dark, polished)

**Core principles:**
1. **Exception-based monitoring** — Quiet when things are fine, loud when they're not
2. **Progressive disclosure** — Portfolio → Plant → Device → Reading
3. **Data confidence everywhere** — Every number shows its quality score
4. **Keyboard-first power users** — ⌘K palette, keyboard shortcuts throughout
5. **Dark mode default** — Professional monitoring aesthetic, reduces eye strain for control room use
6. **Dense but not cluttered** — Show more data, less chrome

### Typography

```
Headings: Inter 600 (Semi-Bold)
Body: Inter 400 (Regular)
Monospace (data/numbers): JetBrains Mono 400
KPI large numbers: Inter 700, 36px
```

### Component Design Standards

**KPI Cards:**
```
┌─────────────────────────┐
│ Total Generation        │  ← Label (12px, muted)
│ 12.4 GWh               │  ← Value (36px, white, JetBrains Mono)
│ ↑ 4.2% vs last year    │  ← Change (14px, green/red)
│ ▁▂▃▄▅▆▇█▇▆▅▄▃▂▁        │  ← Sparkline (30px height)
│ Quality: ████████░░ 85% │  ← Quality indicator (10px)
└─────────────────────────┘
```

**Status colors:**
```
Online/Healthy:    #2D8B5F (green)
Warning/Degraded:  #F59E0B (amber)
Error/Critical:    #C94A4A (red)
Offline/Unknown:   #6B7280 (gray)
Info:              #3B82F6 (blue)
```

**Chart palette (8 colors, colorblind-safe):**
```
#5FBFA0  — Primary teal (generation/power)
#3B82F6  — Blue (irradiance)
#F59E0B  — Amber (temperature)
#C94A4A  — Red (losses)
#8B5CF6  — Purple (budget/forecast)
#EC4899  — Pink (availability)
#10B981  — Emerald (PR)
#6366F1  — Indigo (comparison)
```

### Responsive Breakpoints

```
Mobile:  < 768px   (single column, stacked cards)
Tablet:  768-1024px (2-column grid, collapsed sidebar)
Desktop: > 1024px   (full layout, expanded sidebar)
Monitor: > 1440px   (3-column dashboard, data-dense mode)
```

### Animation Guidelines

- Page transitions: 200ms ease-out slide
- Chart animations: 500ms ease-in-out on data load
- Hover effects: 150ms ease
- Alert pulse: 2s infinite for new critical alerts
- Loading states: Skeleton screens (never blank), shimmer effect

---

## Risk Register

| # | Risk | Impact | Likelihood | Mitigation |
|---|------|--------|------------|------------|
| 1 | TimescaleDB learning curve | Medium | Medium | Prototype with Docker in Phase 0, team training on hypertables + continuous aggregates |
| 2 | React frontend doubles codebase size | High | High | Use shadcn/ui for pre-built components, hire/contract frontend developer |
| 3 | API rate limits from inverter platforms | Medium | High | Implement adaptive polling intervals, cache aggressively, batch requests |
| 4 | Data migration from DuckDB loses data | Critical | Low | Automated migration script with row count validation, keep DuckDB backup |
| 5 | Celery complexity for small team | Medium | Medium | Start with basic periodic tasks, add complexity incrementally |
| 6 | Multiple API credentials management | Medium | Medium | Encrypted credential storage, per-plant configuration UI |
| 7 | Frontend/backend API contract drift | Medium | Medium | OpenAPI spec auto-generated from FastAPI, TypeScript client generation |
| 8 | Existing analysis module accuracy lost in migration | High | Medium | Port Python logic directly (no rewrite), compare outputs against Streamlit version |
| 9 | SolarGIS API costs at scale | Medium | Low | Cache satellite data aggressively (data doesn't change), use only for gap-filling |
| 10 | Scope creep across 8 phases | High | High | Strict phase gating, demo/review at end of each phase, cut scope if behind |

---

## Timeline Summary

| Phase | Name | Duration | Cumulative |
|-------|------|----------|------------|
| 0 | Foundation & Infrastructure | 1–2 weeks | Week 2 |
| 1 | Data Layer & API Integrations | 3–4 weeks | Week 6 |
| 2 | Core Platform & UI Shell | 3–4 weeks | Week 10 |
| 3 | Analysis Engine Migration | 3–4 weeks | Week 14 |
| 4 | Alert & Ticketing System | 3–4 weeks | Week 18 |
| 5 | Reporting Engine | 2–3 weeks | Week 21 |
| 6 | Data Resilience & Quality | 2–3 weeks | Week 24 |
| 7 | Advanced Features | 4–6 weeks | Week 30 |
| 8 | Polish, Testing & Launch | 2–3 weeks | Week 33 |

**Total estimated duration:** 6–8 months for a single developer, 3–4 months with a team of 2–3.

### Milestone Deliverables

| Week | Milestone | Demo-able |
|------|-----------|-----------|
| 2 | Docker Compose stack running, empty dashboard | ✅ Stack boots |
| 6 | Live data flowing from EMIG + Juggle, readings in TimescaleDB | ✅ Data arrives |
| 10 | Dashboard, portfolio map, plant detail pages, auth working | ✅ Full navigation |
| 14 | All 7 analysis modules functional in new UI | ✅ Parity with Streamlit |
| 18 | Alerts firing, tickets auto-created, Kanban board, SLA tracking | ✅ Ops workflow |
| 21 | Monthly reports auto-generated, report builder, scheduling | ✅ Reporting parity+ |
| 24 | Data quality scoring, gap filling, multi-source harmonization | ✅ Data resilience |
| 30 | Anomaly detection, forecasting, financial module, PWA | ✅ Advanced features |
| 33 | E2E tests passing, performance targets met, documentation complete | ✅ **Launch-ready** |

---

## Migration Strategy

### Parallel Running

During development, the existing Streamlit app continues to run. Migration is not a big-bang cutover:

1. **Phase 0–2:** New platform developed in parallel. Streamlit app is production.
2. **Phase 3:** Analysis modules available in both platforms. Users validate accuracy.
3. **Phase 4–5:** New features (ticketing, enhanced reporting) only on new platform. Users begin migration.
4. **Phase 6–8:** Streamlit app deprecated. All users on new platform.
5. **Post-launch:** Streamlit app archived. Legacy code removed.

### Data Continuity

- DuckDB → TimescaleDB migration script runs once
- Both platforms read from TimescaleDB after Phase 1
- Streamlit app gets a `db_utils.py` shim that reads from PostgreSQL instead of DuckDB
- No data loss at any point

---

*End of plan. This document is the source of truth for the transformation project.*
