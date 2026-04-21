"""TTL-based in-memory cache with thread safety.

Thread safety is required because asyncio.to_thread() is used for pipeline
execution, meaning concurrent requests can trigger simultaneous cache reads
and writes from different threads.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from release_planner.constants import CACHE_TTL_CANDIDATES, CACHE_TTL_RELEASES

_cache: dict[str, tuple[float, Any]] = {}
_lock = threading.Lock()


def get(key: str, ttl: int | None = None) -> Any | None:
    """Retrieve a value from the cache if it exists and is not expired.

    Args:
        key: Cache key.
        ttl: Time-to-live in seconds. If None, uses CACHE_TTL_CANDIDATES.

    Returns:
        Cached value, or None if missing or expired.
    """
    effective_ttl = ttl if ttl is not None else CACHE_TTL_CANDIDATES
    with _lock:
        if key in _cache:
            ts, data = _cache[key]
            if time.time() - ts < effective_ttl:
                return data
            del _cache[key]
        return None


def put(key: str, data: Any) -> None:
    """Store a value in the cache with the current timestamp.

    Args:
        key: Cache key.
        data: Value to store.
    """
    with _lock:
        _cache[key] = (time.time(), data)


def invalidate(key: str) -> None:
    """Remove a key from the cache.

    Args:
        key: Cache key to remove.
    """
    with _lock:
        _cache.pop(key, None)


def clear() -> None:
    """Clear all cached data."""
    with _lock:
        _cache.clear()


def get_timestamp(key: str) -> float | None:
    """Get the timestamp when a key was cached.

    Args:
        key: Cache key.

    Returns:
        Unix timestamp, or None if key not in cache.
    """
    with _lock:
        if key in _cache:
            return _cache[key][0]
        return None
