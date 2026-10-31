"""
models/monitoring_model.py
System health: database size, disk usage, active sessions, recent
errors from the application log, and DB connectivity check.
"""

import os
import logging
import shutil

from flask import current_app

from database.db import mysql

logger = logging.getLogger(__name__)


def database_ping():
    try:
        cur = mysql.connection.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        cur.close()
        return True
    except Exception:
        logger.exception("Database health check failed.")
        return False


def database_size_mb():
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT ROUND(SUM(data_length + index_length) / 1024 / 1024, 2)
        FROM information_schema.TABLES
        WHERE table_schema = DATABASE()
    """)
    row = cur.fetchone()
    cur.close()
    return float(row[0]) if row and row[0] else 0.0


def table_sizes(limit=10):
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT table_name, ROUND((data_length + index_length) / 1024 / 1024, 2) AS size_mb, table_rows
        FROM information_schema.TABLES
        WHERE table_schema = DATABASE()
        ORDER BY (data_length + index_length) DESC
        LIMIT %s
    """, (limit,))
    data = cur.fetchall()
    cur.close()
    return data


def _dir_size_mb(path):
    if not os.path.isdir(path):
        return 0.0
    total = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if os.path.exists(fp):
                total += os.path.getsize(fp)
    return round(total / 1024 / 1024, 2)


def storage_usage():
    disk = shutil.disk_usage(".")
    return {
        "uploads_mb": _dir_size_mb("static/uploads"),
        "logs_mb": _dir_size_mb(current_app.config.get("LOG_DIR", "logs")),
        "backups_mb": _dir_size_mb(current_app.config.get("BACKUP_DIR", "backups")),
        "disk_total_gb": round(disk.total / 1024 / 1024 / 1024, 1),
        "disk_used_gb": round(disk.used / 1024 / 1024 / 1024, 1),
        "disk_free_gb": round(disk.free / 1024 / 1024 / 1024, 1),
        "disk_used_pct": round(disk.used / disk.total * 100, 1) if disk.total else 0
    }


def active_session_count():
    cur = mysql.connection.cursor()
    cur.execute("SELECT COUNT(*) FROM user_sessions")
    count = cur.fetchone()[0]
    cur.close()
    return count


def recent_log_lines(n=100, level_filter=None):
    """Tails the application log file (Phase 1's core/logging_config.py)."""
    log_path = os.path.join(current_app.config.get("LOG_DIR", "logs"), "app.log")
    if not os.path.exists(log_path):
        return []

    with open(log_path, "r", errors="replace") as f:
        lines = f.readlines()[-2000:]  # cap how much we ever read into memory

    if level_filter:
        lines = [l for l in lines if f"| {level_filter}" in l]

    return [l.rstrip("\n") for l in lines[-n:]]


def recent_error_count(lines_to_scan=2000):
    log_path = os.path.join(current_app.config.get("LOG_DIR", "logs"), "app.log")
    if not os.path.exists(log_path):
        return 0
    with open(log_path, "r", errors="replace") as f:
        lines = f.readlines()[-lines_to_scan:]
    return sum(1 for l in lines if "| ERROR" in l or "| CRITICAL" in l)
