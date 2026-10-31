"""
core/security.py
Password hashing, password policy, and account-lockout helpers.

Design decisions (why):
- We keep Werkzeug's PBKDF2-SHA256 hasher (already used by the
  existing codebase) rather than introducing bcrypt/argon2 as a hard
  dependency. It is salted, adaptive (configurable iteration count),
  and correct for this workload. Swapping to argon2id later is a
  one-line change in `hash_password` because every caller goes
  through this module instead of calling werkzeug directly.
- Password policy is centralized here so every entry point
  (self-service registration, admin-created accounts, password
  reset) enforces the same rule instead of duplicating regexes.
- Account lockout logic lives here (pure functions, no DB access)
  so it is unit-testable in isolation from Flask/MySQL.
"""

import re
from datetime import datetime, timedelta, timezone

from werkzeug.security import generate_password_hash, check_password_hash

# PBKDF2 with SHA256, 260,000 iterations -- OWASP's current minimum
# recommendation for PBKDF2-HMAC-SHA256 (as of the 2023 cheat sheet).
_HASH_METHOD = "pbkdf2:sha256:260000"

MAX_FAILED_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION = timedelta(minutes=15)

_PASSWORD_RULES = (
    (re.compile(r".{10,}"), "Password must be at least 10 characters long."),
    (re.compile(r"[A-Z]"), "Password must contain at least one uppercase letter."),
    (re.compile(r"[a-z]"), "Password must contain at least one lowercase letter."),
    (re.compile(r"[0-9]"), "Password must contain at least one digit."),
    (re.compile(r"[^A-Za-z0-9]"), "Password must contain at least one special character."),
)


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password for storage. Never store plaintext."""
    return generate_password_hash(plain_password, method=_HASH_METHOD)


def verify_password(stored_hash: str, plain_password: str) -> bool:
    """Constant-time comparison of a plaintext password against its hash."""
    if not stored_hash or not plain_password:
        return False
    try:
        return check_password_hash(stored_hash, plain_password)
    except (TypeError, ValueError):
        # Legacy or corrupted hashes must fail closed instead of turning a
        # bad credential record into a 500 response on the login endpoint.
        return False


def validate_password_strength(plain_password: str) -> list[str]:
    """
    Returns a list of human-readable violations. Empty list = password
    is acceptable. Used by both the registration/admin-create-user
    forms and the API layer so the rule can never be bypassed by
    hitting the API directly.
    """
    if not isinstance(plain_password, str):
        return ["Password is required."]
    if len(plain_password) > 128:
        return ["Password must be 128 characters or fewer."]
    violations = [msg for pattern, msg in _PASSWORD_RULES if not pattern.search(plain_password)]
    return violations


def _utcnow_naive() -> datetime:
    """Return UTC as a naive datetime for MySQL DATETIME compatibility."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def is_account_locked(locked_until: datetime | None) -> bool:
    """True if the account is currently within its lockout window."""
    if locked_until is None:
        return False
    return _utcnow_naive() < locked_until


def compute_lockout(failed_attempts: int) -> datetime | None:
    """
    Given the failed-attempt count *after* incrementing it, decide
    whether the account should now be locked, and until when.
    Returns None if the account should remain unlocked.
    """
    if failed_attempts >= MAX_FAILED_LOGIN_ATTEMPTS:
        return _utcnow_naive() + LOCKOUT_DURATION
    return None


# ---- Phase 9: password expiration ----------------------------

PASSWORD_EXPIRY_DAYS = 90


def is_password_expired(password_changed_at) -> bool:
    """password_changed_at: a datetime (as returned by the DB driver)
    or None. Treats a missing value as not-expired (e.g. legacy rows
    from before this column existed defaulted via the migration)."""
    if password_changed_at is None:
        return False
    age = _utcnow_naive() - password_changed_at
    return age.days >= PASSWORD_EXPIRY_DAYS
