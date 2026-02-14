"""
Development environment configuration.
Overrides base.py settings for local development.
"""

# Logging - verbose for debugging
LOG_LEVEL = "DEBUG"
LOG_FORMAT = "console"

# Feature flags - enable for testing
USE_CACHED_VIEWS = False  # Test raw queries by default
ENABLE_BACKGROUND_JOBS = False
ENABLE_OBSERVABILITY = True

# Performance - smaller limits for faster iteration
QUERY_CACHE_TTL = 60  # seconds (shorter for dev)
MAX_QUERY_RESULTS = 5000
