"""
Base configuration - defaults for all environments.
These values are used unless overridden by environment-specific config or env vars.
"""
from pathlib import Path
import os

try:
    from services.config import get_settings as _get_phase0_settings
except Exception:  # pragma: no cover - legacy fallback path
    _get_phase0_settings = None


def get_settings():
    """Compatibility bridge to the new validated settings model."""
    if _get_phase0_settings is None:
        raise RuntimeError("services.config is not available")
    return _get_phase0_settings()

# Application
APP_NAME = "☀️ Solar Portfolio Manager"
APP_VERSION = "1.1.0"
PAGE_TITLE = "AMPYR Solar Portfolio Manager"
PAGE_ICON = "☀️"

# Paths - All resources now consolidated within Unified app folder
BASE_PATH = Path(__file__).parent.parent  # app_config -> Unified app
SOLAR_TOOLKIT_PATH = BASE_PATH / "Solar Toolkit"
MONTHLY_REPORTING_PATH = BASE_PATH / "Monthly reporting"

# Google Drive sync path (for cross-device database sync)
# Expected format: ~/Library/CloudStorage/GoogleDrive-<email>/My Drive/SolarPortfolioManager/databases
_google_drive_env = os.getenv("GOOGLE_DRIVE_SYNC_PATH", "")
GOOGLE_DRIVE_PATH = Path(_google_drive_env) if _google_drive_env else None

# UNIFIED DATABASE - All tables consolidated into single DuckDB file
# Tables: plants, readings (1.28M rows), solar_data (95 rows), _cache, _mv_metadata
if GOOGLE_DRIVE_PATH and GOOGLE_DRIVE_PATH.exists():
    UNIFIED_DB = GOOGLE_DRIVE_PATH / "plant_registry.duckdb"
else:
    # Fallback to local path if Google Drive not available
    UNIFIED_DB = Path.home() / ".solar_toolkit" / "plant_registry.duckdb"

# For backwards compatibility, both point to the same unified database
TOOLKIT_DB = UNIFIED_DB
REPORTING_DB = UNIFIED_DB

# API Keys
EMIG_API_KEY = os.getenv("EMIG_API_KEY", os.getenv("JUGGLE_API_KEY", ""))
NREL_API_KEY = os.getenv("NREL_API_KEY", "")

# Feature Flags (defaults)
USE_CACHED_VIEWS = False
ENABLE_BACKGROUND_JOBS = False
ENABLE_OBSERVABILITY = True

# Performance
QUERY_CACHE_TTL = 300  # seconds
MAX_QUERY_RESULTS = 10000

# Logging
LOG_LEVEL = "INFO"
LOG_FORMAT = "console"

# Phase 0 bridge: prefer validated settings if available.
if _get_phase0_settings is not None:
    try:
        _phase0_settings = _get_phase0_settings()

        UNIFIED_DB = _phase0_settings.db_path
        TOOLKIT_DB = Path(_phase0_settings.toolkit_db_path).expanduser() if _phase0_settings.toolkit_db_path else UNIFIED_DB
        REPORTING_DB = Path(_phase0_settings.reporting_db_path).expanduser() if _phase0_settings.reporting_db_path else UNIFIED_DB

        EMIG_API_KEY = _phase0_settings.effective_api_key
        NREL_API_KEY = _phase0_settings.nrel_api_key

        USE_CACHED_VIEWS = _phase0_settings.use_cached_views
        ENABLE_BACKGROUND_JOBS = _phase0_settings.enable_background_jobs
        ENABLE_OBSERVABILITY = _phase0_settings.enable_observability

        QUERY_CACHE_TTL = _phase0_settings.query_cache_ttl
        MAX_QUERY_RESULTS = _phase0_settings.max_query_results

        LOG_LEVEL = _phase0_settings.log_level
        LOG_FORMAT = _phase0_settings.log_format
    except Exception:
        pass

# Analysis defaults
DEFAULT_FISCAL_START = 4  # April
TARGET_AVAILABILITY = 99.0
DEFAULT_PR_BUDGET = 79.0
DEFAULT_FOULING_CLEAN_DAYS = 3
DEFAULT_SHADING_BASELINE_MONTHS = ["06", "07", "08"]  # Jun, Jul, Aug
DEFAULT_SHADING_COMPARE_MONTHS = ["10", "11", "12"]   # Oct, Nov, Dec

# AMPYR Brand Colors (shared across all environments)
BRAND_COLORS = {
    # Core brand
    "primary": "#5FBFA0",        # AMPYR teal
    "secondary": "#4A9E80",      # Teal shadow
    "accent": "#8FE0C5",         # Soft mint accent
    # Semantic
    "positive": "#5FBFA0",
    "negative": "#E66B6B",
    "warning": "#F2C265",
    # Surfaces
    "surface": "#1E2538",        # Card/nav surface
    "background": "#0B1120",     # Deep navy
    "border": "#2B354E",         # Border tone
    # Text
    "text": "#FFFFFF",
    "text_secondary": "#E0E0E0",
}

# Chart colors for consistent visualizations (includes Gantt palette cues)
CHART_COLORS = [
    "#5FBFA0",  # Teal (Clean/Veg)
    "#8E44AD",  # Muted purple (Works)
    "#5D6D7E",  # Slate blue/gray (PM)
    "#4A9E80",  # Teal shadow
    "#E66B6B",  # Accent red
    "#F2C265",  # Amber
    "#8FE0C5",  # Mint
]
