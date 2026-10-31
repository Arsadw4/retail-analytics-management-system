#!/usr/bin/env python3
"""
scripts/backup_database.py
Standalone CLI for scheduled (automatic) backups -- meant to be run
by cron (Linux/macOS) or Task Scheduler (Windows), NOT by an in-app
scheduler.

Why a standalone script instead of an in-process scheduler (e.g.
APScheduler running inside Flask): a production deployment of this
app typically runs multiple worker processes (Gunicorn/uWSGI with
several workers, or multiple container replicas). An in-process
scheduler would fire once per worker -- multiple simultaneous backups
racing each other -- and does nothing at all if the process restarts
at exactly the scheduled moment. A cron job (or Task Scheduler task)
calling this script is the standard, reliable pattern real deployments
use, independent of how many app workers are running.

Usage:
    python scripts/backup_database.py

Example crontab entry (daily at 2 AM):
    0 2 * * * cd /path/to/app && /path/to/venv/bin/python scripts/backup_database.py >> logs/backup_cron.log 2>&1

See BACKUP_RECOVERY_GUIDE.md for the Windows Task Scheduler equivalent.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from models.backup_model import create_backup


def main():
    app = create_app()
    with app.app_context():
        ok, message, path = create_backup(triggered_by=None, backup_type="scheduled")
        print(f"[{'OK' if ok else 'FAILED'}] {message}" + (f" -> {path}" if path else ""))
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
