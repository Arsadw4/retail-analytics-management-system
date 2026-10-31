"""
core/perf_monitor.py
Lightweight in-memory request-timing tracker -- no external
dependency, no new table. Deliberately simple: a rolling window of the
last N request timings kept in a process-local deque. Resets on app
restart and is per-worker-process in a multi-worker deployment (each
worker shows only its own traffic) -- documented limitation, see
PERFORMANCE_GUIDE.md for the Prometheus/APM upgrade path if you need
cross-process aggregated metrics.
"""

import time
from collections import deque, defaultdict
from threading import Lock

_WINDOW_SIZE = 500
_lock = Lock()
_timings = deque(maxlen=_WINDOW_SIZE)  # list of (endpoint, duration_ms, status_code, timestamp)


def register(app):
    @app.before_request
    def _start_timer():
        from flask import g
        g._perf_start = time.time()

    @app.after_request
    def _record_timing(response):
        from flask import g, request
        start = getattr(g, "_perf_start", None)
        if start is not None:
            duration_ms = (time.time() - start) * 1000
            with _lock:
                _timings.append((request.endpoint or request.path, duration_ms,
                                 response.status_code, time.time()))
        return response

    return app


def get_stats():
    with _lock:
        snapshot = list(_timings)

    if not snapshot:
        return {"request_count": 0, "avg_ms": 0, "max_ms": 0, "slowest_endpoints": [], "error_count": 0}

    durations = [t[1] for t in snapshot]
    errors = [t for t in snapshot if t[2] >= 500]

    by_endpoint = defaultdict(list)
    for endpoint, duration, status, ts in snapshot:
        by_endpoint[endpoint].append(duration)

    slowest = sorted(
        ({"endpoint": ep, "avg_ms": round(sum(d) / len(d), 1), "count": len(d)} for ep, d in by_endpoint.items()),
        key=lambda r: r["avg_ms"], reverse=True
    )[:10]

    return {
        "request_count": len(snapshot),
        "avg_ms": round(sum(durations) / len(durations), 1),
        "max_ms": round(max(durations), 1),
        "slowest_endpoints": slowest,
        "error_count": len(errors)
    }
