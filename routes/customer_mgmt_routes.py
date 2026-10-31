from flask import Blueprint, render_template, request, redirect, session, flash

from models.customer_model import Customer
from models.customer_ledger_model import CustomerLedger
from models.billing_model import Billing
from database.db import mysql
from core.rbac import role_required
from core.audit import log_action
from core.export_utils import export_csv, export_excel, export_pdf

customer_mgmt_bp = Blueprint("customer_mgmt", __name__)


@customer_mgmt_bp.route("/admin/customers/search")
@role_required("admin", "manager", "employee")
def customers_search():
    query = request.args.get("q")
    membership = request.args.get("membership") or None
    results = Customer.search(query=query, membership_level=membership)
    return render_template("admin/customers/search_customers.html",
                           results=results, query=query, membership=membership)


@customer_mgmt_bp.route("/admin/customers/<int:customer_id>/profile")
@role_required("admin", "manager", "employee")
def customer_profile(customer_id):
    customer = Customer.get_customer(customer_id)
    if customer is None:
        flash("Customer not found.")
        return redirect("/admin/customers/search")

    analytics = Customer.get_analytics(customer_id)
    ledger = CustomerLedger.get_ledger(customer_id)
    purchase_history = Billing.get_customer_billing_history(customer_id)

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT r.return_id, s.invoice_number, p.product_name, r.quantity, r.refund_amount, r.created_at
        FROM sales_returns r
        JOIN sales s ON r.sale_id = s.sale_id
        JOIN products p ON r.product_id = p.product_id
        WHERE s.customer_id=%s
        ORDER BY r.created_at DESC
    """, (customer_id,))
    returns = cur.fetchall()
    cur.close()

    return render_template(
        "admin/customers/profile.html",
        customer=customer, analytics=analytics, ledger=ledger,
        purchase_history=purchase_history, returns=returns
    )


@customer_mgmt_bp.route("/admin/customers/<int:customer_id>/wallet-topup", methods=["POST"])
@role_required("admin", "manager")
def wallet_topup(customer_id):
    amount = float(request.form.get("amount", 0))
    result = CustomerLedger.wallet_topup(customer_id, amount, session.get("user_id"))
    flash(result["message"])
    if result["ok"]:
        log_action(session.get("user_id"), "WALLET_TOPUP", f"customer_id={customer_id} amount={amount}")
    return redirect(f"/admin/customers/{customer_id}/profile")


@customer_mgmt_bp.route("/admin/customers/<int:customer_id>/redeem-points", methods=["POST"])
@role_required("admin", "manager", "employee")
def redeem_points(customer_id):
    points = int(request.form.get("points", 0))
    result = CustomerLedger.redeem_points(customer_id, points, session.get("user_id"))
    flash(result["message"])
    if result["ok"]:
        log_action(session.get("user_id"), "LOYALTY_REDEEMED", f"customer_id={customer_id} points={points}")
    return redirect(f"/admin/customers/{customer_id}/profile")


@customer_mgmt_bp.route("/admin/customers/<int:customer_id>/credit-sale", methods=["POST"])
@role_required("admin", "manager")
def record_credit_sale(customer_id):
    amount = float(request.form.get("amount", 0))
    notes = request.form.get("notes", "")
    result = CustomerLedger.record_credit_sale(customer_id, amount, notes, session.get("user_id"))
    flash(result["message"])
    if result["ok"]:
        log_action(session.get("user_id"), "CREDIT_SALE_RECORDED", f"customer_id={customer_id} amount={amount}")
    return redirect(f"/admin/customers/{customer_id}/profile")


@customer_mgmt_bp.route("/admin/customers/<int:customer_id>/credit-payment", methods=["POST"])
@role_required("admin", "manager")
def record_credit_payment(customer_id):
    amount = float(request.form.get("amount", 0))
    result = CustomerLedger.record_credit_payment(customer_id, amount, session.get("user_id"))
    flash(result["message"])
    if result["ok"]:
        log_action(session.get("user_id"), "CREDIT_PAYMENT_RECORDED", f"customer_id={customer_id} amount={amount}")
    return redirect(f"/admin/customers/{customer_id}/profile")


@customer_mgmt_bp.route("/admin/customers/analytics")
@role_required("admin", "manager", "accountant")
def customers_analytics():
    data = Customer.get_all_analytics()
    return render_template("admin/customers/analytics.html", customers=data)


# ---------------------------------------------------------------
# Exports
# ---------------------------------------------------------------
_CUSTOMER_HEADERS = ["Customer ID", "Name", "Membership", "Loyalty Points",
                     "Wallet Balance", "Credit Limit", "Credit Due",
                     "Total Orders", "Total Spent"]


def _customer_export_rows():
    data = Customer.get_all_analytics()
    return [[d[0], d[1], d[2], d[3], d[4], d[5], d[6], d[7], float(d[8])] for d in data]


@customer_mgmt_bp.route("/admin/customers/export/csv")
@role_required("admin", "manager", "accountant")
def export_customers_csv():
    return export_csv(_CUSTOMER_HEADERS, _customer_export_rows(), "customers.csv")


@customer_mgmt_bp.route("/admin/customers/export/excel")
@role_required("admin", "manager", "accountant")
def export_customers_excel():
    return export_excel(_CUSTOMER_HEADERS, _customer_export_rows(), "customers.xlsx", "Customers")


@customer_mgmt_bp.route("/admin/customers/export/pdf")
@role_required("admin", "manager", "accountant")
def export_customers_pdf():
    return export_pdf(_CUSTOMER_HEADERS, _customer_export_rows(), "customers.pdf", "Customer Report")
