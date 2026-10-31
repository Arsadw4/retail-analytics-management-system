"""
core/audit.py
Append-only audit trail.

Why a dedicated audit_logs table separate from the general
application log file (logs/app.log):
- Compliance/forensics: "who changed the selling price of SKU X, and
  when" needs to be queryable via SQL (joined against users/products),
  not grepped out of a rotating text file.
- The audit table is written to on every security-relevant or
  business-relevant mutation (login, failed login, role change,
  price change, stock adjustment, void sale, etc.), never on routine
  reads -- this keeps it small and genuinely useful for review rather
  than noise.
- Failures to write an audit entry must NEVER crash the request that
  triggered it (e.g. a successful sale should still succeed even if,
  hypothetically, the audit insert failed) -- so this function
  swallows and logs its own errors instead of propagating them.
"""

import logging

from database.db import get_db_cursor

logger = logging.getLogger("app")


def log_action(user_id, action: str, details: str = "", ip_address: str | None = None):
    """
    Record one audit event.

    Args:
        user_id: the acting user's id, or None for unauthenticated events
                 (e.g. a failed login attempt with an unknown email).
        action: a short machine-readable code, e.g. "LOGIN_SUCCESS",
                "LOGIN_FAILED", "PRODUCT_PRICE_CHANGED", "USER_ROLE_CHANGED".
        details: human-readable context, kept free-text so callers
                 don't need a schema migration to log a new kind of event.
        ip_address: caller's IP, when available (pass request.remote_addr).
    """
    try:
        with get_db_cursor() as cur:
            cur.execute(
                """
                INSERT INTO audit_logs (user_id, action, details, ip_address)
                VALUES (%s, %s, %s, %s)
                """,
                (user_id, action, details, ip_address),
            )
    except Exception:
        # Auditing must be best-effort, never request-breaking.
        logger.exception("Failed to write audit log entry (action=%s)", action)
