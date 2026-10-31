"""
middleware/auth.py
Thin re-export so existing/legacy `from middleware.auth import login_required`
imports keep working. All real logic lives in core/rbac.py -- see that
module for the reasoning behind centralizing access control here
instead of ad-hoc `if session.get("role") != "admin"` checks per route.
"""

from core.rbac import login_required  # noqa: F401
