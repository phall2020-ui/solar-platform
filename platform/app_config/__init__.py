"""Backward-compatibility shim — all config now lives in services.config.

This package is deprecated.  Import from ``services.config`` or use the
``unified_config.config`` singleton instead.
"""
from services.config import (
    APP_NAME,
    APP_VERSION,
    BASE_PATH,
    BRAND_COLORS,
    CHART_COLORS,
    MONTHLY_REPORTING_PATH,
    PAGE_ICON,
    PAGE_TITLE,
    SOLAR_TOOLKIT_PATH,
    get_settings,
)

_s = get_settings()

ENVIRONMENT = _s.environment
TOOLKIT_DB = _s.db_path
REPORTING_DB = _s.db_path
UNIFIED_DB = _s.db_path
EMIG_API_KEY = _s.effective_api_key
NREL_API_KEY = _s.nrel_api_key
use_cached_views = _s.use_cached_views
enable_background_jobs = _s.enable_background_jobs
enable_observability = _s.enable_observability
QUERY_CACHE_TTL = _s.query_cache_ttl
MAX_QUERY_RESULTS = _s.max_query_results
LOG_LEVEL = _s.log_level
LOG_FORMAT = _s.log_format
DEFAULT_FISCAL_START = _s.default_fiscal_start
TARGET_AVAILABILITY = _s.target_availability
DEFAULT_PR_BUDGET = _s.default_pr_budget
DEFAULT_FOULING_CLEAN_DAYS = _s.default_fouling_clean_days
DEFAULT_SHADING_BASELINE_MONTHS = _s.default_shading_baseline_months
DEFAULT_SHADING_COMPARE_MONTHS = _s.default_shading_compare_months
