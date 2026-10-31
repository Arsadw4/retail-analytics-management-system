"""
models/mfa_model.py
Optional per-user TOTP-based multi-factor authentication (RFC 6238 --
compatible with Google Authenticator, Authy, etc. via pyotp). Opt-in:
a user with mfa_enabled=FALSE (the default for every existing account)
logs in exactly as before -- the second factor is only asked for once
they've deliberately enabled it from their profile.
"""

import pyotp

from database.db import get_db_cursor


class MFA:

    @staticmethod
    def generate_secret():
        return pyotp.random_base32()

    @staticmethod
    def provisioning_uri(email, secret, issuer):
        return pyotp.totp.TOTP(secret).provisioning_uri(name=email, issuer_name=issuer)

    @staticmethod
    def verify_code(secret, code):
        if not secret or not code:
            return False
        try:
            return pyotp.TOTP(secret).verify(code, valid_window=1)
        except Exception:
            return False

    @staticmethod
    def get_pending_secret(user_id):
        """Secret stored but not yet confirmed (mfa_enabled still FALSE)."""
        with get_db_cursor(commit=False) as cur:
            cur.execute("SELECT mfa_secret FROM users WHERE user_id=%s", (user_id,))
            row = cur.fetchone()
            return row[0] if row else None

    @staticmethod
    def save_pending_secret(user_id, secret):
        with get_db_cursor() as cur:
            cur.execute("UPDATE users SET mfa_secret=%s WHERE user_id=%s", (secret, user_id))

    @staticmethod
    def enable(user_id):
        with get_db_cursor() as cur:
            cur.execute("UPDATE users SET mfa_enabled=TRUE WHERE user_id=%s", (user_id,))

    @staticmethod
    def disable(user_id):
        with get_db_cursor() as cur:
            cur.execute("UPDATE users SET mfa_enabled=FALSE, mfa_secret=NULL WHERE user_id=%s", (user_id,))

    @staticmethod
    def get_status(user_id):
        with get_db_cursor(commit=False) as cur:
            cur.execute("SELECT mfa_enabled, mfa_secret FROM users WHERE user_id=%s", (user_id,))
            return cur.fetchone()
