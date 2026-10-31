import json

from flask import (Blueprint, render_template, request, redirect, session,
                    flash, jsonify, send_file)
import io

from models.product_model import Product
from models.customer_model import Customer
from models.billing_model import Billing
from models.coupon_model import Coupon
from models.sales_return_model import SalesReturn
from models.held_bill_model import HeldBill
from models.company_settings_model import CompanySettings
from core.rbac import role_required
from core.audit import log_action
from core.invoice_pdf import build_invoice_pdf
from core.email_service import send_invoice_email
from database.db import mysql

billing_bp = Blueprint("billing", __name__)


# ---------------------------------------------------------------
# POS
# ---------------------------------------------------------------
@billing_bp.route("/admin/billing/pos")
@role_required("admin", "manager", "employee", "cashier")
def pos():
    products = Product.get_pos_catalog()
    customers = Customer.get_all_customers()
    company = CompanySettings.get()
    resume_id = request.args.get("resume", type=int)
    resume_cart = None
    resume_customer = None
    if resume_id:
        row = HeldBill.get_cart(resume_id)
        if row:
            resume_cart = row[0]
            resume_customer = row[1]

    return render_template(
        "admin/billing/pos.html",
        products=products,
        customers=customers,
        company=company,
        resume_cart=resume_cart,
        resume_customer=resume_customer,
        resume_id=resume_id
    )


@billing_bp.route("/admin/billing/preview", methods=["POST"])
@role_required("admin", "manager", "employee", "cashier")
def preview_checkout():
    payload = request.get_json(force=True, silent=True) or {}
    return jsonify(Billing.preview_totals(
        items=payload.get("items", []),
        coupon_code=(payload.get("coupon_code") or "").strip() or None,
        customer_state=(payload.get("customer_state") or "").strip() or None
    ))


@billing_bp.route("/admin/billing/checkout", methods=["POST"])
@role_required("admin", "manager", "employee", "cashier")
def checkout():
    payload = request.get_json(force=True, silent=True) or {}

    items = payload.get("items", [])
    customer_id = payload.get("customer_id") or None
    payment_methods = payload.get("payment_methods", [])
    coupon_code = (payload.get("coupon_code") or "").strip() or None
    customer_state = (payload.get("customer_state") or "").strip() or None
    hold_id = payload.get("hold_id")

    result = Billing.create_bill(
        items=items,
        customer_id=customer_id,
        user_id=session.get("user_id"),
        payment_methods=payment_methods,
        coupon_code=coupon_code,
        customer_state=customer_state
    )

    if result["ok"]:
        log_action(session.get("user_id"), "SALE_CREATED",
                   f"invoice={result['invoice_number']}")
        if hold_id:
            HeldBill.delete(hold_id)
        if customer_id:
            from models.customer_ledger_model import CustomerLedger
            sale, _, _ = Billing.get_invoice(result["sale_id"])
            if sale:
                CustomerLedger.earn_loyalty_for_sale(
                    customer_id, sale[3], result["sale_id"], session.get("user_id")
                )

    return jsonify(result)


@billing_bp.route("/api/products/for-pos")
@role_required("admin", "manager", "employee", "cashier")
def products_for_pos():
    products = Product.get_all_products()
    return jsonify([
        {"product_id": p[0], "category": p[1], "name": p[2],
         "purchase_price": float(p[3]), "selling_price": float(p[4]), "stock": p[5]}
        for p in products
    ])


# ---------------------------------------------------------------
# Hold & Resume
# ---------------------------------------------------------------
@billing_bp.route("/admin/billing/hold", methods=["POST"])
@role_required("admin", "manager", "employee", "cashier")
def hold_bill():
    payload = request.get_json(force=True, silent=True) or {}
    cart_json = json.dumps(payload.get("items", []))
    customer_id = payload.get("customer_id") or None
    note = payload.get("note", "")

    hold_id = HeldBill.hold(cart_json, customer_id, session.get("user_id"), note)
    log_action(session.get("user_id"), "BILL_HELD", f"hold_id={hold_id}")
    return jsonify({"ok": True, "hold_id": hold_id})


@billing_bp.route("/admin/billing/held")
@role_required("admin", "manager", "employee", "cashier")
def held_bills():
    data = HeldBill.get_all()
    return render_template("admin/billing/held_bills.html", held=data)


@billing_bp.route("/admin/billing/held/delete/<int:id>", methods=["POST"])
@role_required("admin", "manager", "employee", "cashier")
def delete_held(id):
    HeldBill.delete(id)
    return redirect("/admin/billing/held")


# ---------------------------------------------------------------
# Invoice view / PDF / email / search / reprint
# ---------------------------------------------------------------
@billing_bp.route("/admin/billing/invoice/<int:sale_id>")
@role_required("admin", "manager", "employee", "cashier")
def view_invoice(sale_id):
    sale, items, payments = Billing.get_invoice(sale_id)
    if sale is None:
        flash("Invoice not found.")
        return redirect("/admin/billing/search")

    company = CompanySettings.get()
    width = request.args.get("width", "a4")
    return render_template(
        "admin/billing/invoice.html",
        sale=sale, items=items, payments=payments, company=company, width=width
    )


@billing_bp.route("/admin/billing/invoice/<int:sale_id>/pdf")
@role_required("admin", "manager", "employee", "cashier")
def invoice_pdf(sale_id):
    sale, items, payments = Billing.get_invoice(sale_id)
    if sale is None:
        return "Invoice not found", 404

    company = CompanySettings.get()
    pdf_bytes = build_invoice_pdf(company, sale, items, payments)
    return send_file(io.BytesIO(pdf_bytes), mimetype="application/pdf",
                      as_attachment=True, download_name=f"{sale[1]}.pdf")


@billing_bp.route("/admin/billing/invoice/<int:sale_id>/email", methods=["POST"])
@role_required("admin", "manager", "employee", "cashier")
def email_invoice(sale_id):
    sale, items, payments = Billing.get_invoice(sale_id)
    if sale is None:
        flash("Invoice not found.")
        return redirect("/admin/billing/search")

    to_email = request.form.get("email") or sale[15]
    if not to_email:
        flash("No email address available for this customer.")
        return redirect(f"/admin/billing/invoice/{sale_id}")

    company = CompanySettings.get()
    pdf_bytes = build_invoice_pdf(company, sale, items, payments)

    ok, message = send_invoice_email(
        to_email,
        f"Invoice {sale[1]} from {company[1] if company else 'Retail Company'}",
        "Please find your invoice attached. Thank you for your business.",
        pdf_bytes,
        f"{sale[1]}.pdf"
    )

    flash(message)
    if ok:
        log_action(session.get("user_id"), "INVOICE_EMAILED", f"sale_id={sale_id} to={to_email}")

    return redirect(f"/admin/billing/invoice/{sale_id}")


@billing_bp.route("/admin/billing/search")
@role_required("admin", "manager", "employee", "cashier")
def search_invoices():
    query = request.args.get("q")
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")

    results = Billing.search_invoices(query=query, date_from=date_from, date_to=date_to)
    return render_template("admin/billing/search.html", results=results,
                           query=query, date_from=date_from, date_to=date_to)


# ---------------------------------------------------------------
# Returns
# ---------------------------------------------------------------
@billing_bp.route("/admin/billing/returns")
@role_required("admin", "manager")
def returns_list():
    data = SalesReturn.get_all_returns()
    return render_template("admin/billing/returns.html", returns=data)


@billing_bp.route("/admin/billing/returns/new/<int:sale_id>", methods=["GET", "POST"])
@role_required("admin", "manager", "employee", "cashier")
def new_return(sale_id):
    if request.method == "POST":
        items = []
        for key, value in request.form.items():
            if key.startswith("qty_") and value and int(value) > 0:
                pid = int(key.replace("qty_", ""))
                items.append({"product_id": pid, "quantity": int(value)})

        result = SalesReturn.create_return(
            sale_id, items, request.form.get("reason", ""), session.get("user_id")
        )

        if not result["ok"]:
            flash(result["message"])
            return redirect(f"/admin/billing/returns/new/{sale_id}")

        log_action(session.get("user_id"), "SALE_RETURNED",
                   f"sale_id={sale_id} refund={result['refund_amount']}")
        flash(f"Return processed. Refund amount: {result['refund_amount']:.2f}")
        return redirect("/admin/billing/returns")

    sale, _, _ = Billing.get_invoice(sale_id)
    returnable = SalesReturn.get_returnable_items(sale_id)
    return render_template("admin/billing/new_return.html", sale=sale, items=returnable, sale_id=sale_id)


# ---------------------------------------------------------------
# Dashboard & Reports
# ---------------------------------------------------------------
@billing_bp.route("/admin/billing/dashboard")
@role_required("admin", "manager", "accountant")
def billing_dashboard():
    summary = Billing.dashboard_summary()
    return render_template("admin/billing/dashboard.html", summary=summary)


def _fetch_view(view_name):
    cur = mysql.connection.cursor()
    cur.execute(f"SELECT * FROM {view_name}")
    data = cur.fetchall()
    cur.close()
    return data


@billing_bp.route("/admin/billing/reports/daily")
@role_required("admin", "manager", "accountant")
def report_daily():
    return render_template("admin/billing/report_period.html",
                           rows=_fetch_view("v_daily_sales"), period="Daily")


@billing_bp.route("/admin/billing/reports/weekly")
@role_required("admin", "manager", "accountant")
def report_weekly():
    return render_template("admin/billing/report_period.html",
                           rows=_fetch_view("v_weekly_sales"), period="Weekly")


@billing_bp.route("/admin/billing/reports/monthly")
@role_required("admin", "manager", "accountant")
def report_monthly():
    return render_template("admin/billing/report_period.html",
                           rows=_fetch_view("v_monthly_sales"), period="Monthly")


@billing_bp.route("/admin/billing/reports/tax")
@role_required("admin", "manager", "accountant")
def report_tax():
    return render_template("admin/billing/report_tax.html", rows=_fetch_view("v_tax_report"))


# ---------------------------------------------------------------
# Coupons
# ---------------------------------------------------------------
@billing_bp.route("/admin/coupons")
@role_required("admin", "manager")
def coupons():
    data = Coupon.get_all()
    return render_template("admin/billing/coupons.html", coupons=data)


@billing_bp.route("/admin/coupons/add", methods=["GET", "POST"])
@role_required("admin", "manager")
def add_coupon():
    if request.method == "POST":
        from database.errors import DatabaseError
        try:
            Coupon.create(
                request.form["code"],
                request.form["discount_type"],
                float(request.form["discount_value"]),
                float(request.form.get("min_purchase_amount") or 0),
                request.form.get("valid_from") or None,
                request.form.get("valid_until") or None,
                int(request.form["usage_limit"]) if request.form.get("usage_limit") else None
            )
        except DatabaseError as e:
            flash(str(e))
            return render_template("admin/billing/add_coupon.html")

        log_action(session.get("user_id"), "COUPON_CREATED", f"code={request.form['code']}")
        return redirect("/admin/coupons")

    return render_template("admin/billing/add_coupon.html")


@billing_bp.route("/admin/coupons/delete/<int:id>", methods=["POST"])
@role_required("admin", "manager")
def delete_coupon(id):
    Coupon.delete(id)
    log_action(session.get("user_id"), "COUPON_DELETED", f"coupon_id={id}")
    return redirect("/admin/coupons")


# ---------------------------------------------------------------
# Customer billing history
# ---------------------------------------------------------------
@billing_bp.route("/admin/customers/<int:customer_id>/billing-history")
@role_required("admin", "manager", "employee", "cashier")
def customer_billing_history(customer_id):
    customer = Customer.get_customer(customer_id)
    history = Billing.get_customer_billing_history(customer_id)
    return render_template("admin/billing/customer_history.html", customer=customer, history=history)
