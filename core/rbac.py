"""
core/rbac.py
Centralized Role-Based Access Control.

Why this file exists:
The original codebase guarded pages with ad-hoc checks scattered
inside each view function, e.g.:

    if session.get("role") != "admin":
        return redirect("/employee/dashboard")

This is a broken-access-control risk (OWASP Top 10 #1): it is easy
to add a new route and simply forget the check, silently leaving it
public. Centralizing the check into decorators means access control
is declared in the route signature itself, is impossible to forget
without it being visually obvious in code review, and is enforced
identically everywhere.

Roles: 'super_admin' is a universal bypass (see below) added in
Phase 6 for enterprise administration
'admin' remains the original
top operational role and is unchanged from Phase 1. The specialized
Phase 6 roles (cashier, inventory_manager, hr, accountant) are plain
allow-list entries -- they were added to the specific existing
@role_required(...) calls where they clearly belong (POS for cashier,
inventory for inventory_manager, etc.) rather than being given any
implicit hierarchy, to avoid touching the logic of routes they don't
need.
"""

from functools import wraps
from flask import abort, g, redirect, request, session, url_for

from core.audit import log_action

ROLES = ("employee", "cashier", "inventory_manager", "hr", "accountant",
         "manager", "admin", "super_admin")

SUPER_ADMIN = "super_admin"


def _current_role():
    return session.get("role")


def _authenticated_user():
    """Return the active database user only when its server session is valid."""
    if hasattr(g, "authenticated_user"):
        return g.authenticated_user

    user_id = session.get("user_id")
    token = session.get("session_token")
    if not user_id or not token:
        session.clear()
        g.authenticated_user = None
        return None

    from models.user_model import User
    from models.session_model import UserSession

    user = User.get_user_by_id(user_id)
    if user is None or user[5] != "active":
        UserSession.delete_by_token(token)
        session.clear()
        g.authenticated_user = None
        return None

    if not UserSession.is_active(token, user_id):
        UserSession.delete_by_token(token)
        session.clear()
        g.authenticated_user = None
        return None

    session["role"] = user[4]
    UserSession.touch(token)
    g.authenticated_user = user
    return user


def login_required(view_func):
    """Require any authenticated session. Redirects to /login, preserving
    the originally requested URL so the user lands where they intended
    after signing in."""

    @wraps(view_func)
    def wrapped(*args, **kwargs):
        user = _authenticated_user()
        if user is None:
            return redirect(url_for("auth.login", next=request.path))
        if session.get("must_change_password") and request.endpoint not in (
            "auth.change_password_required", "auth.logout"
        ):
            return redirect(url_for("auth.change_password_required"))
        return view_func(*args, **kwargs)

    return wrapped


def role_required(*allowed_roles):
    """
    Require the session's role to be one of `allowed_roles`.
    Usage:
        @admin_bp.route("/admin/users")
        @role_required("admin")
        def admin_users(): ...

        @sales_bp.route("/sales/create")
        @role_required("admin", "manager", "employee")
        def create_sale(): ...

    Unauthenticated users are redirected to login (they haven't proven
    who they are yet, so this isn't sensitive information disclosure).
    Authenticated-but-unauthorized users get an HTTP 403 -- silently
    redirecting them elsewhere hides *that* an authorization failure
    happened, which makes audit/debugging harder, so we return a real
    403 and log the attempt.
    """
    invalid = set(allowed_roles) - set(ROLES)
    if invalid:
        raise ValueError(f"Unknown role(s) in role_required: {invalid}")

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            current_user = _authenticated_user()
            if current_user is None:
                return redirect(url_for("auth.login", next=request.path))

            if session.get("must_change_password") and request.endpoint not in (
                "auth.change_password_required", "auth.logout"
            ):
                return redirect(url_for("auth.change_password_required"))

            if _current_role() != SUPER_ADMIN and _current_role() not in allowed_roles:
                log_action(
                    user_id=session.get("user_id"),
                    action="ACCESS_DENIED",
                    details=f"role='{_current_role()}' attempted '{request.path}' "
                            f"(requires one of {allowed_roles})",
                )
                abort(403)

            return view_func(*args, **kwargs)

        return wrapped

    return decorator


def permission_required(permission_key):
    """Require a named fine-grained permission after authentication/RBAC.

    Super admins retain the universal bypass. Other roles must have an
    explicit grant in role_permissions
    this makes the Phase 6 permission
    matrix authoritative for the actions it names.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            current_user = _authenticated_user()
            if current_user is None:
                return redirect(url_for("auth.login", next=request.path))
            role = current_user[4]
            if role == SUPER_ADMIN:
                return view_func(*args, **kwargs)
            from models.permission_model import Permission
            if not Permission.has_permission(role, permission_key):
                log_action(
                    user_id=session.get("user_id"),
                    action="PERMISSION_DENIED",
                    details=f"role='{role}' attempted '{request.path}' (requires '{permission_key}')",
                )
                abort(403)
            return view_func(*args, **kwargs)
        return wrapped
    return decorator


def roles_at_least(minimum_role):
    """
    Hierarchical variant: grants access to `minimum_role` and anything
    more privileged than it (e.g. roles_at_least("manager") admits
    manager AND admin). Prefer role_required() for explicit allow-lists
    use this when a feature should simply scale with seniority.
    """
    minimum_index = ROLES.index(minimum_role)
    allowed = ROLES[minimum_index:]
    return role_required(*allowed)
