"""
models/backup_model.py
Manual/automatic database backup, restore, and verification via the
standard MySQL client tools (mysqldump / mysql), invoked as
subprocesses -- the same approach any production MySQL backup script
uses. Requires mysqldump and mysql to be installed and reachable
(either on PATH, or via config.MYSQL_CLIENT_BIN_DIR).

Credentials are passed via the MYSQL_PWD environment variable for the
subprocess, not as a command-line argument -- command-line arguments
are visible to any other process on the same machine via `ps`/task
manager
environment variables passed this way to a single child
process are not.
"""

import os
import subprocess
from datetime import datetime

from flask import current_app

from database.db import mysql


def _client_path(binary_name):
    bin_dir = current_app.config.get("MYSQL_CLIENT_BIN_DIR", "")
    return os.path.join(bin_dir, binary_name) if bin_dir else binary_name


def _backup_dir():
    path = current_app.config.get("BACKUP_DIR", "backups")
    os.makedirs(path, exist_ok=True)
    return path


def _log_backup(file_name, size_bytes, backup_type, status, error_message, triggered_by):
    cur = mysql.connection.cursor()
    cur.execute("""
        INSERT INTO backup_logs (file_name, file_size_bytes, backup_type, status, error_message, triggered_by)
        VALUES (%s,%s,%s,%s,%s,%s)
    """, (file_name, size_bytes, backup_type, status, error_message, triggered_by))
    mysql.connection.commit()
    cur.close()


def create_backup(triggered_by=None, backup_type="manual"):
    """
    Returns (ok: bool, message: str, file_path: str|None).
    """
    cfg = current_app.config
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_name = f"backup_{timestamp}.sql"
    file_path = os.path.join(_backup_dir(), file_name)

    env = os.environ.copy()
    env["MYSQL_PWD"] = cfg["MYSQL_PASSWORD"]

    cmd = [
        _client_path("mysqldump"),
        "-h", cfg["MYSQL_HOST"], "-P", str(cfg.get("MYSQL_PORT", 3306)),
        "-u", cfg["MYSQL_USER"],
        "--single-transaction", "--routines", "--triggers",
        cfg["MYSQL_DB"],
    ]

    try:
        with open(file_path, "wb") as f:
            result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, env=env, timeout=600)

        if result.returncode != 0:
            error = result.stderr.decode(errors="replace")[:500]
            _log_backup(file_name, 0, backup_type, "failed", error, triggered_by)
            if os.path.exists(file_path):
                os.remove(file_path)
            return False, f"Backup failed: {error}", None

        ok, verify_message = verify_backup(file_path)
        size = os.path.getsize(file_path)

        if not ok:
            _log_backup(file_name, size, backup_type, "failed", verify_message, triggered_by)
            return False, f"Backup completed but failed verification: {verify_message}", None

        _log_backup(file_name, size, backup_type, "success", None, triggered_by)
        return True, "Backup completed successfully.", file_path

    except FileNotFoundError:
        message = ("mysqldump was not found. Install the MySQL client tools on this server, "
                   "or set MYSQL_CLIENT_BIN_DIR in .env to their location.")
        _log_backup(file_name, 0, backup_type, "failed", message, triggered_by)
        return False, message, None
    except subprocess.TimeoutExpired:
        _log_backup(file_name, 0, backup_type, "failed", "Backup timed out after 10 minutes", triggered_by)
        return False, "Backup timed out.", None


def verify_backup(file_path):
    """Basic sanity check: file exists, is non-trivially small, and
    looks like a real SQL dump (not an error page or empty file)."""
    if not os.path.exists(file_path):
        return False, "Backup file was not created."

    size = os.path.getsize(file_path)
    if size < 100:
        return False, "Backup file is suspiciously small -- likely failed."

    with open(file_path, "rb") as f:
        head = f.read(4096).decode(errors="replace")

    if "CREATE TABLE" not in head and "MySQL dump" not in head:
        return False, "Backup file doesn't look like a valid MySQL dump."

    return True, "Backup verified."


def restore_backup(file_path, triggered_by=None):
    """
    Restores from a SQL file. Takes an automatic safety backup of the
    CURRENT database first, so a bad restore can itself be undone.
    Returns (ok: bool, message: str).
    """
    cfg = current_app.config

    safety_ok, safety_message, safety_path = create_backup(triggered_by, backup_type="manual")
    if not safety_ok:
        return False, f"Restore aborted: could not take a safety backup first ({safety_message})"

    env = os.environ.copy()
    env["MYSQL_PWD"] = cfg["MYSQL_PASSWORD"]

    cmd = [
        _client_path("mysql"),
        "-h", cfg["MYSQL_HOST"], "-P", str(cfg.get("MYSQL_PORT", 3306)),
        "-u", cfg["MYSQL_USER"],
        cfg["MYSQL_DB"],
    ]

    cur = mysql.connection.cursor()
    try:
        with open(file_path, "rb") as f:
            result = subprocess.run(cmd, stdin=f, stderr=subprocess.PIPE, env=env, timeout=900)

        if result.returncode != 0:
            error = result.stderr.decode(errors="replace")[:500]
            cur.execute("""
                INSERT INTO restore_logs (source_file, safety_backup_file, status, error_message, triggered_by)
                VALUES (%s,%s,'failed',%s,%s)
            """, (os.path.basename(file_path), os.path.basename(safety_path), error, triggered_by))
            mysql.connection.commit()
            return False, (f"Restore failed: {error}. Your data was NOT changed beyond this point -- "
                           f"a safety backup was taken first at {safety_path}.")

        cur.execute("""
            INSERT INTO restore_logs (source_file, safety_backup_file, status, triggered_by)
            VALUES (%s,%s,'success',%s)
        """, (os.path.basename(file_path), os.path.basename(safety_path), triggered_by))
        mysql.connection.commit()
        return True, "Database restored successfully."

    except subprocess.TimeoutExpired:
        return False, "Restore timed out."
    finally:
        cur.close()


def list_backups():
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT b.backup_id, b.file_name, b.file_size_bytes, b.backup_type, b.status,
               b.error_message, u.full_name, b.created_at
        FROM backup_logs b
        LEFT JOIN users u ON b.triggered_by = u.user_id
        ORDER BY b.created_at DESC
    """)
    data = cur.fetchall()
    cur.close()
    return data


def list_restores():
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT r.restore_id, r.source_file, r.safety_backup_file, r.status,
               r.error_message, u.full_name, r.created_at
        FROM restore_logs r
        LEFT JOIN users u ON r.triggered_by = u.user_id
        ORDER BY r.created_at DESC
    """)
    data = cur.fetchall()
    cur.close()
    return data
