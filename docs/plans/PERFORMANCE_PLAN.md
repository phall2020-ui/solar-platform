# Performance Improvement Plan

**Created:** 2026-02-16  
**Status:** Ready for implementation  

## Current State

The Streamlit app re-executes `app/main.py` on every user interaction (click, widget change, navigation). Profiling shows:

| Import group | Time |
|---|---|
| `streamlit` | 0.316s |
| `pandas` | 0.296s |
| `solar_platform.config` | 0.056s |
| Everything else | <0.06s |
| **Total imports** | **~0.73s** |

Import time is not the bottleneck. The real problems:

1. **Zero caching** — only 2 of 30 pages use `@st.cache_data`. Every rerun re-queries DuckDB.
2. **Eager imports** — `components/__init__.py` pulls in `job_monitor`, `data_health`, and `ux` for every page even though only `sidebar` is needed at app startup.
3. **CSS file read on every rerun** — `config.get_css()` reads `theme.css` from disk on every interaction.
4. **DDL on startup** — `get_error_handler()` and `init_preferences_in_session()` run `CREATE TABLE IF NOT EXISTS` at first launch.
5. **JS re-injection** — `inject_keyboard_handler()` emits HTML/JS on every rerun.
6. **No `@st.cache_resource`** for expensive singletons (DB engine, services).

---

## Plan (Priority Order)

### P0 — Add `@st.cache_data` to Data-Fetching Functions

**Impact: Highest — eliminates redundant DB queries on every widget click**

Every page that calls a service to fetch data should cache the result. This is the single largest win.

#### Dashboard (`app/pages/dashboard.py`)
```python
@st.cache_data(ttl=300)
def _get_summary(time_range):
    return PortfolioService().get_summary(time_range)

@st.cache_data(ttl=300)
def _get_plant_statuses(time_range):
    return PortfolioService().get_plant_statuses(time_range)
```

#### Each page pattern:
- Wrap the data-fetch call in a `@st.cache_data(ttl=300)` function (5 min TTL)
- Leave chart rendering / UI uncached (Streamlit handles widget state)
- For pages with user parameters (date range, plant selector): pass them as function args so the cache key varies

**Pages needing this treatment:**
- `dashboard.py` — `get_summary()`, `get_plant_statuses()`, `get_generation_trend()`, `get_alert_summary()`
- `site_monitor.py` — `get_plants()`, `query_readings_df()`
- `clipping_analysis.py` — `engine.run()`
- `curtailment_analysis.py` — `engine.run()`
- `shading.py` — `engine.run()`
- `fouling.py` — `engine.run()`
- `thermal_loss.py` — `engine.run()`
- `loss_waterfall.py` — `engine.run()`
- `comparative_analysis.py` — `engine.run()`
- `pr_trending.py` — `engine.run()`
- `degradation_analysis.py` — `engine.run()`
- `anomaly_detection_ui.py` — `query_readings_df()`
- `financial_dashboard.py` — `_load_monthly_revenue()`, `_load_plant_breakdown()`
- `data_quality_dashboard.py` — all DB queries
- `alerts_dashboard.py` — alert queries
- `plant_detail.py` — device readings, KPIs

### P0 — Use `@st.cache_resource` for Singletons

```python
# In app/main.py or a shared init module
@st.cache_resource
def _get_error_handler():
    return get_error_handler()

@st.cache_resource  
def _get_preferences(db_path):
    return init_preferences_in_session(db_path)
```

This ensures DDL (CREATE TABLE, CREATE INDEX) runs once per server lifetime, not per user session.

---

### P1 — Lazy Imports in `components/__init__.py`

**Impact: Medium — saves ~100ms+ per page that doesn't use job_monitor/data_health**

```python
# app/components/__init__.py
from .sidebar import get_navigation_state, render_sidebar

def __getattr__(name):
    if name in ("check_job_completion", "job_status_viewer", "submit_background_job_button"):
        from .job_monitor import check_job_completion, job_status_viewer, submit_background_job_button
        return locals()[name]
    if name in ("data_health_dashboard", "data_quality_uploader"):
        from .data_health import data_health_dashboard, data_quality_uploader
        return locals()[name]
    if name == "drag_drop_uploader":
        from .ux import drag_drop_uploader
        return drag_drop_uploader
    raise AttributeError(f"module 'app.components' has no attribute {name!r}")
```

---

### P1 — Cache CSS String

**Impact: Medium — eliminates disk I/O on every rerun**

```python
# In app/config_compat.py
import functools

@classmethod
@functools.lru_cache(maxsize=1)
def get_css(cls) -> str:
    ...  # existing implementation
```

Or use `@st.cache_resource`:
```python
@st.cache_resource
def _get_theme_css():
    return config.get_css()
```

---

### P2 — Guard JS Injection

```python
# In app/main.py
if "kb_handler_injected" not in st.session_state:
    inject_keyboard_handler()
    st.session_state["kb_handler_injected"] = True
```

Note: Streamlit re-renders the full page on rerun, so the JS needs to be re-injected. This optimization only works if the keyboard handler uses `st.components.html` in a way that persists across reruns. Test before applying.

---

### P2 — Guard `setup_logging()`

```python
if "logging_initialized" not in st.session_state:
    setup_logging()
    st.session_state["logging_initialized"] = True
```

---

### P3 — Connection Reuse

The `DuckDBEngine` already uses a singleton dict in `get_engine()`, but each `connection()` call opens a new `duckdb.connect()`. Consider keeping a persistent read-only connection for query workloads:

```python
@st.cache_resource
def _get_read_connection():
    return duckdb.connect(str(db_path), read_only=True)
```

**Caveat:** DuckDB has a single-writer model. Read-only connections can be concurrent, but writes need a separate connection. This optimization applies only to dashboards/analysis pages that only read.

---

## Summary Matrix

| Priority | Change | Files | Expected Savings |
|---|---|---|---|
| **P0** | `@st.cache_data` on all data-fetching functions | ~16 pages | Eliminates redundant DB queries — **50-80% faster page interactions** |
| **P0** | `@st.cache_resource` for error_handler & prefs | `app/main.py` | DDL runs once per server lifetime |
| **P1** | Lazy imports in `components/__init__.py` | 1 file | ~100ms less per non-data-management page load |
| **P1** | Cache CSS string | `config_compat.py` or `theme.py` | Eliminates disk I/O per rerun |
| **P2** | Guard JS injection | `app/main.py` | Reduces HTML payload |
| **P2** | Guard `setup_logging()` | `app/main.py` | Minor |
| **P3** | Persistent read-only DuckDB connection | `db/engine.py` | Reduces connection churn |

## Implementation Order

1. Start with P0 caching — this alone should make the app feel dramatically faster
2. Then P1 lazy imports and CSS caching
3. P2/P3 are polish optimizations
