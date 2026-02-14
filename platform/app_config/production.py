"""
Production environment configuration.
Optimized for performance and structured logging.
"""

# Logging - JSON format for log aggregation
LOG_LEVEL = "WARNING"
LOG_FORMAT = "json"

# Feature flags - all enabled
USE_CACHED_VIEWS = True
ENABLE_BACKGROUND_JOBS = True
ENABLE_OBSERVABILITY = True

# Performance - production limits
QUERY_CACHE_TTL = 600  # 10 minutes
MAX_QUERY_RESULTS = 50000
