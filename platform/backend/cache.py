"""
Caching abstraction layer.

Current implementation: **MemoryCache** (thread-safe in-process dict with TTL).
Future drop-in: **RedisCache** via ``redis-py``.

Usage:
    from backend.cache import get_cache

    cache = get_cache()
    cache.set("my_key", expensive_result, ttl=120)
    val = cache.get("my_key")  # returns None after TTL expires
"""

from __future__ import annotations

import functools
import hashlib
import logging
import threading
import time
from typing import Any, Protocol, runtime_checkable

from services.config import get_settings

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# Protocol
# ═══════════════════════════════════════════════════════════════════════


@runtime_checkable
class CacheBackend(Protocol):
    """Minimal contract for a cache backend."""

    def get(self, key: str) -> Any | None: ...
    def set(self, key: str, value: Any, ttl: int | None = None) -> None: ...
    def delete(self, key: str) -> bool: ...
    def clear(self) -> None: ...
    def has(self, key: str) -> bool: ...


# ═══════════════════════════════════════════════════════════════════════
# In-memory implementation
# ═══════════════════════════════════════════════════════════════════════


class _Entry:
    __slots__ = ("value", "expires_at")

    def __init__(self, value: Any, ttl: int | None) -> None:
        self.value = value
        self.expires_at = (time.monotonic() + ttl) if ttl else None

    @property
    def expired(self) -> bool:
        return self.expires_at is not None and time.monotonic() > self.expires_at


class MemoryCache:
    """Thread-safe in-memory cache with per-key TTL.

    Parameters:
        default_ttl: Fallback TTL in seconds when ``set()`` is called
            without an explicit ``ttl``.  ``None`` → no expiry.
        max_size: Approximate cap on entries before oldest are evicted.
    """

    def __init__(self, default_ttl: int | None = 300, max_size: int = 2_000) -> None:
        self._store: dict[str, _Entry] = {}
        self._lock = threading.Lock()
        self._default_ttl = default_ttl
        self._max_size = max_size

    # ── public API ─────────────────────────────────────────────────────

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if entry.expired:
                del self._store[key]
                return None
            return entry.value

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        effective_ttl = ttl if ttl is not None else self._default_ttl
        with self._lock:
            self._store[key] = _Entry(value, effective_ttl)
            self._maybe_evict()

    def delete(self, key: str) -> bool:
        with self._lock:
            return self._store.pop(key, None) is not None

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def has(self, key: str) -> bool:
        return self.get(key) is not None

    # ── helpers ────────────────────────────────────────────────────────

    def _maybe_evict(self) -> None:
        """Evict expired + oldest entries when over capacity (called under lock)."""
        # Purge expired first
        expired_keys = [k for k, v in self._store.items() if v.expired]
        for k in expired_keys:
            del self._store[k]

        # If still over capacity, drop oldest entries
        if len(self._store) > self._max_size:
            excess = len(self._store) - self._max_size
            for k in list(self._store.keys())[:excess]:
                del self._store[k]


# ═══════════════════════════════════════════════════════════════════════
# Redis placeholder
# ═══════════════════════════════════════════════════════════════════════


class RedisCache:  # pragma: no cover
    """
    Placeholder for Redis-backed cache.

    Swap in by setting ``CACHE_BACKEND=redis`` and ``REDIS_URL`` in ``.env``.
    Requires ``pip install redis``.
    """

    def __init__(self, url: str, default_ttl: int = 300) -> None:
        raise NotImplementedError(
            "RedisCache is planned for a future release.  "
            "Set CACHE_BACKEND=memory (default) for now."
        )


# ═══════════════════════════════════════════════════════════════════════
# Factory & decorator
# ═══════════════════════════════════════════════════════════════════════

_cache_instance: CacheBackend | None = None


def get_cache() -> CacheBackend:
    """Return a module-level singleton cache."""
    global _cache_instance
    if _cache_instance is not None:
        return _cache_instance

    settings = get_settings()

    if settings.cache_backend == "memory":
        _cache_instance = MemoryCache(default_ttl=settings.query_cache_ttl)
    elif settings.cache_backend == "redis":
        _cache_instance = RedisCache(url=settings.redis_url, default_ttl=settings.query_cache_ttl)
    else:
        raise ValueError(f"Unknown CACHE_BACKEND: {settings.cache_backend}")

    return _cache_instance


def cached(namespace: str, ttl: int | None = None):
    """
    Decorator that caches the return value of a function.

    The cache key is derived from ``namespace`` + the function arguments.

    Example::

        @cached("portfolio_stats", ttl=120)
        def portfolio_stats(plant_uid: str) -> dict: ...
    """

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            raw = f"{namespace}|{args}|{sorted(kwargs.items())}"
            key = f"{namespace}:{hashlib.sha256(raw.encode()).hexdigest()[:16]}"
            c = get_cache()
            hit = c.get(key)
            if hit is not None:
                return hit
            result = fn(*args, **kwargs)
            c.set(key, result, ttl=ttl)
            return result

        return wrapper

    return decorator
