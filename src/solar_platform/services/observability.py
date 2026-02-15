"""
Observability infrastructure: structured logging and metrics.
Provides request timing, cache tracking, error logging, and metrics aggregation.
"""
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, UTC
from functools import wraps
from typing import Any

# Lazy import to avoid circular dependencies
_logger = None
_config = None


def _get_config():
    """Lazy load config to avoid import cycles."""
    global _config
    if _config is None:
        from solar_platform.config import config
        _config = config
    return _config


def _get_logger():
    """Lazy configure and return structlog logger."""
    global _logger
    if _logger is None:
        try:
            import logging

            import structlog
            config = _get_config()
            
            # Map log level string to logging module level
            log_level_map = {
                "DEBUG": logging.DEBUG,
                "INFO": logging.INFO,
                "WARNING": logging.WARNING,
                "ERROR": logging.ERROR,
                "CRITICAL": logging.CRITICAL,
            }
            log_level = log_level_map.get(config.LOG_LEVEL.upper(), logging.INFO)
            
            processors = [
                structlog.contextvars.merge_contextvars,
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
            ]
            
            # JSON output for production, console for dev
            if config.LOG_FORMAT == "json":
                processors.append(structlog.processors.JSONRenderer())
            else:
                processors.append(structlog.dev.ConsoleRenderer())
            
            structlog.configure(
                processors=processors,
                wrapper_class=structlog.make_filtering_bound_logger(log_level),
                context_class=dict,
                logger_factory=structlog.PrintLoggerFactory(),
                cache_logger_on_first_use=True,
            )
            _logger = structlog.get_logger()
        except ImportError:
            # Fallback to standard logging if structlog not installed
            import logging
            logging.basicConfig(level=logging.INFO)
            _logger = logging.getLogger("solar_portfolio")
    return _logger


def get_logger():
    """Public accessor for the configured logger."""
    return _get_logger()


@dataclass
class QueryRecord:
    """Record of a single query execution."""
    timestamp: str
    operation: str
    duration_ms: float
    success: bool
    result_count: int = 0


@dataclass
class ErrorRecord:
    """Record of an error occurrence."""
    timestamp: str
    error_type: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)


class MetricsStore:
    """In-memory metrics aggregator for dashboard display.
    
    Tracks query performance, cache effectiveness, and errors.
    Thread-safe for use with Streamlit's execution model.
    """
    
    def __init__(self, max_samples: int = 1000):
        self.max_samples = max_samples
        self._query_times: deque = deque(maxlen=max_samples)
        self._cache_hits: int = 0
        self._cache_misses: int = 0
        self._errors: deque = deque(maxlen=100)
        self._page_loads: deque = deque(maxlen=max_samples)
        self._start_time: datetime = datetime.now(UTC)
    
    def record_query(
        self, 
        operation: str, 
        duration_ms: float, 
        success: bool,
        result_count: int = 0
    ) -> None:
        """Record a query execution."""
        record = QueryRecord(
            timestamp=datetime.now(UTC).isoformat(),
            operation=operation,
            duration_ms=duration_ms,
            success=success,
            result_count=result_count
        )
        self._query_times.append(record)
        
        logger = _get_logger()
        if success:
            logger.debug(
                "query_completed",
                operation=operation,
                duration_ms=round(duration_ms, 2),
                result_count=result_count
            )
        else:
            logger.warning(
                "query_failed",
                operation=operation,
                duration_ms=round(duration_ms, 2)
            )
    
    def record_cache_hit(self, cache_name: str = "default") -> None:
        """Record a cache hit."""
        self._cache_hits += 1
        _get_logger().debug("cache_hit", cache=cache_name)
    
    def record_cache_miss(self, cache_name: str = "default") -> None:
        """Record a cache miss."""
        self._cache_misses += 1
        _get_logger().debug("cache_miss", cache=cache_name)
    
    def record_error(
        self, 
        error_type: str, 
        message: str, 
        context: dict[str, Any] | None = None
    ) -> None:
        """Record an error occurrence."""
        record = ErrorRecord(
            timestamp=datetime.now(UTC).isoformat(),
            error_type=error_type,
            message=str(message)[:500],  # Truncate long messages
            context=context or {}
        )
        self._errors.append(record)
        
        _get_logger().error(
            "error_occurred",
            error_type=error_type,
            message=str(message)[:200],
            **record.context
        )
    
    def record_page_load(self, page_name: str, duration_ms: float) -> None:
        """Record a page load time."""
        self._page_loads.append({
            "timestamp": datetime.now(UTC).isoformat(),
            "page": page_name,
            "duration_ms": duration_ms
        })
        _get_logger().info(
            "page_loaded",
            page=page_name,
            duration_ms=round(duration_ms, 2)
        )
    
    def get_stats(self) -> dict[str, Any]:
        """Get aggregated statistics for dashboard display."""
        query_list = list(self._query_times)
        
        # Query timing stats
        if query_list:
            durations = [q.duration_ms for q in query_list]
            avg_query_time = sum(durations) / len(durations)
            sorted_durations = sorted(durations)
            p50_idx = int(len(sorted_durations) * 0.50)
            p95_idx = int(len(sorted_durations) * 0.95)
            p50_query_time = sorted_durations[p50_idx] if sorted_durations else 0
            p95_query_time = sorted_durations[p95_idx] if sorted_durations else 0
            success_count = sum(1 for q in query_list if q.success)
            success_rate = (success_count / len(query_list) * 100) if query_list else 100
        else:
            avg_query_time = p50_query_time = p95_query_time = 0
            success_rate = 100
        
        # Cache stats
        total_cache = self._cache_hits + self._cache_misses
        cache_hit_rate = (self._cache_hits / total_cache * 100) if total_cache > 0 else 0
        
        # Page load stats
        page_loads = list(self._page_loads)
        avg_page_load = (
            sum(p["duration_ms"] for p in page_loads) / len(page_loads)
            if page_loads else 0
        )
        
        # Uptime
        uptime_seconds = (datetime.now(UTC) - self._start_time).total_seconds()
        
        return {
            "avg_query_time_ms": round(avg_query_time, 2),
            "p50_query_time_ms": round(p50_query_time, 2),
            "p95_query_time_ms": round(p95_query_time, 2),
            "query_success_rate_pct": round(success_rate, 1),
            "cache_hit_rate_pct": round(cache_hit_rate, 1),
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "total_queries": len(query_list),
            "avg_page_load_ms": round(avg_page_load, 2),
            "recent_errors": [
                {
                    "timestamp": e.timestamp,
                    "type": e.error_type,
                    "message": e.message
                }
                for e in list(self._errors)[-10:]
            ],
            "error_count": len(self._errors),
            "uptime_hours": round(uptime_seconds / 3600, 2)
        }
    
    def reset(self) -> None:
        """Reset all metrics (for testing)."""
        self._query_times.clear()
        self._cache_hits = 0
        self._cache_misses = 0
        self._errors.clear()
        self._page_loads.clear()
        self._start_time = datetime.now(UTC)


# Global metrics instance
metrics = MetricsStore()


def timed_operation(operation_name: str):
    """Decorator to time and log operations.
    
    Usage:
        @timed_operation("fetch_portfolio_data")
        def fetch_data():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            success = True
            result_count = 0
            try:
                result = func(*args, **kwargs)
                # Try to get result count for DataFrames
                if hasattr(result, '__len__'):
                    result_count = len(result)
                elif isinstance(result, tuple) and len(result) > 0:
                    if hasattr(result[0], '__len__'):
                        result_count = len(result[0])
                return result
            except Exception as e:
                success = False
                metrics.record_error(operation_name, str(e))
                raise
            finally:
                duration_ms = (time.perf_counter() - start) * 1000
                metrics.record_query(operation_name, duration_ms, success, result_count)
        return wrapper
    return decorator


def log_context(**context_vars):
    """Context manager to add variables to log context.
    
    Usage:
        with log_context(user_id="123", page="dashboard"):
            logger.info("processing request")
    """
    try:
        import structlog
        return structlog.contextvars.bound_contextvars(**context_vars)
    except ImportError:
        # Fallback: no-op context manager
        from contextlib import nullcontext
        return nullcontext()


# Convenience exports
logger = property(lambda self: _get_logger())
