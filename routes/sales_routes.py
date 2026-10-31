from flask import Blueprint, render_template, request, redirect, session, flash

from models.sales_model import Sale
from core.rbac import role_required

sales_bp = Blueprint("sales", __name__)


# ---------------------------
# Sales List
# ---------------------------
@sales_bp.route("/admin/sales")
@role_required("admin", "manager", "employee")
def sales():

    sales_list = Sale.get_all_sales()

    return render_template(
        "admin/sales/sales.html",
        sales=sales_list
    )


# ---------------------------
# Create Sale
# ---------------------------
@sales_bp.route(
    "/admin/create-sale",
    methods=["GET", "POST"]
)
@role_required("admin", "manager", "employee")
def create_sale():

    customers = Sale.get_customers()
    products = Sale.get_products()

    if request.method == "POST":

        try:
            customer_id = int(request.form["customer_id"]) if request.form.get("customer_id") else None
            product_id = int(request.form["product_id"])
            quantity = int(request.form["quantity"])
        except (TypeError, ValueError):
            flash("Please enter valid sale details.", "error")
            return redirect("/admin/create-sale")

        user_id = session.get("user_id")
        if not user_id:
            flash("Your session has expired. Please log in again.", "error")
            return redirect("/login")

        success = Sale.create_sale(customer_id, user_id, product_id, quantity)
        if not success:
            flash("Sale could not be completed. Check the product, customer and available stock.", "error")
            return redirect("/admin/create-sale")

        flash("Sale created successfully.", "success")
        return redirect("/admin/sales")

    return render_template(
        "admin/sales/create_sale.html",
        customers=customers,
        products=products
    )


# ---------------------------
# Invoice
# ---------------------------
@sales_bp.route("/admin/invoice/<int:sale_id>")
@role_required("admin", "manager", "employee")
def invoice(sale_id):
    # Compatibility URL: use the canonical billing invoice so sales-list
    # links and global-search results always open the complete invoice.
    return redirect(f"/admin/billing/invoice/{sale_id}")
