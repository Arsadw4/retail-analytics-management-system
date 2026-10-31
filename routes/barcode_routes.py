import io

from flask import Blueprint, send_file, render_template, jsonify

from models.product_model import Product
from core.rbac import role_required

barcode_bp = Blueprint("barcode", __name__)


@barcode_bp.route("/admin/products/<int:product_id>/barcode.png")
@role_required("admin", "manager", "employee", "inventory_manager")
def product_barcode_image(product_id):
    """
    Renders a Code128 barcode on the fly from the product's barcode
    value -- nothing is stored on disk, so it's always in sync with
    whatever the product's current barcode value is.
    """
    import barcode
    from barcode.writer import ImageWriter
    from database.db import mysql
    cur = mysql.connection.cursor()
    cur.execute("SELECT barcode FROM products WHERE product_id=%s", (product_id,))
    row = cur.fetchone()
    cur.close()

    if not row or not row[0]:
        return "No barcode set for this product", 404

    code = barcode.get("code128", row[0], writer=ImageWriter())
    buf = io.BytesIO()
    code.write(buf, options={"write_text": True, "module_height": 8.0})
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


@barcode_bp.route("/admin/products/<int:product_id>/qrcode.png")
@role_required("admin", "manager", "employee", "inventory_manager")
def product_qrcode_image(product_id):
    import qrcode
    from database.db import mysql

    cur = mysql.connection.cursor()
    cur.execute("SELECT barcode, product_name FROM products WHERE product_id=%s", (product_id,))
    row = cur.fetchone()
    cur.close()

    if not row:
        return "Product not found", 404

    payload = row[0] or f"PRODUCT-{product_id}"
    img = qrcode.make(payload)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


@barcode_bp.route("/admin/inventory/scan")
@role_required("admin", "manager", "employee", "inventory_manager")
def scan_page():
    return render_template("admin/inventory/scan.html")


@barcode_bp.route("/api/products/lookup-barcode/<code>")
@role_required("admin", "manager", "employee", "inventory_manager")
def lookup_barcode(code):
    """JSON lookup used by the browser-based scanner (scan.js)."""
    product = Product.get_by_barcode(code)

    if not product:
        return jsonify({"found": False}), 404

    return jsonify({
        "found": True,
        "product_id": product[0],
        "product_name": product[1],
        "sku": product[2],
        "barcode": product[3],
        "purchase_price": float(product[4]),
        "selling_price": float(product[5]),
        "stock_quantity": product[6],
    })
