from flask import Blueprint, render_template, request, redirect, session, flash

from models.product_model import Product
from models.inventory_model import Inventory
from core.rbac import role_required
from core.audit import log_action
from database.errors import DatabaseError

inventory_bp = Blueprint('inventory', __name__)


@inventory_bp.route('/admin/inventory')
@role_required("admin", "manager", "inventory_manager")
def inventory():
    inventory_data = Inventory.get_all_inventory()
    return render_template('admin/inventory/inventory.html', inventory=inventory_data)


@inventory_bp.route('/admin/low-stock')
@role_required("admin", "manager", "inventory_manager")
def low_stock():
    low_stock_items = Inventory.get_low_stock()
    return render_template('admin/inventory/low_stock.html', items=low_stock_items)


@inventory_bp.route('/admin/inventory/stock-report')
@role_required("admin", "manager", "inventory_manager")
def stock_report():
    inventory_data = Inventory.get_all_inventory()
    summary = Inventory.inventory_summary()
    low_stock = Inventory.low_stock_count()
    out_stock = Inventory.out_of_stock_count()

    return render_template(
        'admin/inventory/stock_report.html',
        inventory=inventory_data,
        summary=summary,
        low_stock=low_stock,
        out_of_stock=out_stock
    )


@inventory_bp.route('/admin/add-inventory', methods=['GET', 'POST'])
@role_required("admin", "manager", "inventory_manager")
def add_inventory():
    if request.method == "POST":
        # current_stock/purchase_price/selling_price are no longer
        # inventory-specific fields -- they live on the product
        # itself (see database/migrations/002_phase2_schema_redesign.sql).
        # Only reorder thresholds are captured here now.
        try:
            Inventory.create_inventory(
                request.form['product_id'],
                request.form['minimum_stock'],
                request.form['maximum_stock']
            )
        except DatabaseError as e:
            flash(str(e))
            products = Product.get_all_products()
            return render_template('admin/inventory/add_inventory.html', products=products)

        log_action(session.get("user_id"), "INVENTORY_CREATED",
                   f"product_id={request.form['product_id']}")

        return redirect('/admin/inventory')

    products = Product.get_all_products()
    return render_template('admin/inventory/add_inventory.html', products=products)


@inventory_bp.route('/admin/edit-inventory/<int:id>', methods=['GET', 'POST'])
@role_required("admin", "manager", "inventory_manager")
def edit_inventory(id):
    if request.method == "POST":
        Inventory.update_inventory(
            id,
            request.form['minimum_stock'],
            request.form['maximum_stock']
        )

        log_action(session.get("user_id"), "INVENTORY_UPDATED", f"inventory_id={id}")

        return redirect('/admin/inventory')

    item = Inventory.get_inventory_by_id(id)
    return render_template('admin/inventory/edit_inventory.html', item=item)


@inventory_bp.route('/admin/delete-inventory/<int:id>', methods=["POST"])
@role_required("admin", "manager", "inventory_manager")
def delete_inventory(id):
    Inventory.delete_inventory(id)
    log_action(session.get("user_id"), "INVENTORY_DELETED", f"inventory_id={id}")
    return redirect('/admin/inventory')
