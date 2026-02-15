# Solar Portfolio Manager — Comprehensive Codebase Report

> **Generated:** June 2025  
> **Version:** 1.1.0  
> **Codebase root:** `/Users/peterhall/Documents/GitHub/Unified app`

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [API Integrations & External Services](#2-api-integrations--external-services)
3. [Analysis Modules](#3-analysis-modules)
4. [UI Structure & Navigation](#4-ui-structure--navigation)
5. [Authentication System](#5-authentication-system)
6. [Data Pipeline](#6-data-pipeline)
7. [Reporting Capabilities](#7-reporting-capabilities)
8. [Notification & Alert System](#8-notification--alert-system)
9. [Database Schema Patterns](#9-database-schema-patterns)
10. [What Works Well](#10-what-works-well)
11. [Gaps & Limitations](#11-gaps--limitations)
12. [External Services & APIs Referenced](#12-external-services--apis-referenced)
13. [File Inventory](#13-file-inventory)

---

## 1. Architecture Overview

### High-Level Design

The application is a **Streamlit-based solar portfolio management platform** branded for **AMPYR Energy**. It consolidates two legacy sub-projects — "Solar Toolkit" (operational data) and "Monthly Reporting" (financial/ExCom-level analytics) — into a single unified interface.

```
┌─────────────────────────────────────────────────────┐
│                    app.py (entry)                    │
│        PAGE_REGISTRY → lazy importlib loading        │
├─────────┬───────────────┬───────────────────────────┤
│ components/             │ modules/                   │
│  sidebar, auth_ui,      │  dashboard, plant_mgmt,   │
│  notifications_ui,      │  fouling, shading,         │
│  global_search, ux,     │  clipping, thermal,        │
│  keyboard_shortcuts,    │  curtailment, waterfall,   │
│  preferences_ui,        │  monthly_reporting,        │
│  report_button,         │  report_builder,           │
│  data_health,           │  comparative_analysis,     │
│  job_monitor,           │  data_explorer,            │
│  contextual_help        │  data_overview,            │
│                         │  database_viewer,          │
│                         │  data_export_ui,           │
│                         │  api_management_ui,        │
│                         │  poa_import,               │
│                         │  loss_waterfall,           │
│                         │  clipping_loss,            │
│                         │  system_health,            │
│                         │  chart_utils,              │
│                         │  report_generator          │
├─────────────────────────┴───────────────────────────┤
│                    services/                         │
│  toolkit_bridge, reporting_bridge, api_service,      │
│  auth_service, background_jobs, cache_layer,         │
│  db_utils, error_handler, export_service,            │
│  incremental_etl, legacy_toolkit, materialized_views,│
│  notification_service, observability,                │
│  user_preferences                                    │
├─────────────────────────────────────────────────────┤
│                    Legacy Sub-Projects               │
│  Solar Toolkit/    Monthly reporting/                 │
│  (orchestrator,    (analysis, data_access,           │
│   data_viewer)      ui_excom_report, brand_theme)    │
├─────────────────────────────────────────────────────┤
│                    Data Layer                         │
│  DuckDB (unified)  SQLite (auth, notifications, API) │
└─────────────────────────────────────────────────────┘
```

### Technology Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| **Web Framework** | Streamlit | ≥1.52 |
| **Runtime** | Python | ≥3.11 (target 3.12) |
| **Primary Database** | DuckDB | ≥1.0 / 1.4 |
| **Auth/Notification DB** | SQLite | stdlib |
| **Visualization** | Plotly | ≥6.5 |
| **PDF Generation** | ReportLab | ≥4.4 |
| **Solar Modelling** | pvlib | ≥0.13 |
| **Data Processing** | pandas ≥2.3, numpy ≥2.4, pyarrow ≥22.0 |
| **Validation** | pydantic ≥2.12 |
| **Logging** | structlog ≥25.5 |
| **Auth Crypto** | bcrypt, PyJWT, cryptography |
| **Image Export** | kaleido ≥1.0 |
| **Fuzzy Search** | fuzzywuzzy |
| **Deployment** | Docker (python:3.12-slim), docker-compose |

### Configuration System

Three-tier environment config (`app_config/`):

- **`base.py`** — defaults for all environments (DB paths, API keys, fiscal defaults, chart colors)
- **`development.py`** — debug logging, verbose SQL
- **`staging.py`** — moderate settings
- **`production.py`** — optimized caching, JSON logging, background jobs enabled

Environment selection via `ENVIRONMENT` env var (default: `development`). The `.env` file provides runtime overrides for `TOOLKIT_DB_PATH`, `REPORTING_DB_PATH`, `EMIG_API_KEY`, `NREL_API_KEY`, and feature flags (`use_cached_views`, `enable_background_jobs`, `enable_observability`).

`unified_config.py` wraps `app_config` for backward compatibility, providing `config.get_css()` and `config.get_page_config()`.

### Database Unification Strategy

Both legacy sub-projects originally used separate databases. The unified app points both `TOOLKIT_DB` and `REPORTING_DB` to the same `plant_registry.duckdb` file at `~/.solar_toolkit/plant_registry.duckdb` (or a Google Drive sync path if `GOOGLE_DRIVE_SYNC_PATH` is set).

SQLite is used separately for three auxiliary concerns:
- `users.db` — authentication and sessions
- `notifications.db` — notifications and alerts
- `api.db` — API key management

---

## 2. API Integrations & External Services

### EMIG API (Primary Data Source)

- **Purpose:** Fetch real-time and historical inverter/irradiance readings from EMIG-monitored solar plants.
- **Authentication:** `EMIG_API_KEY` (env var, also checks `JUGGLE_API_KEY` for backward compatibility).
- **Usage:** `ToolkitBridge.fetch_readings(plant_uid, start_date, end_date)` via `solar_toolkit.emig_api.EmigApiClient`.
- **Data Flow:** API → raw JSON → pandas DataFrame → DuckDB `readings` table.
- **Incremental Pull:** Plant Management page supports "Bulk Smart Update" which auto-detects the latest timestamp per site and fetches only new data.

### NREL PSM3 (Weather/Solar Resource Data)

- **Purpose:** Fetch satellite-derived weather data for clipping loss twin simulations.
- **Authentication:** `NREL_API_KEY` (free tier via `DEMO_KEY`; sign-up at developer.nrel.gov).
- **Usage:** `clipping_loss.py` module calls `orch.run_clipping_analysis()` with the NREL key and email.
- **Data:** Provides GHI/DHI/DNI irradiance for PV modelling via pvlib.

### SolarGIS (POA Irradiance)

- **Purpose:** Import Plane-of-Array irradiance data from SolarGIS exports.
- **Integration:** File-based import via `poa_import.py` (CSV upload or folder scan). Fuzzy-matches filenames to registered plant aliases using `difflib.SequenceMatcher`.
- **Not a live API** — requires manual file export from SolarGIS portal.

### Export Limit Data

- **Purpose:** Grid curtailment/export limitation data.
- **Source:** Parquet files in `data/export_limits/` folder, ingested by `export_limit_crawler.ExportLimitClient`.
- **Usage:** `curtailment_analysis.py` loads these for curtailment event detection and financial impact calculation.

### Google Drive (Optional Sync)

- **Purpose:** Cross-device database synchronization.
- **Config:** `GOOGLE_DRIVE_SYNC_PATH` env var points to a Google Drive folder.
- **Implementation:** Simply changes the DuckDB file path — no Google Drive API integration. Relies on Google Drive desktop client syncing the file.

### Internal "API" Endpoints (Simulated)

`services/api_service.py` defines REST-like endpoints (`GET /api/plants`, `GET /api/metrics`, `POST /api/export`) but these are **not actual HTTP endpoints**. They are Python method calls with OpenAPI-like documentation. The API Management UI generates API keys and shows docs, but the endpoints would need a separate web server (e.g., FastAPI) to actually serve HTTP requests.

---

## 3. Analysis Modules

### 3.1 Fouling / Soiling Analysis (`modules/fouling.py`)

- Calculates soiling/fouling index over time.
- Uses `AnalysisOrchestrator.run_fouling_analysis_from_db()` or CSV upload.
- Outputs: fouling index trend chart, PR vs irradiance scatter, daily summary table.
- Auto-clean period detection or manual clean date range selection.

### 3.2 Shading Analysis (`modules/shading.py`)

- Compares summer baseline to winter performance to estimate shading losses.
- Uses `solar_toolkit.shading_analysis` module.
- Outputs: heatmap by inverter × hour, per-inverter efficiency comparison.
- Classification: No Shading (≥0.95), Mild (0.85–0.95), Moderate (0.70–0.85), Severe (<0.70).

### 3.3 Clipping Analysis (`modules/clipping_analysis.py`, 1011 lines)

- **First-principles inverter clipping detection** from operational data.
- Two methods:
  1. Power Plateau Detection — identifies sustained power capping.
  2. Power vs Irradiance Deviation — detects divergence from linear response.
- Auto-detects power/irradiance columns and units (kW vs W, kW/m² vs W/m²).
- Aggregates site-level power across all inverters.
- Configurable thresholds: plateau %, min irradiance, flatness tolerance.

### 3.4 Clipping Loss (Twin Simulation) (`modules/clipping_loss.py`)

- **Model-based clipping estimation** using pvlib.
- Runs twin simulations: constrained (real inverter) vs unconstrained (unlimited inverter).
- Fetches NREL PSM3 weather data for the selected year.
- User configures inverter specs (rated AC, max DC, efficiency) and module specs (temp coefficient).
- Outputs: unconstrained energy vs actual, clipping loss %, daily profile of worst clipping day.

### 3.5 Thermal Loss Analysis (`modules/thermal_loss.py`)

- Cell temperature estimation using NOCT model: $T_{cell} = T_{amb} + \frac{NOCT - 20}{800} \times POA$.
- Thermal loss with configurable gamma coefficient (default: −0.4 %/°C).
- Requires POA irradiance, ambient temperature, and power device selections.

### 3.6 Curtailment Analysis (`modules/curtailment_analysis.py`, 960 lines)

- Analyzes grid export curtailment from parquet-based export limit data.
- Statistics: curtailment events, lost energy (upper bound MWh), financial impact (configurable tariff, default GBP/kWh).
- Temporal pattern analysis: hourly, daily, monthly curtailment heatmaps.
- Hardcoded AC capacities for known plants (e.g., Newfold Farm = 8050 kW).

### 3.7 Loss Waterfall (`modules/loss_waterfall.py`, 486 lines)

- Orchestrates multiple loss components into a unified waterfall chart.
- **UK-specific seasonal logic** via `SEASONAL_CONFIG`:
  - Clipping: Apr–Sep (high irradiance months)
  - Thermal: May–Sep (warm weather, >25°C)
  - Shading: Oct–Feb (low sun angle)
  - Fouling: year-round
  - Curtailment: year-round
  - Availability: year-round
- Calls individual analysis functions and aggregates results.

### 3.8 Waterfall (Reporting) (`modules/waterfall.py`)

- Loss waterfall visualization based on monthly reporting data.
- Column mapping UI with auto-detection from the column map (COLMAP).
- Time aggregation: Daily/Weekly/Monthly/Quarterly/YTD/Annual.
- Group-by dimension support for multi-site waterfalls.

### 3.9 Comparative Analysis (`modules/comparative_analysis.py`, 532 lines)

- Cross-plant comparison dashboard with 4 analysis types:
  1. **Plant Comparison** — side-by-side metrics for up to 5 plants
  2. **Time Period Comparison** — compare same plant across periods
  3. **Metric Comparison** — correlate different metrics
  4. **Portfolio Overview** — geographic distribution, fleet-level stats
- Note: uses direct `sqlite3` connections to TOOLKIT_DB, which is actually a DuckDB file — this is a **bug** (should use DuckDB).

### 3.10 Monthly Performance (`modules/monthly_reporting.py`, 852 lines)

- Executive report generation importing from legacy Monthly Reporting modules.
- Sections: Top/Bottom 5 performance ranking, Technical Loss Heatmap (12 months), Shading Analysis, Soiling Analysis.
- Date format: "Mon-YY" (e.g., "Jan-24").
- Calculates Technical Loss if not in DB: $TechnicalLoss = CalculatedExp - ActualGen$.

### 3.11 Chart Utilities (`modules/chart_utils.py`)

- Shared Plotly chart creation functions:
  - `create_shading_chart()` — scatter plot with diverging RdYlGn colorscale
  - `create_soiling_chart()` — loss line chart
  - `create_heatmap_chart()` — divergent heatmap centered at zero with symmetric range

---

## 4. UI Structure & Navigation

### Entry Point (`app.py`)

- Sets Streamlit page config (wide layout, AMPYR favicon).
- Applies CSS theme via `styles.apply_theme()`.
- Initializes services: preferences, error handler, global search, keyboard shortcuts.
- Renders sidebar via `components.render_sidebar()`.
- **PAGE_REGISTRY** maps 18 page names to `(module_path, function_name)` tuples.
- **SPECIAL_PAGES** handles 3 more: Notifications, User Management, Settings.
- Pages are **lazy-loaded** via `importlib.import_module()` — only imports the module when navigated to.

### Sidebar (`components/sidebar.py`)

- AMPYR logo + app name + version.
- Navigation sections with button-based routing:
  - **OVERVIEW:** Dashboard
  - **OPERATIONS:** Plant Management, POA Import, Database Viewer, Data Explorer
  - **ANALYSIS:** Data Overview, Fouling, Shading, Clipping, Thermal Loss, Curtailment
  - **REPORTING:** Monthly Performance, Report Builder
  - **ADVANCED:** Comparative Analysis, Data Export, API Management, Notifications
  - **SETTINGS:** Preferences, Fiscal Year selector, Data Source filter
- Active page highlighted with primary button style.
- Includes job monitor, global search trigger (Ctrl+K), onboarding tour, and auth user menu.

### Component Library (`components/`)

| Component | Purpose |
|-----------|---------|
| `auth_ui.py` | Login page, user menu (sidebar), profile editor, user management (admin-only) |
| `sidebar.py` | Navigation, fiscal year picker, data source filter, app branding |
| `notifications_ui.py` | Notification badge (sidebar), notification center, alert management |
| `global_search.py` | Fuzzy search across plants/reports/pages via `fuzzywuzzy`, Ctrl+K trigger |
| `keyboard_shortcuts.py` | Shortcut manager with defaults: Ctrl+K (search), Ctrl+H (dashboard), Ctrl+R (refresh), Ctrl+Shift+N (new report), Ctrl+E (export) |
| `preferences_ui.py` | Full settings page with tabs: General, Dashboard, Charts, Data Sources, Notifications, Advanced |
| `data_health.py` | Data quality badges, health dashboard, upload-with-validation |
| `job_monitor.py` | Background job sidebar widget, submit button helper, detailed job viewer |
| `report_button.py` | Universal "Add to Report" button — captures Plotly/Matplotlib/Altair charts, DataFrames, KPI dicts, and text as `ReportItem` objects |
| `contextual_help.py` | Inline help tooltips, section-level help expanders, field-level help captions |
| `ux.py` | Breadcrumbs, empty states, drag-drop uploader wrapper, onboarding tour, `UndoRedoBuffer` class |

### Theming (`styles/`)

- **`theme.css`** — CSS custom properties for AMPYR brand: Playfair Display headings, Lato body, dark navy sidebar (#0B1120), gradient buttons, pill-shaped buttons.
- **`theme.py`** — Python helpers: `apply_theme()`, `render_kpi_card()`, `render_section_header()`, `render_status_badge()`, `render_metric_row()`, `get_chart_layout()`.
- Brand colors: primary teal (#5FBFA0), dark navy background (#0B1120), warm amber accent (#D4A84B), positive green (#2D8B5F), negative red (#C94A4A).

Note: The legacy `Monthly reporting/brand_theme.py` has **different brand colors** — primary #1B4D5C (dark teal), secondary #2D8B9E, lighter overall palette. This creates an inconsistency between unified app pages and legacy reporting pages.

---

## 5. Authentication System

### Implementation (`services/auth_service.py`, 426 lines)

- **Database:** SQLite (`users.db`), separate from main DuckDB.
- **Tables:**
  - `users` — user_id, username, email, full_name, password_hash, role, permissions (JSON), is_active, created_at
  - `sessions` — session_id, user_id, created_at, expires_at, is_active
  - `audit_log` — log_id, user_id, action, details, ip_address, timestamp

### Roles & Permissions

| Role | Permissions |
|------|------------|
| **admin** | read, write, delete, export, manage_users, manage_settings |
| **manager** | read, write, export, manage_settings |
| **analyst** | read, write, export |
| **viewer** | read |

### Security Features

- **Password hashing:** bcrypt (12 rounds). Legacy SHA-256 auto-upgrade on login.
- **Rate limiting:** 5 failed attempts → 15-minute account lockout.
- **Auto-created admin:** On first run, creates default admin with random password (logged to console). UI also shows `admin/admin123` as default — **this is a security concern**.
- **Session management:** JWT-compatible session tokens stored in Streamlit session state.
- **Audit logging:** All auth events (login, logout, create/update/delete user) recorded with timestamp.

### UI (`components/auth_ui.py`)

- Login form, profile page (change password), user management (admin-only: list users, change roles, deactivate, create new users).

---

## 6. Data Pipeline

### Data Ingestion Flow

```
EMIG API → ToolkitBridge.fetch_readings()
              → EmigApiClient.get_readings()
                 → pandas DataFrame
                    → DuckDB 'readings' table

SolarGIS files → poa_import.py
                   → fuzzy filename matching
                      → DuckDB 'poa_data' table

Export Limit parquets → curtailment_analysis.py
                          → ExportLimitClient
                             → in-memory DataFrame

Manual CSV/Excel uploads → data_explorer.py
                             → IncrementalETL.validate_dataframe()
                                → 7 quality checks
                                   → DuckDB target table
```

### Incremental ETL (`services/incremental_etl.py`)

- **Metadata table:** `_etl_metadata` in DuckDB tracks per-table ingestion state (last timestamp, max date, validation status, row count).
- **Pydantic validation:** `SolarDataSchema` model validates required fields: Site, Date, PR (0–2 range), Irradiance, Energy, Availability.
- **7 quality checks:** empty data, required columns, null percentages, duplicate rows, date validity, schema validation, numeric range checks.
- **Incremental loading:** Date-based — only inserts rows with dates > last max date in table.

### Caching (`services/cache_layer.py`)

- **Two backends:**
  - `memory` — thread-safe in-process dict with TTL.
  - `duckdb` — persistent cache stored in `_cache` table (namespace, key, value as JSON, timestamp, TTL).
- **`@cached(namespace, ttl)` decorator** for transparent function caching.
- **`get_or_compute(key, func)`** pattern for lazy evaluation.
- **Cache warming** on startup for commonly accessed queries.

### Materialized Views (`services/materialized_views.py`)

- **3 precomputed views** stored as regular DuckDB tables:
  - `mv_site_month_summary` — monthly PR, availability, generation by Site/Date
  - `mv_loss_breakdown` — grid/availability/inverter/weather losses
  - `mv_portfolio_kpis` — portfolio-wide aggregate metrics
- **Source table:** `solar_data` (monthly reporting data, ~95 rows).
- **Metadata:** `_mv_metadata` table tracks refresh timestamps and row counts.
- **Refresh:** Manual or feature-flag-triggered. Uses `@timed_operation` decorator for performance tracking.

### DuckDB Connection Management (`services/db_utils.py`)

- Context manager `get_connection(db_path, read_only)` with fallback logic: tries read-only first, degrades to automatic access mode on `ConnectionException`.
- Helpers: `execute_query()`, `execute_df()`, `table_exists()`, `get_tables()`.
- **Known issue:** DuckDB single-writer limitation can cause lock conflicts, especially with Google Drive sync. The reporting bridge uses memory caching to mitigate this.

---

## 7. Reporting Capabilities

### Report Builder (`modules/report_builder.py`, 512 lines)

- **Custom executive report assembly** from content captured across any page.
- Data model:
  - `ReportItem` — chart (image bytes), table (DataFrame), KPI (dict), or text.
  - `ReportConfig` — title, subtitle, list of items, TOC toggle.
  - `ReportRegistry` — manages items in `st.session_state` with undo/redo (`UndoRedoBuffer`).
- **Add-to-report pattern:** Any analysis page can use `add_to_report_button()` to capture the current chart/table and push it to the report registry.
- **PDF generation:** `PDFReportGenerator` (ReportLab) with branded styles (AMPYR colors, Helvetica fonts, alternating row colors).

### PDF Generator (`modules/report_generator.py`, 308 lines)

- ReportLab-based PDF with A4 or landscape page size.
- Brand-styled title page, section headers, tables, plots (Plotly → PNG via kaleido, Matplotlib → PNG), KPI grids.
- `add_report_item()` universal entry point routes by item type.
- Support for image bytes, DataFrames-as-tables, KPI dictionaries, and text blocks.

### Monthly Executive Reporting (`modules/monthly_reporting.py` + `Monthly reporting/ui_excom_report.py`)

- **ExCom-style waterfall** with defined steps: Budget → Irradiance → Availability → Efficiency → Actual.
- Loss calculations:
  - $Loss_{TechTotal} = WAB - Actual$
  - $Var_{Weather} = WAB - Budget$
  - $Loss_{PR} = WAB \times (PR_{budget} - PR_{actual})$
  - $Loss_{Avail} = WAB \times (0.99 - Availability)$
  - $Efficiency = Budget + Irradiance + Availability - Actual$ (balancing item)
- KPI cards: portfolio generation, PR, availability, technical loss.
- Portfolio summary table with color-coded performance bands.

### Data Export (`modules/data_export_ui.py` + `services/export_service.py`)

- **Quick Export Templates:** Monthly Performance Report, Plant Summary Report, All Plants, Performance Metrics, Alert History.
- **Custom Export Builder:** Select data source, table, date range, format.
- **Formats:** CSV, XLSX (multi-sheet), JSON, Parquet.
- **Download via Streamlit:** `st.download_button()` for in-browser download.
- **Export package:** ZIP of multiple files via `create_export_package()`.

---

## 8. Notification & Alert System

### Service (`services/notification_service.py`, 370 lines)

- **Database:** SQLite (`notifications.db`).
- **Tables:**
  - `notifications` — notification_id, user_id, title, message, type (INFO/WARNING/ERROR/SUCCESS/ALERT), data (JSON), is_read, created_at
  - `alerts` — alert_id, name, description, metric, condition, threshold, is_active, created_by, created_at
  - `alert_history` — history of triggered alerts

### Default Alert Rules

| Alert | Metric | Condition | Threshold |
|-------|--------|-----------|-----------|
| Low PR | Performance Ratio | < | 75% |
| High Availability | Availability | > | 99% |
| Low Availability | Availability | < | 95% |
| High Clipping Loss | Clipping Loss | > | 5% |
| High Soiling Loss | Soiling Loss | > | 3% |

### Alert Evaluation

- `Alert.check(value)` evaluates conditions using operator comparison (<, >, ≤, ≥, ==, !=).
- `check_alert(metric, value, context)` auto-creates notifications when thresholds are exceeded.
- **Not automated:** Alert checking is triggered manually or when analysis pages compute metrics. There is no background scheduler that periodically evaluates alerts against live data.

### UI (`components/notifications_ui.py`)

- Sidebar badge with unread count.
- Full notification center: list, mark read, delete, filter unread.
- Alert management: CRUD for alert rules (create, edit, toggle, view history).

---

## 9. Database Schema Patterns

### DuckDB (`plant_registry.duckdb`) — Primary Data Store

| Table | Purpose | Approx Rows | Key Columns |
|-------|---------|-------------|-------------|
| `plants` | Plant registry | ~20 | alias, plant_uid, inverter_ids, weather_id, dc_size_kw, latitude, longitude, tilt, azimuth |
| `readings` | Time-series operational data | ~1.28M | plant_uid, device_id, timestamp, apparentPower_value, poaIrradiance_value, etc. |
| `solar_data` | Monthly reporting data | ~95 | Site, Date, PR, Irradiance, Energy, Availability, losses, budget columns |
| `_cache` | Cache layer storage | varies | namespace, key, value (JSON), timestamp, ttl_seconds |
| `_mv_metadata` | Materialized view tracking | 3 | view_name, last_refresh, row_count, status |
| `_user_preferences` | Per-user settings | varies | user_id, key, value, updated_at |
| `_etl_metadata` | ETL ingestion tracking | varies | table_name, last_ingestion_timestamp, total_rows, last_max_date, validation_status |
| `_error_log` | Error records | varies | error_type, message, timestamp, severity, context |
| `mv_site_month_summary` | Precomputed monthly stats | varies | Site, Date, PR, Availability, Generation |
| `mv_loss_breakdown` | Precomputed loss detail | varies | Site, Date, grid_loss, availability_loss, etc. |
| `mv_portfolio_kpis` | Portfolio-wide KPIs | varies | metric_name, value |

### SQLite (`users.db`) — Authentication

| Table | Key Columns |
|-------|-------------|
| `users` | user_id (UUID), username, email, full_name, password_hash, role, permissions (JSON), is_active |
| `sessions` | session_id (UUID), user_id, created_at, expires_at, is_active |
| `audit_log` | log_id, user_id, action, details, ip_address, timestamp |

### SQLite (`notifications.db`) — Alerts

| Table | Key Columns |
|-------|-------------|
| `notifications` | notification_id, user_id, title, message, notification_type, data (JSON), is_read |
| `alerts` | alert_id, name, metric, condition, threshold, is_active |
| `alert_history` | history_id, alert_id, triggered_at, value, notification_id |

### SQLite (`api.db`) — API Keys

| Table | Key Columns |
|-------|-------------|
| `api_keys` | key_id, user_id, name, key_hash (SHA-256), permissions (JSON), is_active |
| `api_usage` | usage_id, key_id, endpoint, timestamp, response_status |

---

## 10. What Works Well

### Architecture Strengths

1. **Clean modular separation** — services layer isolates business logic from UI; components are reusable across pages; modules are self-contained page renderers.
2. **Lazy loading pattern** — `importlib.import_module()` in `PAGE_REGISTRY` means startup only loads what's needed, keeping the app responsive.
3. **Bridge pattern for legacy integration** — `ToolkitBridge` and `ReportingBridge` provide clean interfaces to legacy code without requiring rewrites.
4. **Unified database strategy** — pointing both legacy projects at the same DuckDB file avoids data duplication and enables cross-module queries.
5. **Comprehensive error handling** — `AppErrorHandler` with an error catalog provides consistent user-facing messages with recovery suggestions.
6. **Report builder pattern** — the `add_to_report_button()` → `ReportRegistry` → PDF pipeline allows users to compose custom reports from any analysis page.

### Feature Strengths

7. **Multiple analysis modes** — five distinct loss analysis types (fouling, shading, clipping, thermal, curtailment) plus a unified loss waterfall with seasonal awareness.
8. **Data quality pipeline** — pydantic-based validation with 7 automated checks on ingestion, plus per-table health badges.
9. **Incremental ETL** — date-based windowing avoids re-processing historical data.
10. **Observability** — structlog for structured logging, in-memory metrics with p50/p95 query times, `@timed_operation` decorator.
11. **User preferences** — DuckDB-backed persistence for 25+ preferences with favorites, recent items, saved filters.
12. **Flexible export** — four formats (CSV, XLSX, JSON, Parquet) with multi-sheet and ZIP packaging support.

---

## 11. Gaps & Limitations

### Critical Issues

1. **`comparative_analysis.py` uses `sqlite3` to connect to DuckDB** — This will fail or produce incorrect results since the database is DuckDB format, not SQLite. Should use `duckdb.connect()` via `db_utils.get_connection()`.

2. **Default admin credentials exposed in UI** — `auth_ui.py` renders `st.info("Default credentials: admin / admin123")` directly on the login page. The actual default password is randomly generated, making this misleading and potentially a security risk.

3. **API endpoints are not real HTTP endpoints** — `api_service.py` documents REST endpoints and generates API keys, but there's no HTTP server. The UI gives users API keys and curl examples that won't work. Needs FastAPI/Flask or Streamlit `connections` integration.

4. **Brand color inconsistency** — The unified app uses primary teal #5FBFA0 (via `unified_config.py`) while legacy monthly reporting uses #1B4D5C (via `brand_theme.py`). Charts from different modules will have mismatched color palettes.

### Architectural Gaps

5. **No background scheduler** — Alert evaluation requires manual triggering. There's no cron/APScheduler/Celery to periodically check thresholds against live data.

6. **DuckDB single-writer contention** — Multiple Streamlit sessions (or Google Drive sync) can cause lock conflicts. The workaround (memory caching in reporting bridge) is fragile.

7. **Three separate SQLite databases** alongside DuckDB — Auth, notifications, and API keys could be consolidated into DuckDB tables, reducing operational complexity.

8. **No database migrations** — Tables are created via `CREATE TABLE IF NOT EXISTS` on first use. No versioned migration system (e.g., Alembic) for schema changes.

9. **Legacy sub-projects use `sys.path` manipulation** — `legacy_toolkit.py` and `reporting_bridge.py` insert legacy directories into `sys.path`, which can cause import conflicts and makes testing difficult.

### Feature Gaps

10. **Scheduled exports not implemented** — The "Scheduled Exports" tab exists in `data_export_ui.py` but appears non-functional (no scheduling mechanism).

11. **No real-time data streaming** — Data freshness depends on manual "Bulk Smart Update" pulls. No webhook or polling integration for auto-ingest when new API data is available.

12. **POA import folder browser is Windows-only** — `poa_import.py` uses PowerShell for folder selection, which won't work on macOS/Linux.

13. **Missing test coverage** — The `tests/` directory exists but test files were not examined. Based on the codebase complexity (~60+ files), automated test coverage is likely minimal.

14. **Keyboard shortcuts inject JavaScript** — `keyboard_shortcuts.py` likely injects JS into Streamlit's custom HTML, which is fragile and may break across Streamlit versions.

15. **`loss_waterfall.py` imports from `clipping_analysis` and `curtailment_analysis` via relative path** — Uses `sys.path.insert(0, ...)` to make sibling modules importable. Should use proper package imports.

16. **Hardcoded plant-specific values** — `curtailment_analysis.py` has hardcoded AC capacities for specific AMPYR plants (Newfold Farm 8050kW, etc.), and `toolkit_bridge.py` has hardcoded alias mappings. These should be in configuration or the database.

### Performance Considerations

17. **`readings` table has 1.28M rows** with no documented indexes — DuckDB is columnar and efficient for analytics, but specific query patterns (filter by plant_uid + date range) could benefit from explicit indexing or partitioning.

18. **Materialized views source from `solar_data` (95 rows)** — The view system is built but sources from a very small table. The larger `readings` table doesn't have corresponding materialized views.

---

## 12. External Services & APIs Referenced

| Service | How Referenced | Used In |
|---------|---------------|---------|
| **EMIG API** | `EmigApiClient` via Solar Toolkit | `toolkit_bridge.py`, `plant_management.py` |
| **NREL PSM3** | HTTP API via pvlib | `clipping_loss.py` |
| **SolarGIS** | File import (CSV) | `poa_import.py` |
| **Google Drive** | File sync (desktop client) | `app_config/base.py` |
| **Google Fonts** | CDN (Playfair Display, Lato) | `styles/theme.css` |
| **Export Limit Crawler** | `ExportLimitClient` | `curtailment_analysis.py` |

---

## 13. File Inventory

### Root Files (6)

| File | Lines | Purpose |
|------|-------|---------|
| `app.py` | 109 | Main entry point, page registry, lazy loading |
| `unified_config.py` | ~120 | Backward-compatible config wrapper |
| `requirements.txt` | ~25 | Python dependencies |
| `pyproject.toml` | ~40 | Build config, ruff settings |
| `Dockerfile` | ~15 | Docker build (python:3.12-slim) |
| `docker-compose.yml` | ~30 | Single service with volumes |

### Services (15 + __init__)

| File | Lines | Purpose |
|------|-------|---------|
| `__init__.py` | 47 | Package exports, singleton instances |
| `toolkit_bridge.py` | 431 | Solar Toolkit integration |
| `reporting_bridge.py` | 451 | Monthly Reporting integration |
| `auth_service.py` | 426 | Authentication, RBAC, sessions |
| `notification_service.py` | 370 | Alerts, notifications |
| `api_service.py` | 370 | API key management, endpoint docs |
| `cache_layer.py` | 410 | Memory + DuckDB caching |
| `incremental_etl.py` | 350 | Data ingestion with validation |
| `materialized_views.py` | 310 | Precomputed aggregate tables |
| `export_service.py` | 280 | Multi-format data export |
| `background_jobs.py` | 230 | Threading-based task queue |
| `user_preferences.py` | 310 | Per-user settings persistence |
| `observability.py` | 270 | Structured logging, metrics |
| `error_handler.py` | 402 | Error catalog, safe execution |
| `db_utils.py` | 75 | DuckDB connection management |
| `legacy_toolkit.py` | 65 | Solar Toolkit path/import wrapper |

### Modules (18 + chart_utils + __init__)

| File | Lines | Purpose |
|------|-------|---------|
| `dashboard.py` | 200 | Executive portfolio overview |
| `plant_management.py` | 270 | Register plants, fetch API data |
| `clipping_analysis.py` | 1011 | First-principles clipping detection |
| `clipping_loss.py` | ~130 | pvlib twin simulation wrapper |
| `curtailment_analysis.py` | 960 | Export curtailment analysis |
| `fouling.py` | 300 | Soiling/fouling analysis |
| `shading.py` | 639 | Shading loss analysis |
| `thermal_loss.py` | 300 | Thermal derating analysis |
| `monthly_reporting.py` | 852 | Monthly executive reporting |
| `waterfall.py` | 280 | Loss waterfall visualization |
| `loss_waterfall.py` | 486 | Unified loss waterfall with seasonal logic |
| `report_builder.py` | 512 | Custom report assembly |
| `report_generator.py` | 308 | PDF generation (ReportLab) |
| `comparative_analysis.py` | 532 | Cross-plant comparison |
| `data_explorer.py` | 332 | Upload, health, jobs, cache management |
| `data_overview.py` | 160 | Data availability heatmap |
| `database_viewer.py` | 220 | View/edit/delete database records |
| `data_export_ui.py` | 423 | Export interface |
| `api_management_ui.py` | 257 | API key and docs interface |
| `poa_import.py` | 337 | SolarGIS POA import |
| `system_health.py` | ~160 | Observability dashboard |
| `chart_utils.py` | ~80 | Shared chart creation functions |

### Components (11 + __init__)

| File | Lines | Purpose |
|------|-------|---------|
| `__init__.py` | 55 | Package exports |
| `sidebar.py` | ~150 | Navigation, settings |
| `auth_ui.py` | 228 | Login, profile, user management |
| `notifications_ui.py` | 238 | Notification center, alerts |
| `global_search.py` | 439 | Fuzzy search system |
| `keyboard_shortcuts.py` | 476 | Hotkey management |
| `preferences_ui.py` | 419 | Settings page |
| `data_health.py` | 274 | Data quality monitoring |
| `job_monitor.py` | 247 | Background job UI |
| `report_button.py` | 353 | "Add to Report" universal button |
| `contextual_help.py` | 466 | Help tooltips, guided tours |
| `ux.py` | ~140 | Breadcrumbs, empty states, undo/redo |

### Styles (3)

| File | Purpose |
|------|---------|
| `__init__.py` | Package exports |
| `theme.py` | Python rendering helpers, KPI cards, status badges |
| `theme.css` | CSS custom properties, AMPYR brand styling |

### App Config (5)

| File | Purpose |
|------|---------|
| `__init__.py` | Environment-aware config loader |
| `base.py` | Default configuration |
| `development.py` | Dev-specific overrides |
| `staging.py` | Staging overrides |
| `production.py` | Production overrides |

### Legacy: Monthly Reporting (~15 files)

Key files: `analysis.py` (509 lines — loss calculations, variance analysis), `data_access.py` (764 lines — SolarDataExtractor with SQLite/DuckDB access), `ui_excom_report.py` (1354 lines — ExCom waterfall charts, KPI cards), `brand_theme.py` (428 lines — AMPYR design system), `config.py` (289 lines — column patterns, session state).

### Legacy: Solar Toolkit

External package at `Solar Toolkit/` with its own orchestrator, data viewer, EMIG API client, and analysis modules. Accessed via `services/legacy_toolkit.py` and `services/toolkit_bridge.py`.

---

*End of report.*
