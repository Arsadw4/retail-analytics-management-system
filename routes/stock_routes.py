from flask import Blueprint, render_template, request, redirect, session, flash

from models.product_model import Product
from models.inventory_model import Inventory
from models.warehouse_model import Warehouse
from models.stock_movement_model import StockMovement
from models.batch_model import Batch
from database.db import mysql
from core.rbac import role_required
from core.audit import log_action

stock_bp = Blueprint("stock", __name__)


def _get_reorder_suggestions():
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT product_id, product_name, current_stock, minimum_stock,
               maximum_stock, suggested_reorder_qty, supplier_name, supplier_contact
        FROM v_reorder_suggestions
    """)
    data = cur.fetchall()
    cur.close()
    return data


@stock_bp.route("/admin/inventory/dashboard")
@role_required("admin", "manager", "inventory_manager")
def inventory_dashboard():
    summary = Inventory.inventory_summary()
    low_stock = Inventory.low_stock_count()
    out_stock = Inventory.out_of_stock_count()

    cur = mysql.connection.cursor()
    cur.execute("SELECT COUNT(*) FROM warehouses WHERE is_active=TRUE")
    warehouse_count = cur.fetchone()[0]
    cur.close()

    reorder_data = _get_reorder_suggestions()
    expiring_soon = Batch.get_expiring(days=30)
    recent_movements = StockMovement.get_history(limit=15)

    return render_template(
        "admin/inventory/dashboard.html",
        summary=summary,
        low_stock=low_stock,
        out_stock=out_stock,
        warehouse_count=warehouse_count,
        reorder_suggestions=reorder_data,
        expiring_soon=expiring_soon,
        recent_movements=recent_movements
    )


@stock_bp.route("/admin/inventory/reorder-suggestions")
@role_required("admin", "manager", "inventory_manager")
def reorder_suggestions():
    data = _get_reorder_suggestions()
    return render_template("admin/inventory/reorder_suggestions.html", suggestions=data)


@stock_bp.route("/admin/inventory/stock-in", methods=["GET", "POST"])
@role_required("admin", "manager", "employee", "inventory_manager")
def stock_in():
    if request.method == "POST":
        product_id = int(request.form["product_id"])
        quantity = int(request.form["quantity"])
        warehouse_id = request.form.get("warehouse_id") or None
        reason = request.form.get("reason", "Stock In")

        success = StockMovement.stock_in(
            product_id, quantity, warehouse_id, reason, session.get("user_id")
        )

        if not success:
            flash("Stock In failed. Check the product and quantity.")
        else:
            log_action(session.get("user_id"), "STOCK_IN",
                       f"product_id={product_id} qty={quantity}")
            flash("Stock added successfully.")

        return redirect("/admin/inventory")

    products = Product.get_all_products()
    warehouses = Warehouse.get_active()
    preselect = request.args.get("product_id", type=int)
    return render_template("admin/inventory/stock_in.html", products=products,
                           warehouses=warehouses, preselect=preselect)


@stock_bp.route("/admin/inventory/stock-out", methods=["GET", "POST"])
@role_required("admin", "manager", "employee", "inventory_manager")
def stock_out():
    if request.method == "POST":
        product_id = int(request.form["product_id"])
        quantity = int(request.form["quantity"])
        warehouse_id = request.form.get("warehouse_id") or None
        reason = request.form.get("reason", "Stock Out")

        success = StockMovement.stock_out(
            product_id, quantity, warehouse_id, reason, session.get("user_id")
        )

        if not success:
            flash("Stock Out failed. Insufficient stock or invalid product.")
        else:
            log_action(session.get("user_id"), "STOCK_OUT",
                       f"product_id={product_id} qty={quantity}")
            flash("Stock removed successfully.")

        return redirect("/admin/inventory")

    products = Product.get_all_products()
    warehouses = Warehouse.get_active()
    preselect = request.args.get("product_id", type=int)
    return render_template("admin/inventory/stock_out.html", products=products,
                           warehouses=warehouses, preselect=preselect)


@stock_bp.route("/admin/inventory/movements")
@role_required("admin", "manager", "inventory_manager")
def movements():
    product_id = request.args.get("product_id", type=int)
    movement_type = request.args.get("movement_type") or None

    data = StockMovement.get_history(product_id=product_id, movement_type=movement_type)
    products = Product.get_all_products()

    return render_template(
        "admin/inventory/movements.html",
        movements=data,
        products=products,
        selected_product=product_id,
        selected_type=movement_type
    )


@stock_bp.route("/admin/inventory/batches")
@role_required("admin", "manager", "inventory_manager")
def batches():
    data = Batch.get_all()
    return render_template("admin/inventory/batches.html", batches=data)


@stock_bp.route("/admin/inventory/add-batch", methods=["GET", "POST"])
@role_required("admin", "manager", "inventory_manager")
def add_batch():
    if request.method == "POST":
        Batch.add_batch(
            int(request.form["product_id"]),
            request.form["batch_number"],
            int(request.form["quantity"]),
            request.form.get("manufacture_date") or None,
            request.form.get("expiry_date") or None,
            request.form.get("warehouse_id") or None
        )

        log_action(session.get("user_id"), "BATCH_CREATED",
                   f"product_id={request.form['product_id']} batch={request.form['batch_number']}")

        return redirect("/admin/inventory/batches")

    products = Product.get_all_products()
    warehouses = Warehouse.get_active()
    return render_template("admin/inventory/add_batch.html", products=products, warehouses=warehouses)


@stock_bp.route("/admin/inventory/delete-batch/<int:id>", methods=["POST"])
@role_required("admin", "manager", "inventory_manager")
def delete_batch(id):
    Batch.delete_batch(id)
    log_action(session.get("user_id"), "BATCH_DELETED", f"batch_id={id}")
    return redirect("/admin/inventory/batches")


@stock_bp.route("/admin/inventory/expiry-report")
@role_required("admin", "manager", "inventory_manager")
def expiry_report():
    data = Batch.get_expiring(days=None)
    return render_template("admin/inventory/expiry_report.html", batches=data)
