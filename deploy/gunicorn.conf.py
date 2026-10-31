"""
deploy/gunicorn.conf.py
Production Gunicorn configuration.

Run: gunicorn --config deploy/gunicorn.conf.py wsgi:app
"""

import multiprocessing
import os

# --- Networking ---
bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:8000")

# --- Workers ---
# (2 x CPU cores) + 1 is the standard starting point for sync workers
# handling a mix of I/O-bound (DB queries) and CPU-bound (PDF/Excel
# generation, image resizing) work. Override via env var if your
# host's core count doesn't match the container's.
workers = int(os.environ.get("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1))
worker_class = "sync"
threads = int(os.environ.get("GUNICORN_THREADS", 2))

# Recycle workers periodically -- guards against slow memory growth
# from any long-running worker (e.g. a stuck PDF/Excel generation)
# rather than requiring a manual restart.
max_requests = 1000
max_requests_jitter = 100

timeout = int(os.environ.get("GUNICORN_TIMEOUT", 60))  # DB backup/restore routes need headroom
graceful_timeout = 30
keepalive = 5

# --- Logging ---
accesslog = "-"   # stdout -- let the container/systemd runtime collect it
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")

# --- Process naming ---
proc_name = "retail_analytics_system"

# --- Preload ---
# Deliberately FALSE. app.py builds the DBUtils connection pool
# (Phase 1's init_db_pool) at import time, as soon as `from app import
# app` runs. If preload_app were True, gunicorn would import the app
# ONCE in the master process and every forked worker would inherit
# (via fork()) the SAME underlying database socket file descriptors --
# a well-known source of connection corruption/hangs when multiple
# processes share one DB connection. With preload_app=False (the
# gunicorn default), each worker imports wsgi.py independently after
# forking, so each one builds its own separate connection pool.
preload_app = False
