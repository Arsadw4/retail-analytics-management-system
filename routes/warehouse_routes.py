from flask import Blueprint, render_template, request, redirect, session, flash

from models.warehouse_model import Warehouse
from core.rbac import role_required
from core.audit import log_action
from database.errors import DatabaseError

warehouse_bp = Blueprint("warehouse", __name__)


@warehouse_bp.route("/admin/warehouses")
@role_required("admin", "manager", "inventory_manager")
def warehouses():
    data = Warehouse.get_all()
    return render_template("admin/warehouses/warehouses.html", warehouses=data)


@warehouse_bp.route("/admin/add-warehouse", methods=["GET", "POST"])
@role_required("admin", "manager", "inventory_manager")
def add_warehouse():
    if request.method == "POST":
        try:
            Warehouse.create(
                request.form["warehouse_name"],
                request.form.get("location", ""),
                request.form.get("contact_person", ""),
                request.form.get("contact_phone", "")
            )
        except DatabaseError as e:
            flash(str(e))
            return render_template("admin/warehouses/add_warehouse.html")

        log_action(session.get("user_id"), "WAREHOUSE_CREATED",
                   f"name={request.form['warehouse_name']}")
        return redirect("/admin/warehouses")

    return render_template("admin/warehouses/add_warehouse.html")


@warehouse_bp.route("/admin/edit-warehouse/<int:id>", methods=["GET", "POST"])
@role_required("admin", "manager", "inventory_manager")
def edit_warehouse(id):
    if request.method == "POST":
        is_active = 1 if request.form.get("is_active") == "on" else 0
        try:
            Warehouse.update(
                id,
                request.form["warehouse_name"],
                request.form.get("location", ""),
                request.form.get("contact_person", ""),
                request.form.get("contact_phone", ""),
                is_active
            )
        except DatabaseError as e:
            flash(str(e))
            return redirect(f"/admin/edit-warehouse/{id}")

        log_action(session.get("user_id"), "WAREHOUSE_UPDATED", f"warehouse_id={id}")
        return redirect("/admin/warehouses")

    warehouse = Warehouse.get_by_id(id)
    if warehouse is None:
        flash("Warehouse not found.")
        return redirect("/admin/warehouses")
    return render_template("admin/warehouses/edit_warehouse.html", warehouse=warehouse)


@warehouse_bp.route("/admin/delete-warehouse/<int:id>", methods=["POST"])
@role_required("admin", "manager", "inventory_manager")
def delete_warehouse(id):
    try:
        Warehouse.delete(id)
    except DatabaseError as e:
        flash(str(e))
        return redirect("/admin/warehouses")

    log_action(session.get("user_id"), "WAREHOUSE_DELETED", f"warehouse_id={id}")
    return redirect("/admin/warehouses")
