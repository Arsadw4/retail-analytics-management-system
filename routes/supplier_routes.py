from flask import Blueprint, render_template, request, redirect, session, flash

from models.supplier_model import Supplier
from models.purchase_order_model import PurchaseOrder
from models.grn_model import GRN
from models.product_model import Product
from models.warehouse_model import Warehouse
from database.errors import DatabaseError
from core.rbac import role_required
from core.audit import log_action
from core.export_utils import export_csv, export_excel, export_pdf

supplier_bp = Blueprint("supplier", __name__)


# ---------------------------------------------------------------
# Supplier CRUD / profile / search
# ---------------------------------------------------------------
@supplier_bp.route("/admin/suppliers")
@role_required("admin", "manager", "accountant")
def suppliers():
    query = request.args.get("q")
    data = Supplier.get_all(query=query)
    return render_template("admin/suppliers/suppliers.html", suppliers=data, query=query)


@supplier_bp.route("/admin/add-supplier", methods=["GET", "POST"])
@role_required("admin", "manager")
def add_supplier():
    if request.method == "POST":
        Supplier.create(
            request.form["supplier_name"], request.form.get("contact_person", ""),
            request.form.get("phone", ""), request.form.get("email", ""),
            request.form.get("address", ""), request.form.get("gst_number", "")
        )
        log_action(session.get("user_id"), "SUPPLIER_CREATED", f"name={request.form['supplier_name']}")
        return redirect("/admin/suppliers")
    return render_template("admin/suppliers/add_supplier.html")


@supplier_bp.route("/admin/edit-supplier/<int:id>", methods=["GET", "POST"])
@role_required("admin", "manager")
def edit_supplier(id):
    if request.method == "POST":
        is_active = 1 if request.form.get("is_active") == "on" else 0
        Supplier.update(
            id, request.form["supplier_name"], request.form.get("contact_person", ""),
            request.form.get("phone", ""), request.form.get("email", ""),
            request.form.get("address", ""), request.form.get("gst_number", ""), is_active
        )
        log_action(session.get("user_id"), "SUPPLIER_UPDATED", f"supplier_id={id}")
        return redirect("/admin/suppliers")

    supplier = Supplier.get_by_id(id)
    if supplier is None:
        flash("Supplier not found.")
        return redirect("/admin/suppliers")
    return render_template("admin/suppliers/edit_supplier.html", supplier=supplier)


@supplier_bp.route("/admin/delete-supplier/<int:id>", methods=["POST"])
@role_required("admin", "manager")
def delete_supplier(id):
    try:
        Supplier.delete(id)
    except DatabaseError as e:
        flash(str(e))
        return redirect("/admin/suppliers")
    log_action(session.get("user_id"), "SUPPLIER_DELETED", f"supplier_id={id}")
    return redirect("/admin/suppliers")


@supplier_bp.route("/admin/suppliers/<int:id>/profile")
@role_required("admin", "manager", "accountant")
def supplier_profile(id):
    supplier = Supplier.get_by_id(id)
    if supplier is None:
        flash("Supplier not found.")
        return redirect("/admin/suppliers")

    ledger = Supplier.get_ledger(id)
    pos = PurchaseOrder.get_by_supplier(id)
    performance = Supplier.get_single_performance(id)

    return render_template("admin/suppliers/profile.html",
                           supplier=supplier, ledger=ledger, pos=pos, performance=performance)


@supplier_bp.route("/admin/suppliers/<int:id>/payment", methods=["POST"])
@role_required("admin", "manager")
def record_supplier_payment(id):
    amount = float(request.form.get("amount", 0))
    result = Supplier.record_payment(
        id, amount, request.form.get("payment_method", "bank_transfer"),
        request.form.get("reference_no", ""), request.form.get("notes", ""), session.get("user_id")
    )
    flash(result["message"])
    if result["ok"]:
        log_action(session.get("user_id"), "SUPPLIER_PAYMENT_RECORDED", f"supplier_id={id} amount={amount}")
    return redirect(f"/admin/suppliers/{id}/profile")


@supplier_bp.route("/admin/suppliers/performance")
@role_required("admin", "manager", "accountant")
def suppliers_performance():
    data = Supplier.get_performance()
    return render_template("admin/suppliers/performance.html", suppliers=data)


# ---------------------------------------------------------------
# Purchase Orders
# ---------------------------------------------------------------
@supplier_bp.route("/admin/purchase-orders")
@role_required("admin", "manager", "accountant")
def purchase_orders():
    data = PurchaseOrder.get_all()
    return render_template("admin/suppliers/purchase_orders.html", orders=data)


@supplier_bp.route("/admin/purchase-orders/add", methods=["GET", "POST"])
@role_required("admin", "manager")
def add_purchase_order():
    if request.method == "POST":
        items = []
        product_ids = request.form.getlist("product_id[]")
        quantities = request.form.getlist("quantity[]")
        costs = request.form.getlist("unit_cost[]")

        for pid, qty, cost in zip(product_ids, quantities, costs):
            if pid and qty and cost:
                items.append({"product_id": int(pid), "quantity": int(qty), "unit_cost": float(cost)})

        if not items:
            flash("Add at least one item to the purchase order.")
            return redirect("/admin/purchase-orders/add")

        try:
            po_id, po_number = PurchaseOrder.create(
                int(request.form["supplier_id"]), request.form.get("expected_date") or None,
                request.form.get("notes", ""), items, session.get("user_id")
            )
        except (TypeError, ValueError) as exc:
            flash(str(exc), "error")
            return redirect("/admin/purchase-orders/add")

        log_action(session.get("user_id"), "PO_CREATED", f"po_number={po_number}")
        return redirect(f"/admin/purchase-orders/{po_id}")

    suppliers = Supplier.get_all()
    products = Product.get_all_products()
    return render_template("admin/suppliers/add_purchase_order.html", suppliers=suppliers, products=products)


@supplier_bp.route("/admin/purchase-orders/<int:po_id>")
@role_required("admin", "manager", "accountant")
def view_purchase_order(po_id):
    po, items = PurchaseOrder.get_by_id(po_id)
    if po is None:
        flash("Purchase order not found.")
        return redirect("/admin/purchase-orders")
    return render_template("admin/suppliers/view_purchase_order.html", po=po, items=items)


@supplier_bp.route("/admin/purchase-orders/<int:po_id>/cancel", methods=["POST"])
@role_required("admin", "manager")
def cancel_purchase_order(po_id):
    if not PurchaseOrder.cancel(po_id):
        flash("Purchase order cannot be cancelled because it was not found or has already been fully received.", "error")
    else:
        log_action(session.get("user_id"), "PO_CANCELLED", f"po_id={po_id}")
    return redirect(f"/admin/purchase-orders/{po_id}")


# ---------------------------------------------------------------
# GRN
# ---------------------------------------------------------------
@supplier_bp.route("/admin/grn")
@role_required("admin", "manager", "accountant")
def grn_list():
    data = GRN.get_all()
    return render_template("admin/suppliers/grn_list.html", grns=data)


@supplier_bp.route("/admin/grn/add", methods=["GET", "POST"])
@role_required("admin", "manager")
def add_grn():
    if request.method == "POST":
        items = []
        po_item_ids = request.form.getlist("po_item_id[]")
        product_ids = request.form.getlist("product_id[]")
        quantities = request.form.getlist("quantity[]")
        costs = request.form.getlist("unit_cost[]")

        for poi, pid, qty, cost in zip(po_item_ids, product_ids, quantities, costs):
            if pid and qty and cost:
                items.append({
                    "po_item_id": int(poi) if poi else None,
                    "product_id": int(pid), "quantity": int(qty), "unit_cost": float(cost)
                })

        if not items:
            flash("Add at least one item to the GRN.")
            return redirect("/admin/grn/add")

        warehouse_id = request.form.get("warehouse_id") or None
        try:
            grn_id, grn_number = GRN.create(
                int(request.form["supplier_id"]),
                int(request.form["po_id"]) if request.form.get("po_id") else None,
                request.form.get("received_date"), request.form.get("notes", ""),
                items, session.get("user_id"), warehouse_id
            )
        except (TypeError, ValueError) as exc:
            flash(str(exc), "error")
            return redirect("/admin/grn/add")

        log_action(session.get("user_id"), "GRN_CREATED", f"grn_number={grn_number}")
        return redirect(f"/admin/grn/{grn_id}")

    suppliers = Supplier.get_all()
    products = Product.get_all_products()
    warehouses = Warehouse.get_active()
    po_id = request.args.get("po_id", type=int)
    po_items = None
    if po_id:
        _, po_items = PurchaseOrder.get_by_id(po_id)

    return render_template("admin/suppliers/add_grn.html", suppliers=suppliers, products=products,
                           warehouses=warehouses, po_id=po_id, po_items=po_items)


@supplier_bp.route("/admin/grn/<int:grn_id>")
@role_required("admin", "manager", "accountant")
def view_grn(grn_id):
    grn, items = GRN.get_by_id(grn_id)
    if grn is None:
        flash("GRN not found.")
        return redirect("/admin/grn")
    return render_template("admin/suppliers/view_grn.html", grn=grn, items=items)


# ---------------------------------------------------------------
# Exports
# ---------------------------------------------------------------
_SUPPLIER_HEADERS = ["Supplier ID", "Name", "Outstanding Balance", "Total POs", "Total GRNs", "Total Purchase Value"]


def _supplier_export_rows():
    data = Supplier.get_performance()
    return [[d[0], d[1], float(d[2]), d[3], d[4], float(d[5])] for d in data]


@supplier_bp.route("/admin/suppliers/export/csv")
@role_required("admin", "manager")
def export_suppliers_csv():
    return export_csv(_SUPPLIER_HEADERS, _supplier_export_rows(), "suppliers.csv")


@supplier_bp.route("/admin/suppliers/export/excel")
@role_required("admin", "manager")
def export_suppliers_excel():
    return export_excel(_SUPPLIER_HEADERS, _supplier_export_rows(), "suppliers.xlsx", "Suppliers")


@supplier_bp.route("/admin/suppliers/export/pdf")
@role_required("admin", "manager")
def export_suppliers_pdf():
    return export_pdf(_SUPPLIER_HEADERS, _supplier_export_rows(), "suppliers.pdf", "Supplier Report")
