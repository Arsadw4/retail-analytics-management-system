"""Real-MySQL regression checks for catalog, customer, stock and purchasing flows."""

import os
import uuid
from datetime import date, timedelta

import pytest


_RUN_DATABASE_TESTS = os.environ.get("RUN_DB_INTEGRATION") == "1"
_DATABASE_NAME = os.environ.get("MYSQL_DB", "")
if _RUN_DATABASE_TESTS and not _DATABASE_NAME.endswith("_test"):
    raise RuntimeError("Business workflow tests require MYSQL_DB to end in '_test'.")

pytestmark = pytest.mark.skipif(
    not _RUN_DATABASE_TESTS,
    reason="Set RUN_DB_INTEGRATION=1 and use a disposable MYSQL_DB ending in '_test'.",
)
_ADMIN_PASSWORD = f"BusinessAudit!{uuid.uuid4().hex[:16]}"


@pytest.fixture(scope="module")
def app():
    from app import create_app
    from core.security import hash_password
    from models.user_model import User

    test_app = create_app()
    test_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with test_app.app_context():
        admin = User.get_user_by_email("admin@example.com")
        if admin is None:
            raise AssertionError("The disposable schema is missing its seeded administrator.")
        User.update_password(admin[0], hash_password(_ADMIN_PASSWORD))
    return test_app


def _admin_client(app):
    client = app.test_client()
    response = client.post(
        "/login",
        data={"email": "admin@example.com", "password": _ADMIN_PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/dashboard")
    return client


def _category_id(app):
    from database.db import get_db_cursor

    with app.app_context(), get_db_cursor(commit=False) as cursor:
        cursor.execute("SELECT category_id FROM categories ORDER BY category_id LIMIT 1")
        row = cursor.fetchone()
    assert row is not None
    return row[0]


def _product_form(category_id, name, sku, stock="0"):
    return {
        "category_id": str(category_id),
        "product_name": name,
        "purchase_price": "12.50",
        "selling_price": "20.00",
        "stock_quantity": stock,
        "sku": sku,
    }


def _query_one(app, query, params=()):
    from database.db import get_db_cursor

    with app.app_context(), get_db_cursor(commit=False) as cursor:
        cursor.execute(query, params)
        return cursor.fetchone()


def test_product_crud_stock_movements_and_duplicate_sku_rollback(app):
    admin = _admin_client(app)
    category_id = _category_id(app)
    suffix = uuid.uuid4().hex[:12]
    product_name = f"Workflow Product {suffix}"
    sku = f"WF-{suffix}"

    missing = admin.post("/admin/add-product", data={"product_name": ""})
    assert missing.status_code == 200
    assert b"category" in missing.data.lower()

    created = admin.post(
        "/admin/add-product",
        data=_product_form(category_id, product_name, sku),
        follow_redirects=False,
    )
    assert created.status_code == 302
    product = _query_one(
        app,
        "SELECT product_id, sku, barcode, stock_quantity FROM products WHERE sku=%s",
        (sku,),
    )
    assert product is not None
    product_id = product[0]
    assert product[1] == sku and product[2] == f"890{product_id:09d}"
    assert admin.get(f"/admin/products/{product_id}").status_code == 200

    admin.post(
        "/admin/inventory/stock-in",
        data={"product_id": str(product_id), "quantity": "7", "reason": "QA receipt"},
    )
    assert _query_one(app, "SELECT stock_quantity FROM products WHERE product_id=%s", (product_id,))[0] == 7

    admin.post(
        "/admin/inventory/stock-out",
        data={"product_id": str(product_id), "quantity": "2", "reason": "QA issue"},
    )
    assert _query_one(app, "SELECT stock_quantity FROM products WHERE product_id=%s", (product_id,))[0] == 5

    admin.post(
        "/admin/inventory/stock-out",
        data={"product_id": str(product_id), "quantity": "99", "reason": "Over issue"},
    )
    assert _query_one(app, "SELECT stock_quantity FROM products WHERE product_id=%s", (product_id,))[0] == 5

    edit_data = _product_form(category_id, f"Edited {product_name}", sku, stock="5")
    updated = admin.post(f"/admin/edit-product/{product_id}", data=edit_data)
    assert updated.status_code == 302
    assert _query_one(app, "SELECT product_name FROM products WHERE product_id=%s", (product_id,))[0] == edit_data["product_name"]
    assert _query_one(
        app,
        "SELECT COUNT(*) FROM stock_movements WHERE product_id=%s AND movement_type IN ('in','out')",
        (product_id,),
    )[0] == 2

    duplicate_name = f"Duplicate SKU {suffix}"
    duplicate = admin.post(
        "/admin/add-product",
        data=_product_form(category_id, duplicate_name, sku),
        follow_redirects=False,
    )
    assert duplicate.status_code == 302
    assert _query_one(app, "SELECT COUNT(*) FROM products WHERE product_name=%s", (duplicate_name,))[0] == 0

    disposable_name = f"Disposable Product {suffix}"
    admin.post(
        "/admin/add-product",
        data=_product_form(category_id, disposable_name, f"DEL-{suffix}"),
    )
    disposable_id = _query_one(app, "SELECT product_id FROM products WHERE sku=%s", (f"DEL-{suffix}",))[0]
    deleted = admin.post(f"/admin/delete-product/{disposable_id}")
    assert deleted.status_code == 302
    assert _query_one(app, "SELECT COUNT(*) FROM products WHERE product_id=%s", (disposable_id,))[0] == 0


def test_customer_create_edit_delete_and_missing_field_handling(app):
    admin = _admin_client(app)
    empty = admin.post("/admin/add-customer", data={}, follow_redirects=False)
    assert empty.status_code == 302
    assert empty.headers["Location"].endswith("/admin/add-customer")

    suffix = uuid.uuid4().hex[:12]
    name = f"Workflow Customer {suffix}"
    created = admin.post(
        "/admin/add-customer",
        data={"name": name, "phone": "+1 555 010 2030", "email": f"{suffix}@example.test", "address": "QA"},
    )
    assert created.status_code == 302
    customer = _query_one(app, "SELECT customer_id FROM customers WHERE customer_name=%s", (name,))
    assert customer is not None
    customer_id = customer[0]
    assert admin.get(f"/admin/edit-customer/{customer_id}").status_code == 200

    updated_name = f"Edited {name}"
    updated = admin.post(
        f"/admin/edit-customer/{customer_id}",
        data={"name": updated_name, "phone": "+1 555 010 2031", "email": "", "address": "Updated"},
    )
    assert updated.status_code == 302
    assert _query_one(app, "SELECT customer_name, phone FROM customers WHERE customer_id=%s", (customer_id,)) == (
        updated_name, "+1 555 010 2031"
    )

    assert admin.get("/admin/edit-customer/999999999").status_code == 302
    deleted = admin.post(f"/employee/delete-customer/{customer_id}")
    assert deleted.status_code == 302
    assert _query_one(app, "SELECT COUNT(*) FROM customers WHERE customer_id=%s", (customer_id,))[0] == 0


def test_supplier_purchase_order_grn_and_report_exports(app):
    admin = _admin_client(app)
    category_id = _category_id(app)
    suffix = uuid.uuid4().hex[:12]
    product_sku = f"PO-{suffix}"
    product_name = f"Purchase Workflow Product {suffix}"
    admin.post("/admin/add-product", data=_product_form(category_id, product_name, product_sku))
    product_id = _query_one(app, "SELECT product_id FROM products WHERE sku=%s", (product_sku,))[0]

    supplier_name = f"Workflow Supplier {suffix}"
    admin.post(
        "/admin/add-supplier",
        data={"supplier_name": supplier_name, "contact_person": "QA", "phone": "+1 555 010 2040",
              "email": f"supplier-{suffix}@example.test", "address": "QA", "gst_number": ""},
    )
    supplier_id = _query_one(app, "SELECT supplier_id FROM suppliers WHERE supplier_name=%s", (supplier_name,))[0]

    po_response = admin.post(
        "/admin/purchase-orders/add",
        data={"supplier_id": str(supplier_id), "product_id[]": str(product_id),
              "quantity[]": "4", "unit_cost[]": "12.50", "notes": "QA purchase"},
        follow_redirects=False,
    )
    assert po_response.status_code == 302
    po_id = int(po_response.headers["Location"].rsplit("/", 1)[1])
    po_item_id = _query_one(app, "SELECT po_item_id FROM purchase_order_items WHERE po_id=%s", (po_id,))[0]
    assert admin.get(f"/admin/purchase-orders/{po_id}").status_code == 200

    grn_response = admin.post(
        "/admin/grn/add",
        data={"supplier_id": str(supplier_id), "po_id": str(po_id), "received_date": date.today().isoformat(),
              "po_item_id[]": str(po_item_id), "product_id[]": str(product_id),
              "quantity[]": "4", "unit_cost[]": "12.50", "notes": "QA receipt"},
        follow_redirects=False,
    )
    assert grn_response.status_code == 302
    grn_id = int(grn_response.headers["Location"].rsplit("/", 1)[1])
    assert admin.get(f"/admin/grn/{grn_id}").status_code == 200
    assert _query_one(app, "SELECT status FROM purchase_orders WHERE po_id=%s", (po_id,))[0] == "received"
    assert _query_one(app, "SELECT stock_quantity FROM products WHERE product_id=%s", (product_id,))[0] == 4
    assert _query_one(app, "SELECT outstanding_balance FROM suppliers WHERE supplier_id=%s", (supplier_id,))[0] == 50.0
    assert _query_one(app, "SELECT COUNT(*) FROM supplier_ledger WHERE supplier_id=%s", (supplier_id,))[0] == 1

    rejected = admin.post(
        "/admin/grn/add",
        data={"supplier_id": str(supplier_id), "po_id": str(po_id), "received_date": date.today().isoformat(),
              "po_item_id[]": str(po_item_id), "product_id[]": str(product_id),
              "quantity[]": "1", "unit_cost[]": "12.50"},
        follow_redirects=False,
    )
    assert rejected.status_code == 302
    assert _query_one(app, "SELECT stock_quantity FROM products WHERE product_id=%s", (product_id,))[0] == 4

    for path in (
        "/admin/customers/export/csv", "/admin/customers/export/excel", "/admin/customers/export/pdf",
        "/admin/suppliers/export/csv", "/admin/suppliers/export/excel", "/admin/suppliers/export/pdf",
        "/admin/sales-report/export/csv", "/admin/profit-report/export/csv", "/admin/stock-report/export/csv",
    ):
        response = admin.get(path)
        assert response.status_code == 200, (path, response.status_code, response.data[:200])
        assert response.headers.get("Content-Disposition", "").startswith("attachment;")


def test_hr_attendance_leave_approval_and_payroll_workflow(app):
    admin = _admin_client(app)
    suffix = uuid.uuid4().hex[:12]
    email = f"hr-workflow-{suffix}@example.test"
    employee_password = f"HRWorkflow!{suffix}9"
    created = admin.post(
        "/admin/add-employee",
        data={
            "name": f"HR Workflow {suffix}",
            "email": email,
            "phone": "+1 555 010 2050",
            "designation": "HR Workflow QA",
            "salary": "52000.00",
            "password": employee_password,
        },
    )
    assert created.status_code == 302
    employee_id = _query_one(app, "SELECT employee_id FROM employees WHERE email=%s", (email,))[0]

    today = date.today()
    attendance_response = admin.post(
        "/admin/hr/attendance",
        data={
            "date": today.isoformat(),
            f"status_{employee_id}": "present",
            f"checkin_{employee_id}": "09:00",
            f"checkout_{employee_id}": "17:00",
        },
    )
    assert attendance_response.status_code == 302
    assert _query_one(
        app,
        "SELECT status FROM attendance WHERE employee_id=%s AND attendance_date=%s",
        (employee_id, today.isoformat()),
    )[0] == "present"

    leave_day = today + timedelta(days=1)
    leave_response = admin.post(
        "/admin/hr/leaves/request",
        data={
            "employee_id": str(employee_id),
            "leave_type": "casual",
            "start_date": leave_day.isoformat(),
            "end_date": leave_day.isoformat(),
            "reason": "QA workflow",
        },
    )
    assert leave_response.status_code == 302
    leave_id = _query_one(
        app,
        "SELECT leave_id FROM leave_requests WHERE employee_id=%s ORDER BY leave_id DESC LIMIT 1",
        (employee_id,),
    )[0]
    approved = admin.post(f"/admin/hr/leaves/{leave_id}/decide", data={"decision": "approved"})
    assert approved.status_code == 302
    assert _query_one(app, "SELECT status FROM leave_requests WHERE leave_id=%s", (leave_id,))[0] == "approved"
    assert _query_one(
        app,
        "SELECT status FROM attendance WHERE employee_id=%s AND attendance_date=%s",
        (employee_id, leave_day.isoformat()),
    )[0] == "leave"

    month = today.strftime("%Y-%m")
    payroll = admin.post(
        f"/admin/hr/salary?month={month}",
        data={"employee_id": str(employee_id), "basic_salary": "4000", "allowances": "200", "deductions": "50"},
    )
    assert payroll.status_code == 302
    salary_id = _query_one(
        app,
        "SELECT salary_id FROM salary_records WHERE employee_id=%s AND salary_month=%s",
        (employee_id, month),
    )[0]
    marked_paid = admin.post(f"/admin/hr/salary/{salary_id}/mark-paid")
    assert marked_paid.status_code == 302
    assert _query_one(
        app,
        "SELECT payment_status, net_salary FROM salary_records WHERE salary_id=%s",
        (salary_id,),
    ) == ("paid", 4150.0)
