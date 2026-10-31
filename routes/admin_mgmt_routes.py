from flask import Blueprint, render_template, request, redirect, session, flash

from models.user_model import User
from models.session_model import UserSession
from models.permission_model import Permission
from database.db import mysql
from core.rbac import role_required, permission_required
from core.security import hash_password, validate_password_strength
from core.audit import log_action

admin_mgmt_bp = Blueprint("admin_mgmt", __name__)

ALL_ROLES = ("super_admin", "admin", "manager", "cashier", "inventory_manager", "hr", "accountant", "employee")


# ---------------------------------------------------------------
# Password reset (admin-initiated)
# ---------------------------------------------------------------
@admin_mgmt_bp.route("/admin/users/<int:user_id>/reset-password", methods=["GET", "POST"])
@role_required("admin", "super_admin")
@permission_required("manage_users")
def reset_password(user_id):
    user = User.get_user_by_id(user_id)
    if user is None:
        flash("User not found.")
        return redirect("/admin/users")
    if session.get("role") == "admin" and user[4] == "super_admin":
        flash("Administrators cannot reset a Super Admin password.")
        return redirect("/admin/users")

    if request.method == "POST":
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if new_password != confirm_password:
            flash("Passwords do not match.")
            return render_template("admin/administration/reset_password.html", user=user)

        violations = validate_password_strength(new_password)
        if violations:
            for v in violations:
                flash(v)
            return render_template("admin/administration/reset_password.html", user=user)

        resetting_current_user = user_id == session.get("user_id")
        User.update_password(user_id, hash_password(new_password))
        log_action(session.get("user_id"), "ADMIN_PASSWORD_RESET", f"target_user_id={user_id}")
        if resetting_current_user:
            session.clear()
            flash("Password reset successfully. Sign in again with the new password.", "success")
            return redirect("/login")
        flash("Password reset successfully.")
        return redirect("/admin/users")

    return render_template("admin/administration/reset_password.html", user=user)


# ---------------------------------------------------------------
# Activity / audit logs
# ---------------------------------------------------------------
@admin_mgmt_bp.route("/admin/activity-logs")
@role_required("admin", "super_admin", "hr", "accountant")
@permission_required("view_audit_logs")
def activity_logs():
    from core.pagination import get_pagination_params, build_page_info

    action_filter = request.args.get("action")
    page, size, offset = get_pagination_params()

    cur = mysql.connection.cursor()

    count_sql = "SELECT COUNT(*) FROM audit_logs a WHERE 1=1"
    sql = """
        SELECT a.audit_id, u.full_name, a.action, a.details, a.ip_address, a.created_at
        FROM audit_logs a LEFT JOIN users u ON a.user_id = u.user_id
        WHERE 1=1
    """
    params = []
    if action_filter:
        count_sql += " AND a.action=%s"
        sql += " AND a.action=%s"
        params.append(action_filter)

    cur.execute(count_sql, tuple(params))
    total_count = cur.fetchone()[0]

    sql += " ORDER BY a.created_at DESC LIMIT %s OFFSET %s"
    cur.execute(sql, tuple(params) + (size, offset))
    logs = cur.fetchall()
    cur.close()

    page_info = build_page_info(page, size, total_count)
    return render_template("admin/administration/activity_logs.html", logs=logs,
                           action_filter=action_filter, page_info=page_info)


@admin_mgmt_bp.route("/admin/login-history")
@role_required("admin", "super_admin", "hr")
@permission_required("view_audit_logs")
def login_history():
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM v_login_history LIMIT 500")
    data = cur.fetchall()
    cur.close()
    return render_template("admin/administration/login_history.html", history=data)


# ---------------------------------------------------------------
# Session management
# ---------------------------------------------------------------
@admin_mgmt_bp.route("/admin/sessions")
@role_required("admin", "super_admin")
def sessions():
    return render_template("admin/administration/sessions.html", sessions=UserSession.get_all())


@admin_mgmt_bp.route("/admin/sessions/<int:session_id>/revoke", methods=["POST"])
@role_required("admin", "super_admin")
def revoke_session(session_id):
    UserSession.revoke(session_id)
    log_action(session.get("user_id"), "SESSION_REVOKED", f"session_id={session_id}")
    return redirect("/admin/sessions")


# ---------------------------------------------------------------
# Permission management
# ---------------------------------------------------------------
@admin_mgmt_bp.route("/admin/permissions")
@role_required("admin", "super_admin")
def permissions():
    matrix = Permission.get_matrix()
    all_permissions = Permission.get_all_permissions()
    return render_template("admin/administration/permissions.html",
                           matrix=matrix, permissions=all_permissions, roles=ALL_ROLES)


@admin_mgmt_bp.route("/admin/permissions/toggle", methods=["POST"])
@role_required("admin", "super_admin")
@permission_required("manage_permissions")
def toggle_permission():
    role = request.form["role"]
    permission_key = request.form["permission_key"]
    granted = request.form.get("granted") == "1"
    Permission.set_permission(role, permission_key, granted)
    log_action(session.get("user_id"), "PERMISSION_CHANGED",
               f"role={role} permission={permission_key} granted={granted}")
    return redirect("/admin/permissions")
