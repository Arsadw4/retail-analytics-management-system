import logging
import secrets

from database.db import get_db_cursor
from flask import current_app, has_app_context

logger = logging.getLogger("app")


class UserSession:
    """
    Records active logins for session management. The signed Flask cookie
    stores a token that role-protected requests validate against this table;
    deleting the row revokes that cookie on its next protected request.
    """

    @staticmethod
    def create(user_id, ip_address, user_agent):
        token = secrets.token_hex(32)
        try:
            with get_db_cursor() as cur:
                cur.execute("""
                    INSERT INTO user_sessions (user_id, session_token, ip_address, user_agent)
                    VALUES (%s,%s,%s,%s)
                """, (user_id, token, ip_address, (user_agent or "")[:255]))
        except Exception:
            logger.exception("Failed to record session for user %s", user_id)
            return None
        return token

    @staticmethod
    def is_active(token, user_id):
        if not token or not user_id:
            return False
        try:
            timeout_minutes = 60
            if has_app_context():
                timeout_minutes = int(current_app.config.get("SESSION_TIMEOUT_MINUTES", 60))
            timeout_minutes = max(1, timeout_minutes)
            with get_db_cursor(commit=False) as cur:
                cur.execute(
                    """
                    SELECT 1
                    FROM user_sessions
                    WHERE session_token=%s
                      AND user_id=%s
                      AND last_seen_at >= NOW() - INTERVAL %s MINUTE
                    """,
                    (token, user_id, timeout_minutes),
                )
                row = cur.fetchone()
            return row is not None
        except Exception:
            logger.exception("Failed to validate an active user session.")
            return False

    @staticmethod
    def touch(token):
        try:
            with get_db_cursor() as cur:
                cur.execute("UPDATE user_sessions SET last_seen_at=NOW() WHERE session_token=%s", (token,))
        except Exception:
            logger.exception("Failed to update user session activity.")

    @staticmethod
    def delete_by_token(token):
        try:
            with get_db_cursor() as cur:
                cur.execute("DELETE FROM user_sessions WHERE session_token=%s", (token,))
            return True
        except Exception:
            logger.exception("Failed to revoke a user session.")
            return False

    @staticmethod
    def delete_for_user(user_id):
        """Revoke every active server-side session for a user."""
        try:
            with get_db_cursor() as cur:
                cur.execute("DELETE FROM user_sessions WHERE user_id=%s", (user_id,))
            return True
        except Exception:
            logger.exception("Failed to revoke sessions for user %s", user_id)
            return False

    @staticmethod
    def get_all():
        with get_db_cursor(commit=False) as cur:
            cur.execute("""
                SELECT s.session_id, u.full_name, u.email, s.ip_address, s.user_agent,
                       s.created_at, s.last_seen_at
                FROM user_sessions s JOIN users u ON s.user_id = u.user_id
                ORDER BY s.last_seen_at DESC
            """)
            return cur.fetchall()

    @staticmethod
    def revoke(session_id):
        with get_db_cursor() as cur:
            cur.execute("DELETE FROM user_sessions WHERE session_id=%s", (session_id,))
