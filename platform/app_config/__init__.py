"""
Environment-aware configuration loader.
Loads base config, then overlays environment-specific settings.
"""
import os
from pathlib import Path

# Load .env file if present
try:
    from dotenv import load_dotenv
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)
except ImportError:
    pass  # python-dotenv already in requirements.txt

# Determine environment
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()

# Import base config
from .base import *

# Overlay environment-specific config
if ENVIRONMENT == "production":
    try:
        from .production import *
    except ImportError:
        pass
elif ENVIRONMENT == "staging":
    try:
        from .staging import *
    except ImportError:
        pass
else:
    try:
        from .development import *
    except ImportError:
        pass

# Runtime overrides from environment variables
_toolkit_db = os.getenv("TOOLKIT_DB_PATH")
if _toolkit_db:
    TOOLKIT_DB = Path(_toolkit_db)

_reporting_db = os.getenv("REPORTING_DB_PATH")
if _reporting_db:
    REPORTING_DB = Path(_reporting_db)

# Feature flags (with env var overrides)
use_cached_views = os.getenv("USE_CACHED_VIEWS", str(USE_CACHED_VIEWS)).lower() == "true"
enable_background_jobs = os.getenv("ENABLE_BACKGROUND_JOBS", str(ENABLE_BACKGROUND_JOBS)).lower() == "true"
enable_observability = os.getenv("ENABLE_OBSERVABILITY", str(ENABLE_OBSERVABILITY)).lower() == "true"

# Logging overrides
LOG_LEVEL = os.getenv("LOG_LEVEL", LOG_LEVEL).upper()
LOG_FORMAT = os.getenv("LOG_FORMAT", LOG_FORMAT).lower()

# Performance overrides
_cache_ttl = os.getenv("QUERY_CACHE_TTL")
if _cache_ttl:
    QUERY_CACHE_TTL = int(_cache_ttl)
    
_max_results = os.getenv("MAX_QUERY_RESULTS")
if _max_results:
    MAX_QUERY_RESULTS = int(_max_results)
