"""
models/user_model.py
User data access. Migrated to core's pooled get_db_cursor() (see
database/db.py) since auth is the most security-sensitive path in
the app and belongs on the new connection layer from day one, rather
than the legacy compatibility shim.

Columns referenced beyond the original schema (failed_login_attempts,
locked_until, last_login_at) are added by
database/migrations/001_phase1_security_rbac.sql.
"""

from database.db import get_db_cursor
from database.errors import translate_integrity_error
import pymysql

_COLUMNS = """
    user_id, full_name, email, password, role, status,
    failed_login_attempts, locked_until, last_login_at,
    password_changed_at, created_at, mfa_enabled, mfa_secret
"""


class User:

    @staticmethod
    def get_user_by_email(email):
        with get_db_cursor(commit=False) as cur:
            cur.execute(f"SELECT {_COLUMNS} FROM users WHERE email=%s", (email,))
            return cur.fetchone()

    @staticmethod
    def get_user_by_id(user_id):
        with get_db_cursor(commit=False) as cur:
            cur.execute(f"SELECT {_COLUMNS} FROM users WHERE user_id=%s", (user_id,))
            return cur.fetchone()

    @staticmethod
    def get_all_users():
        with get_db_cursor(commit=False) as cur:
            cur.execute(f"SELECT {_COLUMNS} FROM users ORDER BY user_id DESC")
            return cur.fetchall()

    @staticmethod
    def count_users():
        with get_db_cursor(commit=False) as cur:
            cur.execute("SELECT COUNT(*) FROM users")
            return cur.fetchone()[0]

    @staticmethod
    def create_user(full_name, email, password_hash, role):
        """`password_hash` must already be hashed via core.security.hash_password."""
        try:
            with get_db_cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users (full_name, email, password, role)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (full_name, email, password_hash, role),
                )
                return cur.lastrowid
        except pymysql.err.IntegrityError as exc:
            translate_integrity_error(exc)

    @staticmethod
    def update_user(user_id, full_name, email, role, status=None):
        try:
            with get_db_cursor() as cur:
                cur.execute(
                    """
                    UPDATE users
                    SET full_name=%s, email=%s, role=%s,
                        status=COALESCE(%s, status)
                    WHERE user_id=%s
                    """,
                    (full_name, email, role, status, user_id),
                )
                cur.execute(
                    "UPDATE employees SET employee_name=%s, email=%s WHERE user_id=%s",
                    (full_name, email, user_id),
                )
                if status == "inactive":
                    cur.execute("DELETE FROM user_sessions WHERE user_id=%s", (user_id,))
        except pymysql.err.IntegrityError as exc:
            translate_integrity_error(exc)

    @staticmethod
    def update_profile(user_id, full_name, email):
        try:
            with get_db_cursor() as cur:
                cur.execute(
                    "UPDATE users SET full_name=%s, email=%s WHERE user_id=%s",
                    (full_name, email, user_id),
                )
        except pymysql.err.IntegrityError as exc:
            translate_integrity_error(exc)

    @staticmethod
    def update_password(user_id, password_hash):
        with get_db_cursor() as cur:
            cur.execute(
                """
                UPDATE users
                SET password=%s, password_changed_at=NOW(),
                    failed_login_attempts=0, locked_until=NULL
                WHERE user_id=%s
                """,
                (password_hash, user_id),
            )
            cur.execute("DELETE FROM user_sessions WHERE user_id=%s", (user_id,))

    @staticmethod
    def delete_user(user_id):
        with get_db_cursor() as cur:
            cur.execute("DELETE FROM users WHERE user_id=%s", (user_id,))

    # ---- Account lockout / brute-force defense -----------------

    @staticmethod
    def register_failed_login(user_id):
        """Increments the failed-attempt counter and returns the new count."""
        with get_db_cursor() as cur:
            cur.execute(
                "UPDATE users SET failed_login_attempts = failed_login_attempts + 1 "
                "WHERE user_id=%s",
                (user_id,),
            )
            cur.execute(
                "SELECT failed_login_attempts FROM users WHERE user_id=%s",
                (user_id,),
            )
            return cur.fetchone()[0]

    @staticmethod
    def lock_account(user_id, locked_until):
        with get_db_cursor() as cur:
            cur.execute(
                "UPDATE users SET locked_until=%s WHERE user_id=%s",
                (locked_until, user_id),
            )

    @staticmethod
    def register_successful_login(user_id):
        with get_db_cursor() as cur:
            cur.execute(
                """
                UPDATE users
                SET failed_login_attempts=0, locked_until=NULL, last_login_at=NOW()
                WHERE user_id=%s
                """,
                (user_id,),
            )
