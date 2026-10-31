"""Opt-in tests against a disposable, real MySQL database.

Set RUN_DB_INTEGRATION=1 and MYSQL_DB to a database ending in _test.
These tests create disposable employee/product/sale records through the
application and must never be pointed at a production database.
"""

import os
import uuid
from datetime import date, timedelta

import pytest


_RUN_DATABASE_TESTS = os.environ.get("RUN_DB_INTEGRATION") == "1"
_DATABASE_NAME = os.environ.get("MYSQL_DB", "")

if _RUN_DATABASE_TESTS and not _DATABASE_NAME.endswith("_test"):
    raise RuntimeError("Database integration tests require MYSQL_DB to end in '_test'.")

pytestmark = pytest.mark.skipif(
    not _RUN_DATABASE_TESTS,
    reason="Set RUN_DB_INTEGRATION=1 to use the explicitly named disposable MySQL database.",
)


def test_employee_provisioning_login_and_dashboard_chart():
    from app import create_app
    from core.security import hash_password
    from database.db import get_db_cursor
    from models.user_model import User

    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    with app.app_context():
        with get_db_cursor(commit=False) as cursor:
            cursor.execute("SELECT user_id FROM users WHERE email=%s", ("admin@example.com",))
            admin_row = cursor.fetchone()
        assert admin_row is not None, "Fresh schema must include the administrator seed account."
        admin_user_id = admin_row[0]
        admin_password = f"AdminAudit!{uuid.uuid4().hex[:12]}"
        User.update_password(admin_user_id, hash_password(admin_password))

    suffix = uuid.uuid4().hex[:10]
    employee_email = f"employee-{suffix}@example.test"
    employee_password = f"EmployeeAudit!{suffix}"
    employee_name = f"Audit Employee {suffix}"
    admin_client = app.test_client()

    login_response = admin_client.post(
        "/login",
        data={"email": "admin@example.com", "password": admin_password},
        follow_redirects=False,
    )
    assert login_response.status_code == 302
    assert login_response.headers["Location"].endswith("/admin/dashboard")

    # Pick a date before the earliest completed sale so this check remains
    # repeatable on a disposable database that already has test transactions.
    with app.app_context():
        with get_db_cursor(commit=False) as cursor:
            cursor.execute(
                "SELECT DATE_SUB(MIN(sale_date), INTERVAL 1 DAY) "
                "FROM sales WHERE status='completed'"
            )
            empty_date_row = cursor.fetchone()
    empty_date = empty_date_row[0] if empty_date_row and empty_date_row[0] else date(1900, 1, 1)
    empty_date = empty_date.date() if hasattr(empty_date, "date") else empty_date
    empty_chart = admin_client.get(
        "/admin/dashboard/chart-data?period=custom"
        f"&start={empty_date.isoformat()}&end={empty_date.isoformat()}"
    )
    assert empty_chart.status_code == 200
    empty_data = empty_chart.get_json()
    assert empty_data["transactions"] == 0
    assert len(empty_data["labels"]) == 1
    assert empty_data["values"] == [0.0]

    baseline_chart = admin_client.get("/admin/dashboard/chart-data?period=this_year")
    assert baseline_chart.status_code == 200
    baseline_data = baseline_chart.get_json()

    create_response = admin_client.post(
        "/admin/add-employee",
        data={
            "name": employee_name,
            "email": employee_email,
            "phone": "+1 555 010 1234",
            "designation": "Audit Associate",
            "salary": "42000.50",
            "password": employee_password,
            "date_of_birth": "1995-04-12",
        },
        follow_redirects=False,
    )
    assert create_response.status_code == 302
    assert create_response.headers["Location"].endswith("/admin/hr/employees")
    directory_response = admin_client.get(create_response.headers["Location"])
    assert directory_response.status_code == 200
    assert employee_name.encode() in directory_response.data
    assert b"Audit Associate" in directory_response.data

    duplicate_response = admin_client.post(
        "/admin/add-employee",
        data={
            "name": employee_name,
            "email": employee_email,
            "phone": "+1 555 010 1234",
            "designation": "Audit Associate",
            "salary": "42000.50",
            "password": employee_password,
        },
    )
    assert duplicate_response.status_code == 200
    assert b"already exists" in duplicate_response.data.lower()

    employee_client = app.test_client()
    employee_login = employee_client.post(
        "/login",
        data={"email": employee_email, "password": employee_password},
        follow_redirects=False,
    )
    assert employee_login.status_code == 302
    assert employee_login.headers["Location"].endswith("/employee/dashboard")
    employee_dashboard = employee_client.get(employee_login.headers["Location"])
    assert employee_dashboard.status_code == 200
    assert employee_name.encode() in employee_dashboard.data

    employee_logout = employee_client.post("/logout")
    assert employee_logout.status_code == 302
    protected_after_logout = employee_client.get("/employee/dashboard")
    assert protected_after_logout.status_code == 302
    assert "/login" in protected_after_logout.headers["Location"]

    with app.app_context():
        with get_db_cursor() as cursor:
            cursor.execute(
                "INSERT INTO products "
                "(category_id, product_name, sku, purchase_price, selling_price, "
                "stock_quantity, is_active, gst_rate) "
                "SELECT category_id, %s, %s, 10.00, 20.00, 5, TRUE, 18.00 "
                "FROM categories ORDER BY category_id LIMIT 1",
                (f"Audit Product {suffix}", f"AUDIT-{suffix}"),
            )
            product_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO stock_movements "
                "(product_id, movement_type, quantity, reason, reference_type, reference_id, performed_by) "
                "VALUES (%s, 'in', 5, 'Integration test stock', 'test_setup', %s, %s)",
                (product_id, product_id, admin_user_id),
            )
        assert product_id

    sale_response = admin_client.post(
        "/admin/billing/checkout",
        json={
            "items": [{"product_id": product_id, "quantity": 1}],
            "payment_methods": [{"method": "cash", "amount": 23.60}],
            "customer_state": "Same State",
        },
    )
    assert sale_response.status_code == 200
    sale_data = sale_response.get_json()
    assert sale_data["ok"] is True, sale_data.get("message")

    populated_chart = admin_client.get("/admin/dashboard/chart-data?period=this_year")
    assert populated_chart.status_code == 200
    populated_data = populated_chart.get_json()
    assert populated_data["transactions"] == baseline_data["transactions"] + 1
    assert len(populated_data["labels"]) == 12
    assert sum(populated_data["values"]) == pytest.approx(
        sum(baseline_data["values"]) + 23.60
    )

    dashboard_response = admin_client.get("/admin/dashboard")
    assert dashboard_response.status_code == 200
    assert b"salesChart" in dashboard_response.data
    assert b"chartLoading" in dashboard_response.data
    assert b"chartEmpty" in dashboard_response.data
    assert b"chartError" in dashboard_response.data
