"""
Simple in-memory cache for frequently accessed data.
Tenant-specific store names, settings, etc.
"""
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import threading

_cache: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()

DEFAULT_TTL = 300  # 5 minutes


def set_cache(key: str, value: Any, ttl: int = DEFAULT_TTL):
    """Set cache entry with TTL in seconds."""
    with _lock:
        _cache[key] = {
            "value": value,
            "expires_at": datetime.utcnow() + timedelta(seconds=ttl)
        }


def get_cache(key: str) -> Optional[Any]:
    """Get cache entry if not expired."""
    with _lock:
        entry = _cache.get(key)
        if not entry:
            return None

        if datetime.utcnow() > entry["expires_at"]:
            del _cache[key]
            return None

        return entry["value"]


def invalidate_cache(key: str):
    """Invalidate specific cache entry."""
    with _lock:
        _cache.pop(key, None)


def clear_cache():
    """Clear all cache entries."""
    with _lock:
        _cache.clear()
