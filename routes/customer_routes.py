from flask import Blueprint, render_template, request, redirect, flash

from models.customer_model import Customer
from core.rbac import role_required
from core.customer_validation import validate_customer_form

customer_bp = Blueprint("customer", __name__)


@customer_bp.route("/admin/customers")
@role_required("admin", "manager", "employee")
def customers():

    customer_list = Customer.get_all_customers()

    return render_template(
        "admin/customers/customers.html",
        customers=customer_list
    )


@customer_bp.route("/admin/add-customer", methods=["GET", "POST"])
@role_required("admin", "manager", "employee")
def add_customer():

    if request.method == "POST":
        customer, errors = validate_customer_form(request.form)
        if errors:
            for error in errors:
                flash(error, "error")
            return redirect("/admin/add-customer")

        Customer.add_customer(
            customer["name"], customer["phone"],
            customer["email"], customer["address"]
        )

        return redirect("/admin/customers")

    return render_template(
        "admin/customers/add_customer.html"
    )

@customer_bp.route("/admin/edit-customer/<int:id>", methods=["GET","POST"])
@role_required("admin", "manager", "employee")
def edit_customer(id):
    customer_record = Customer.get_customer(id)
    if customer_record is None:
        flash("Customer not found.", "error")
        return redirect("/admin/customers")

    if request.method == "POST":
        customer, errors = validate_customer_form(request.form)
        if errors:
            for error in errors:
                flash(error, "error")
            return redirect(f"/admin/edit-customer/{id}")

        Customer.update_customer(
            id,
            customer["name"], customer["phone"],
            customer["email"], customer["address"]
        )

        return redirect("/admin/customers")

    return render_template(
        "admin/customers/edit_customer.html",
        customer=customer_record
    )
