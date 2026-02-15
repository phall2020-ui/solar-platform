"""
Centralized caching layer for expensive aggregates and queries.
Supports both in-memory and DuckDB-backed caching with TTL and cache warming.
"""
import base64
import hashlib
import logging
import pickle
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from solar_platform.db.utils import get_connection

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Represents a cache entry."""
    key: str
    value: Any
    created_at: float
    ttl: int
    hits: int = 0


class CacheLayer:
    """Centralized cache with memory and DuckDB backend options."""
    
    def __init__(
        self,
        backend: str = "memory",
        db_path: str | None = None,
        default_ttl: int = 300
    ):
        """
        Initialize cache layer.
        
        Args:
            backend: "memory" or "duckdb"
            db_path: Path to DuckDB database (required for duckdb backend)
            default_ttl: Default time-to-live in seconds
        """
        self.backend = backend
        self.db_path = db_path
        self.default_ttl = default_ttl
        self._memory_cache: dict[str, CacheEntry] = {}
        self._lock = threading.Lock()
        
        if backend == "sqlite" or backend == "duckdb":
            if not db_path:
                raise ValueError("db_path required for duckdb backend")
            self._init_duckdb()
    
    def _init_duckdb(self) -> None:
        """Initialize DuckDB cache table."""
        with get_connection(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS _cache (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    created_at DOUBLE,
                    ttl INTEGER,
                    hits INTEGER DEFAULT 0
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cache_created ON _cache(created_at)")
    
    def _make_key(self, namespace: str, *args, **kwargs) -> str:
        """
        Generate cache key from namespace and parameters.
        
        Args:
            namespace: Cache namespace (e.g., "portfolio_stats")
            *args: Positional arguments to include in key
            **kwargs: Keyword arguments to include in key
            
        Returns:
            str: Cache key
        """
        # Serialize args and kwargs to create a unique key
        key_parts = [namespace]
        for arg in args:
            key_parts.append(str(arg))
        for k, v in sorted(kwargs.items()):
            key_parts.append(f"{k}={v}")
        
        key_string = "|".join(key_parts)
        # Hash for consistent length
        key_hash = hashlib.sha256(key_string.encode()).hexdigest()
        return f"{namespace}:{key_hash[:16]}"
    
    def get(self, key: str) -> Any | None:
        """
        Get value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found/expired
        """
        if self.backend == "memory":
            return self._get_memory(key)
        else:
            return self._get_sqlite(key)
    
    def _get_memory(self, key: str) -> Any | None:
        """Get from memory cache."""
        with self._lock:
            entry = self._memory_cache.get(key)
            if entry:
                # Check if expired
                if time.time() - entry.created_at > entry.ttl:
                    del self._memory_cache[key]
                    logger.debug("Cache expired: %s", key)
                    return None
                
                entry.hits += 1
                logger.debug("Cache hit: %s (hits=%d)", key, entry.hits)
                return entry.value
        logger.debug("Cache miss: %s", key)
        return None
    
    def _get_sqlite(self, key: str) -> Any | None:
        """Get from DuckDB cache."""
        try:
            with get_connection(self.db_path) as conn:
                result = conn.execute(
                    "SELECT value, created_at, ttl, hits FROM _cache WHERE key = ?",
                    (key,)
                ).fetchone()
                
                if result:
                    value_str, created_at, ttl, hits = result
                    
                    # Check if expired
                    if time.time() - created_at > ttl:
                        conn.execute("DELETE FROM _cache WHERE key = ?", (key,))
                        logger.debug("Cache expired (duckdb): %s", key)
                        return None
                    
                    # Increment hit counter
                    conn.execute(
                        "UPDATE _cache SET hits = hits + 1 WHERE key = ?",
                        (key,)
                    )
                    
                    logger.debug("Cache hit (duckdb): %s", key)
                    # Deserialize value
                    return self._deserialize(value_str)
                
                logger.debug("Cache miss (duckdb): %s", key)
                return None
            
        except Exception as e:
            logger.error("Cache get error (duckdb): %s, key=%s", e, key)
            return None
    
    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """
        Set value in cache.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (uses default if None)
        """
        ttl = ttl if ttl is not None else self.default_ttl
        
        if self.backend == "memory":
            self._set_memory(key, value, ttl)
        else:
            self._set_sqlite(key, value, ttl)
    
    def _set_memory(self, key: str, value: Any, ttl: int) -> None:
        """Set in memory cache."""
        with self._lock:
            self._memory_cache[key] = CacheEntry(
                key=key,
                value=value,
                created_at=time.time(),
                ttl=ttl,
                hits=0
            )
    
    def _set_sqlite(self, key: str, value: Any, ttl: int) -> None:
        """Set in DuckDB cache."""
        try:
            value_str = self._serialize(value)
            with get_connection(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO _cache (key, value, created_at, ttl, hits)
                    VALUES (?, ?, ?, ?, 0)
                    """,
                    (key, value_str, time.time(), ttl)
                )
        except Exception as e:
            logger.error("Cache set error (duckdb): %s, key=%s", e, key)
    
    def _serialize(self, value: Any) -> str:
        """Serialize value for storage."""
        # Use pickle and base64 for general Python objects
        pickled = pickle.dumps(value)
        return base64.b64encode(pickled).decode('utf-8')
    
    def _deserialize(self, value_str: str) -> Any:
        """Deserialize value from storage."""
        decoded = base64.b64decode(value_str.encode('utf-8'))
        return pickle.loads(decoded)
    
    def delete(self, key: str) -> None:
        """Delete key from cache."""
        if self.backend == "memory":
            with self._lock:
                self._memory_cache.pop(key, None)
        else:
            try:
                with get_connection(self.db_path) as conn:
                    conn.execute("DELETE FROM _cache WHERE key = ?", (key,))
            except Exception as e:
                logger.error("Cache delete error: %s, key=%s", e, key)
    
    def clear(self, namespace: str | None = None) -> None:
        """
        Clear cache entries.
        
        Args:
            namespace: If provided, only clear entries with this namespace prefix
        """
        if self.backend == "memory":
            with self._lock:
                if namespace:
                    keys_to_delete = [k for k in self._memory_cache.keys() if k.startswith(f"{namespace}:")]
                    for key in keys_to_delete:
                        del self._memory_cache[key]
                else:
                    self._memory_cache.clear()
        else:
            try:
                with get_connection(self.db_path) as conn:
                    if namespace:
                        conn.execute("DELETE FROM _cache WHERE key LIKE ?", (f"{namespace}:%",))
                    else:
                        conn.execute("DELETE FROM _cache")
            except Exception as e:
                logger.error("Cache clear error: %s, namespace=%s", e, namespace)
    
    def cleanup_expired(self) -> int | None:
        """Remove expired entries from cache."""
        now = time.time()
        
        if self.backend == "memory":
            with self._lock:
                expired_keys = [
                    key for key, entry in self._memory_cache.items()
                    if now - entry.created_at > entry.ttl
                ]
                for key in expired_keys:
                    del self._memory_cache[key]
        else:
            try:
                with get_connection(self.db_path) as conn:
                    # Delete entries where current_time - created_at > ttl
                    result = conn.execute(
                        "DELETE FROM _cache WHERE ? - created_at > ttl RETURNING *",
                        (now,)
                    ).fetchall()
                    deleted = len(result)
                    return deleted
            except Exception as e:
                logger.error("Cache cleanup error: %s", e)
                return 0
    
    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        if self.backend == "memory":
            with self._lock:
                return {
                    "backend": "memory",
                    "total_entries": len(self._memory_cache),
                    "total_hits": sum(e.hits for e in self._memory_cache.values()),
                    "namespaces": list(set(k.split(":")[0] for k in self._memory_cache.keys()))
                }
        else:
            try:
                with get_connection(self.db_path) as conn:
                    result = conn.execute("SELECT COUNT(*), SUM(hits) FROM _cache").fetchone()
                    total_entries, total_hits = result
                    
                    namespaces_result = conn.execute("SELECT DISTINCT split_part(key, ':', 1) FROM _cache").fetchall()
                    namespaces = [row[0] for row in namespaces_result if row[0]]
                    
                    return {
                    "backend": "duckdb",
                    "total_entries": total_entries or 0,
                    "total_hits": total_hits or 0,
                    "namespaces": namespaces
                }
            except Exception as e:
                logger.error("Cache stats error: %s", e)
                return {"backend": "duckdb", "error": str(e)}
    
    def get_or_compute(
        self,
        namespace: str,
        compute_func: Callable,
        *args,
        ttl: int | None = None,
        **kwargs
    ) -> Any:
        """
        Get from cache or compute and cache the result.
        
        Args:
            namespace: Cache namespace
            compute_func: Function to call if cache miss
            *args: Arguments to pass to compute_func (also used in cache key)
            ttl: Cache TTL
            **kwargs: Keyword arguments for compute_func (also used in cache key)
            
        Returns:
            Cached or computed value
        """
        key = self._make_key(namespace, *args, **kwargs)
        
        # Try cache first
        cached = self.get(key)
        if cached is not None:
            return cached
        
        # Compute and cache
        value = compute_func(*args, **kwargs)
        self.set(key, value, ttl)
        return value
    
    def warm_cache(self, warm_funcs: list[dict[str, Any]]) -> None:
        """
        Warm cache by pre-computing values.
        
        Args:
            warm_funcs: List of dicts with keys: namespace, func, args, kwargs, ttl
        """
        for config in warm_funcs:
            namespace = config.get("namespace")
            func = config.get("func")
            args = config.get("args", ())
            kwargs = config.get("kwargs", {})
            ttl = config.get("ttl")
            
            if not namespace or not func:
                continue
            
            try:
                self.get_or_compute(namespace, func, *args, ttl=ttl, **kwargs)
            except Exception as e:
                logger.error("Cache warming error for namespace=%s: %s", namespace, e)


# Global singleton instance
_cache_layer: CacheLayer | None = None


def get_cache_layer(
    backend: str = "memory",
    db_path: str | None = None,
    default_ttl: int = 300
) -> CacheLayer:
    """
    Get or create global cache layer instance.
    
    Args:
        backend: "memory" or "duckdb" (also accepts "sqlite" for backwards compatibility)
        db_path: Path to DuckDB database (for duckdb backend)
        default_ttl: Default TTL in seconds
        
    Returns:
        CacheLayer instance
    """
    global _cache_layer
    if _cache_layer is None:
        _cache_layer = CacheLayer(backend=backend, db_path=db_path, default_ttl=default_ttl)
    return _cache_layer


def cached(namespace: str, ttl: int | None = None) -> Callable:
    """
    Decorator to cache function results.
    
    Args:
        namespace: Cache namespace
        ttl: Cache TTL in seconds
        
    Example:
        @cached("portfolio_stats", ttl=600)
        def get_portfolio_stats(table_name):
            # expensive computation
            return stats
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            cache = get_cache_layer()
            return cache.get_or_compute(namespace, func, *args, ttl=ttl, **kwargs)
        return wrapper
    return decorator
