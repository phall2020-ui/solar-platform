"""
Staging environment configuration.
Mirrors production but with more verbose logging.
"""

# Logging
LOG_LEVEL = "INFO"
LOG_FORMAT = "json"

# Feature flags
USE_CACHED_VIEWS = True
ENABLE_BACKGROUND_JOBS = True
ENABLE_OBSERVABILITY = True

# Performance
QUERY_CACHE_TTL = 300
MAX_QUERY_RESULTS = 10000
