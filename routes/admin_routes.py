import logging

from flask import Blueprint, jsonify, render_template, request, redirect, session, flash, url_for

from models.user_model import User
from models.product_model import Product
from models.customer_model import Customer
from models.sales_model import Sale
from models.company_settings_model import CompanySettings
from models.inventory_model import Inventory
from core.rbac import role_required, permission_required
from core.security import hash_password, validate_password_strength
from core.employee_validation import is_valid_email
from core.audit import log_action
from core.dashboard_period import build_dashboard_chart_series, resolve_dashboard_period
from database.errors import DatabaseError

admin_bp = Blueprint('admin', __name__)
logger = logging.getLogger(__name__)


@admin_bp.route('/admin/dashboard')
@role_required("admin", "manager", "super_admin")
def admin_dashboard():
    """Render the enterprise dashboard from live database projections."""
    period = request.args.get('period', 'this_year').strip().lower()
    try:
        period, start, end, chart_granularity, period_label = resolve_dashboard_period(
            period,
            request.args.get('start', ''),
            request.args.get('end', ''),
        )
    except ValueError:
        flash('Please select a valid custom date range.', 'error')
        return redirect('/admin/dashboard?period=this_year')

    metrics = Sale.dashboard_metrics(start, end)

    return render_template(
        "admin/dashboard.html",
        total_users=User.count_users(),
        total_products=Product.count_products(),
        total_customers=Customer.count_customers(),
        total_sales=metrics['sales'],
        total_profit=metrics['profit'],
        total_loss=metrics['loss'],
        total_transactions=metrics['transactions'],
        chart_url=url_for('admin.admin_dashboard_chart_data'),
        period=period,
        period_label=period_label,
        custom_start=start.isoformat() if period == 'custom' else '',
        custom_end=end.isoformat() if period == 'custom' else '',
        recent_sales=Sale.recent_sales_for_range(start, end, 5),
        low_stock_products=Product.dashboard_low_stock(5),
        top_products=Sale.top_products_for_range(start, end, 5),
        new_customers=Customer.dashboard_recent(5, start, end),
        low_stock_count=Inventory.low_stock_count(),
    )


@admin_bp.route('/admin/dashboard/chart-data')
@role_required("admin", "manager", "super_admin")
def admin_dashboard_chart_data():
    """Return chart data as JSON so the UI can show loading and error states."""
    period = request.args.get('period', 'this_year').strip().lower()
    try:
        period, start, end, granularity, _ = resolve_dashboard_period(
            period,
            request.args.get('start', ''),
            request.args.get('end', ''),
        )
    except ValueError:
        return jsonify(error="Please select a valid custom date range."), 400

    try:
        metrics = Sale.dashboard_metrics(start, end)
        rows = Sale.dashboard_series(start, end, granularity)
        labels, values = build_dashboard_chart_series(rows, start, end, granularity, period)
    except Exception:
        logger.exception("Dashboard chart data query failed for period=%s", period)
        return jsonify(error="Sales chart data is temporarily unavailable. Please retry."), 503

    return jsonify(
        labels=labels,
        values=values,
        transactions=metrics['transactions'],
    )


@admin_bp.route('/admin/users')
@role_required("admin")  # user administration is admin-only, not manager
@permission_required("manage_users")
def admin_users():
    users = User.get_all_users()
    return render_template('admin/users/users.html', users=users)


@admin_bp.route('/admin/add-user', methods=['GET', 'POST'])
@role_required("admin")
@permission_required("manage_users")
def add_user():
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        role = request.form.get('role', '')

        # SECURITY FIX: the original handler passed the plaintext
        # password straight into the INSERT statement. Every
        # admin-created account was therefore stored with an
        # unhashed password. All entry points must hash before
        # persisting -- this is exactly why core/security.py exists,
        # so the rule can't be silently skipped by one call site.
        violations = validate_password_strength(password)
        if violations:
            for v in violations:
                flash(v)
            return render_template('admin/users/add_user.html')

        if not full_name or len(full_name) > 100 or not is_valid_email(email):
            flash("Enter a valid name and email address.", "error")
            return render_template('admin/users/add_user.html')

        allowed_roles = {"admin", "manager", "cashier", "inventory_manager", "hr", "accountant", "employee"}
        if session.get("role") == "super_admin":
            allowed_roles.add("super_admin")
        if role not in allowed_roles:
            flash("Invalid role selected.")
            return render_template('admin/users/add_user.html')

        try:
            user_id = User.create_user(full_name, email, hash_password(password), role)
        except DatabaseError as exc:
            flash(str(exc), "error")
            return render_template('admin/users/add_user.html')

        log_action(session.get("user_id"), "USER_CREATED",
                   f"created user_id={user_id} email={email} role={role}")

        flash("User created successfully.")
        return redirect('/admin/users')

    return render_template('admin/users/add_user.html')


@admin_bp.route('/admin/delete-user/<int:user_id>', methods=['POST'])
@role_required("admin")
@permission_required("manage_users")
def delete_user(user_id):
    target = User.get_user_by_id(user_id)
    if target is None:
        flash("User not found.")
        return redirect('/admin/users')
    if user_id == session.get("user_id"):
        flash("You cannot delete your own account while logged in.")
        return redirect('/admin/users')
    if session.get("role") == "admin" and target[4] == "super_admin":
        flash("Administrators cannot delete a Super Admin account.")
        return redirect('/admin/users')

    User.delete_user(user_id)
    log_action(session.get("user_id"), "USER_DELETED", f"deleted user_id={user_id}")

    return redirect('/admin/users')


@admin_bp.route('/admin/edit-user/<int:user_id>', methods=['GET', 'POST'])
@role_required("admin")
@permission_required("manage_users")
def edit_user(user_id):
    user = User.get_user_by_id(user_id)
    if user is None:
        flash("User not found.")
        return redirect('/admin/users')
    if session.get("role") == "admin" and user[4] == "super_admin":
        flash("Administrators cannot modify a Super Admin account.")
        return redirect('/admin/users')

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        role = request.form.get('role', '')
        status = request.form.get('status', user[5])

        if not full_name or len(full_name) > 100 or not is_valid_email(email):
            flash("Enter a valid name and email address.", "error")
            return render_template('admin/users/edit_user.html', user=user)

        allowed_roles = {"admin", "manager", "cashier", "inventory_manager", "hr", "accountant", "employee"}
        if session.get("role") == "super_admin":
            allowed_roles.add("super_admin")
        if role not in allowed_roles:
            flash("Invalid role selected.")
            return render_template('admin/users/edit_user.html', user=user)
        if status not in ("active", "inactive"):
            flash("Invalid account status selected.", "error")
            return render_template('admin/users/edit_user.html', user=user)
        if user_id == session.get("user_id") and status == "inactive":
            flash("You cannot deactivate your own account while signed in.", "error")
            return render_template('admin/users/edit_user.html', user=user)

        try:
            User.update_user(user_id, full_name, email, role, status)
        except DatabaseError as exc:
            flash(str(exc), "error")
            return redirect(f'/admin/edit-user/{user_id}')
        log_action(session.get("user_id"), "USER_UPDATED", f"user_id={user_id} new_role={role}")

        return redirect('/admin/users')

    return render_template('admin/users/edit_user.html', user=user)


@admin_bp.route('/admin/settings', methods=['GET', 'POST'])
@role_required("admin", "super_admin")
def admin_settings():
    """Manage the single company profile used by invoices and billing."""
    company = CompanySettings.get()

    if request.method == 'POST':
        company_name = request.form.get('company_name', '').strip()
        gst_number = request.form.get('gst_number', '').strip()
        address = request.form.get('address', '').strip()
        state = request.form.get('state', '').strip()
        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip()

        if not company_name:
            flash("Company name is required.")
            return render_template('admin/settings.html', company=company)
        if not state:
            flash("State is required.")
            return render_template('admin/settings.html', company=company)
        if email and ('@' not in email or '.' not in email.rsplit('@', 1)[-1]):
            flash("Please enter a valid business email address.")
            return render_template('admin/settings.html', company=company)

        CompanySettings.update(company_name, gst_number or None, address or None,
                               state, phone or None, email or None)
        log_action(session.get("user_id"), "COMPANY_SETTINGS_UPDATED",
                   "updated company profile", request.remote_addr)
        flash("Business settings saved successfully.")
        return redirect('/admin/settings')

    return render_template('admin/settings.html', company=company)
