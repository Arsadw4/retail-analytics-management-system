"""
core/cache.py
Minimal in-process TTL cache for expensive, read-heavy queries (e.g.
AI/BI dashboard aggregates). Deliberately simple -- a dict with
expiry timestamps behind a lock, no Redis dependency. Per-process
(each worker in a multi-worker deployment has its own cache), which
is a fine tradeoff for dashboard-style data that doesn't need to be
byte-identical across workers. See PERFORMANCE_GUIDE.md for the
Redis/Flask-Caching upgrade path if you need a shared cache across
workers or a persistent cache across restarts.
"""

import time
from threading import Lock
from functools import wraps

_store = {}
_lock = Lock()


def cached(ttl_seconds=60):
    """
    Decorator: caches a function's return value for `ttl_seconds`,
    keyed by function name + args. Use only on pure read functions
    with no side effects (e.g. AI dashboard aggregates) -- never on
    anything that writes data or must reflect the very latest state
    (e.g. current stock during checkout).
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            key = (func.__module__, func.__name__, args, tuple(sorted(kwargs.items())))
            now = time.time()

            with _lock:
                entry = _store.get(key)
                if entry and entry[1] > now:
                    return entry[0]

            result = func(*args, **kwargs)

            with _lock:
                _store[key] = (result, now + ttl_seconds)

            return result
        return wrapper
    return decorator


def clear():
    with _lock:
        _store.clear()


def stats():
    with _lock:
        return {"entries": len(_store)}
