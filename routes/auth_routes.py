from flask import Blueprint, render_template, request, redirect, session, flash, url_for
import secrets
import time
from urllib.parse import urlsplit

from models.user_model import User
from core.security import (
    verify_password,
    is_account_locked,
    compute_lockout,
    is_password_expired,
    hash_password,
)
from core.audit import log_action
from core.extensions import limiter
from core.rbac import login_required

auth_bp = Blueprint('auth', __name__)
_DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(32))
_MFA_PENDING_TIMEOUT_SECONDS = 300

_ROLE_HOME = {
    # Enterprise roles must land on a valid dashboard after a
    # successful password check. In particular, super_admin is
    # authorized by core.rbac.role_required() but was previously
    # missing here, causing a successful login to fall back to /login.
    "super_admin": "/admin/dashboard",
    "admin": "/admin/dashboard",
    "manager": "/admin/dashboard",
    "cashier": "/admin/billing/pos",
    "inventory_manager": "/admin/inventory/dashboard",
    "hr": "/admin/hr/employees",
    "accountant": "/admin/billing/dashboard",
    "employee": "/employee/dashboard",
}


def _safe_next_url(next_url):
    """Accept only same-site absolute paths; reject scheme-relative URLs."""
    if (not next_url or not next_url.startswith("/") or next_url.startswith("//")
            or "\\" in next_url or any(ord(char) < 32 for char in next_url)):
        return None
    parsed = urlsplit(next_url)
    if parsed.scheme or parsed.netloc:
        return None
    return next_url


@auth_bp.route("/")
def home():
    return redirect("/login")


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")  # throttles credential-stuffing / brute-force attempts
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        remember = request.form.get("remember") in ("1", "true", "on", "yes")

        user = User.get_user_by_email(email)
        # user tuple columns (see models/user_model.py _COLUMNS):
        # 0 user_id, 1 full_name, 2 email, 3 password, 4 role, 5 status,
        # 6 failed_login_attempts, 7 locked_until, 8 last_login_at, ...

        if user is None:
            # Perform the same expensive password check as a known account so
            # response timing does not reveal whether an email is registered.
            verify_password(_DUMMY_PASSWORD_HASH, password or " ")
            log_action(None, "LOGIN_FAILED", "unknown account", request.remote_addr)
            flash("Invalid Email or Password")
            return render_template("login.html")

        user_id, full_name, _, stored_password, role, status = user[0:6]
        locked_until = user[7]
        password_changed_at = user[9]
        mfa_enabled = user[11]
        password_matches = verify_password(
            stored_password or _DUMMY_PASSWORD_HASH,
            password or " ",
        ) and bool(password)

        if status != "active":
            log_action(user_id, "LOGIN_BLOCKED", "account inactive", request.remote_addr)
            flash("Invalid Email or Password")
            return render_template("login.html")

        if is_account_locked(locked_until):
            log_action(user_id, "LOGIN_BLOCKED", "account locked", request.remote_addr)
            flash("Invalid Email or Password")
            return render_template("login.html")

        if password_matches:
            next_url = request.args.get("next")

            if mfa_enabled:
                # Password verified, but a second factor is required
                # before establishing a real session -- nothing in
                # `session` is set to an authenticated state yet.
                session.clear()
                session["mfa_pending_user_id"] = user_id
                session["mfa_pending_at"] = time.time()
                safe_next = _safe_next_url(next_url)
                if safe_next:
                    session["mfa_pending_next"] = safe_next
                session["mfa_remember"] = remember
                log_action(user_id, "LOGIN_MFA_REQUIRED", "", request.remote_addr)
                return redirect(url_for("auth.mfa_verify"))

            return _complete_login(user_id, full_name, role, password_changed_at, next_url, remember)

        # Wrong password: count it, and lock the account if the
        # threshold is reached.
        attempts = User.register_failed_login(user_id)
        lock_until = compute_lockout(attempts)
        if lock_until:
            User.lock_account(user_id, lock_until)
            log_action(user_id, "ACCOUNT_LOCKED",
                       f"after {attempts} failed attempts", request.remote_addr)
            flash("Invalid Email or Password")
        else:
            log_action(user_id, "LOGIN_FAILED", f"attempt {attempts}", request.remote_addr)
            flash("Invalid Email or Password")

    return render_template("login.html")


def _complete_login(user_id, full_name, role, password_changed_at, next_url=None, remember=False):
    """
    Finishes establishing an authenticated session -- shared by the
    normal (no-MFA) login path and the post-MFA-verification path, so
    session setup, the session-tracking row, and the audit log entry
    are only written in one place.
    """
    User.register_successful_login(user_id)

    session.clear()  # session fixation defense: never reuse a pre-login session id
    session["user_id"] = user_id
    session["name"] = full_name
    session["role"] = role
    from core.profile import get_profile_photo_filename, get_profile_photo_version
    session["profile_photo"] = get_profile_photo_filename(user_id) or ""
    session["profile_photo_version"] = get_profile_photo_version(user_id)

    from models.session_model import UserSession
    session_token = UserSession.create(user_id, request.remote_addr, request.user_agent.string)
    if not session_token:
        session.clear()
        flash("Unable to establish a secure session. Please try again.")
        return redirect(url_for("auth.login"))
    session["session_token"] = session_token
    # Respect the login form's Remember Me choice. A remembered session
    # is persistent; an ordinary login uses Flask's session cookie.
    session.permanent = bool(remember)

    if is_password_expired(password_changed_at):
        session["must_change_password"] = True
        log_action(user_id, "LOGIN_SUCCESS", "password change required", request.remote_addr)
        return redirect(url_for("auth.change_password_required"))

    log_action(user_id, "LOGIN_SUCCESS", "", request.remote_addr)

    safe_next = _safe_next_url(next_url)
    if safe_next:
        return redirect(safe_next)

    return redirect(_ROLE_HOME.get(role, "/login"))


@auth_bp.route("/login/mfa", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def mfa_verify():
    pending_user_id = session.get("mfa_pending_user_id")
    pending_at = session.get("mfa_pending_at")
    if not pending_user_id or not pending_at:
        return redirect(url_for("auth.login"))
    if time.time() - float(pending_at) > _MFA_PENDING_TIMEOUT_SECONDS:
        session.clear()
        flash("Sign-in attempt expired. Please sign in again.")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        from models.mfa_model import MFA

        code = request.form.get("code", "").strip()
        status = MFA.get_status(pending_user_id)

        if status and status[0] and MFA.verify_code(status[1], code):
            user = User.get_user_by_id(pending_user_id)
            if user is None or user[5] != "active" or is_account_locked(user[7]):
                session.clear()
                flash("Invalid Email or Password")
                return redirect(url_for("auth.login"))
            next_url = session.pop("mfa_pending_next", None)
            remember = bool(session.pop("mfa_remember", False))
            session.pop("mfa_pending_user_id", None)
            session.pop("mfa_pending_at", None)
            return _complete_login(user[0], user[1], user[4], user[9], next_url, remember)

        log_action(pending_user_id, "LOGIN_MFA_FAILED", "", request.remote_addr)
        flash("Invalid authentication code.")

    return render_template("mfa_verify.html")


@auth_bp.route("/account/change-password-required", methods=["GET", "POST"])
@login_required
def change_password_required():
    current_user = User.get_user_by_id(session.get("user_id"))
    if current_user is None or current_user[5] != "active":
        session.clear()
        return redirect(url_for("auth.login"))
    session["role"] = current_user[4]
    if not session.get("must_change_password"):
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        from core.security import hash_password, validate_password_strength

        new_password = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")

        if new_password != confirm:
            flash("Passwords do not match.")
            return render_template("change_password_required.html")

        violations = validate_password_strength(new_password)
        if violations:
            for v in violations:
                flash(v)
            return render_template("change_password_required.html")

        User.update_password(session["user_id"], hash_password(new_password))
        log_action(session["user_id"], "PASSWORD_CHANGED", "expired password forced change",
                   request.remote_addr)
        session.clear()
        flash("Password updated. You're all set.")
        return redirect(url_for("auth.login"))

    return render_template("change_password_required.html")


@auth_bp.route("/logout", methods=["POST"])
def logout():
    log_action(session.get("user_id"), "LOGOUT", "", request.remote_addr)
    token = session.get("session_token")
    session_revoked = True
    if token:
        from models.session_model import UserSession
        session_revoked = UserSession.delete_by_token(token)
    session.clear()
    if not session_revoked:
        flash("You were signed out in this browser, but the server could not revoke the session record. Please retry after reconnecting.", "error")
    return redirect("/login")



@auth_bp.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.get_user_by_email(email)

        # Same response regardless of whether the email exists --
        # otherwise this endpoint becomes a user-enumeration oracle.
        log_action(user[0] if user else None, "PASSWORD_RESET_REQUESTED",
                   "forgot-password form submitted", request.remote_addr)
        flash("If that email is registered, an administrator will be in touch "
              "to help you reset your password.")

    return render_template("forgot_password.html")
