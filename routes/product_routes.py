import logging
import os
import uuid

from flask import Blueprint, render_template, request, redirect, session, flash, current_app
from werkzeug.utils import secure_filename

from models.product_model import Product
from models.category_model import Category
from core.rbac import role_required
from core.audit import log_action
from core.product_validation import validate_product_form
from database.errors import DatabaseError

product_bp = Blueprint('product', __name__)
logger = logging.getLogger(__name__)


def _allowed_image(filename: str) -> bool:
    """
    Extension allow-list check. Uploaded product images were
    previously accepted with no validation at all -- any file type
    could be saved into static/uploads and, depending on server
    config, potentially be served back as executable content (e.g. a
    disguised .html/.svg enabling stored XSS). We only accept the
    image extensions declared in config.UPLOAD_ALLOWED_EXTENSIONS.
    Belt-and-braces: MAX_CONTENT_LENGTH in config.py also caps upload
    size at the WSGI layer regardless of what a route does.
    """
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in current_app.config["UPLOAD_ALLOWED_EXTENSIONS"]


def _save_product_image(image):
    if not image or image.filename == "":
        return ""

    if not _allowed_image(image.filename):
        return None

    original = secure_filename(image.filename)
    if not original or "." not in original:
        return None
    ext = original.rsplit(".", 1)[1].lower()

    # Verify the actual image payload, not only its extension.
    try:
        from PIL import Image
        image.stream.seek(0)
        img = Image.open(image.stream)
        img.verify()
        image.stream.seek(0)
        img = Image.open(image.stream)
        img.thumbnail((1200, 1200))
        if ext in ("jpg", "jpeg"):
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            save_ext = "jpg"
        else:
            save_ext = ext
        filename = f"{uuid.uuid4().hex}.{save_ext}"
        save_path = os.path.join(current_app.static_folder, "uploads", filename)
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        if save_ext == "jpg":
            img.save(save_path, format="JPEG", quality=88, optimize=True)
        elif save_ext == "webp":
            img.save(save_path, format="WEBP", quality=88, method=6)
        else:
            img.save(save_path, format="PNG", optimize=True)
        return filename
    except Exception:
        logger.exception("Could not validate or save an uploaded product image.")
        return None


@product_bp.route('/admin/products')
@role_required("admin", "manager", "employee")
def products():
    products = Product.get_all_products()
    return render_template('admin/products/products.html', products=products)


@product_bp.route('/admin/products/<int:product_id>')
@role_required("admin", "manager", "employee")
def product_details(product_id):
    product = Product.get_product_by_id(product_id)
    if product is None:
        flash("Product not found.")
        return redirect('/admin/products')
    categories = Category.get_all_categories()
    category_name = next((c[1] for c in categories if c[0] == product[1]), None)
    return render_template('admin/products/product_details.html', product=product, category_name=category_name)


@product_bp.route('/admin/add-product', methods=['GET', 'POST'])
@role_required("admin", "manager")
def add_product():
    if request.method == 'POST':
        categories = Category.get_all_categories()
        product, errors = validate_product_form(
            request.form, {category[0] for category in categories}
        )
        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('admin/products/add_product.html', categories=categories)

        filename = _save_product_image(request.files.get('product_image'))

        if filename is None:
            flash("Unsupported image type. Allowed: " +
                  ", ".join(sorted(current_app.config["UPLOAD_ALLOWED_EXTENSIONS"])))
            return render_template('admin/products/add_product.html', categories=Category.get_all_categories())

        try:
            product_id = Product.create_product(
                product['category_id'],
                product['product_name'],
                product['purchase_price'],
                product['selling_price'],
                product['stock_quantity'],
                filename,
                session.get('user_id'),
                product['sku'],
            )
        except (ValueError, DatabaseError) as exc:
            if filename:
                try:
                    os.remove(os.path.join(current_app.static_folder, 'uploads', filename))
                except OSError:
                    pass
            flash(str(exc), 'error')
            return redirect('/admin/products')

        log_action(session.get("user_id"), "PRODUCT_CREATED",
                   f"product_id={product_id} name={product['product_name']}")

        return redirect('/admin/products')

    return render_template('admin/products/add_product.html', categories=Category.get_all_categories())


@product_bp.route('/admin/delete-product/<int:product_id>', methods=["POST"])
@role_required("admin", "manager")
def delete_product(product_id):
    product = Product.get_product_by_id(product_id)
    try:
        Product.delete_product(product_id)
    except DatabaseError as e:
        flash(str(e))
        return redirect('/admin/products')

    if product and product[8]:
        try:
            os.remove(os.path.join(current_app.static_folder, 'uploads', product[8]))
        except OSError:
            pass

    log_action(session.get("user_id"), "PRODUCT_DELETED", f"product_id={product_id}")
    return redirect('/admin/products')


@product_bp.route('/admin/edit-product/<int:product_id>', methods=['GET', 'POST'])
@role_required("admin", "manager")
def edit_product(product_id):
    product = Product.get_product_by_id(product_id)
    if product is None:
        flash('Product not found.')
        return redirect('/admin/products')

    if request.method == 'POST':
        categories = Category.get_all_categories()
        product_values, errors = validate_product_form(
            request.form, {category[0] for category in categories}
        )
        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template(
                'admin/products/edit_product.html',
                product=product,
                categories=categories,
            )

        old_image = product[8] or ""
        remove_image = request.form.get('remove_product_image') == '1'
        uploaded = request.files.get('product_image')
        new_image = old_image
        saved_new = None

        if uploaded and uploaded.filename:
            saved_new = _save_product_image(uploaded)
            if not saved_new:
                flash("Invalid product image. Use a valid JPG, PNG or WEBP image.", 'error')
                return redirect(f'/admin/edit-product/{product_id}')
            new_image = saved_new
        elif remove_image:
            new_image = ""

        try:
            Product.update_product(
                product_id,
                product_values['category_id'],
                product_values['product_name'],
                product_values['purchase_price'],
                product_values['selling_price'],
                product_values['stock_quantity'],
                new_image,
                session.get('user_id')
            )
        except (ValueError, DatabaseError) as exc:
            if saved_new:
                try:
                    os.remove(os.path.join(current_app.static_folder, 'uploads', saved_new))
                except OSError:
                    pass
            flash(str(exc), 'error')
            return redirect(f'/admin/edit-product/{product_id}')

        # Remove the previous file only after the DB update succeeds.
        if old_image and old_image != new_image:
            try:
                os.remove(os.path.join(current_app.static_folder, 'uploads', old_image))
            except OSError:
                pass

        log_action(session.get("user_id"), "PRODUCT_UPDATED", f"product_id={product_id}")
        return redirect('/admin/products')

    return render_template('admin/products/edit_product.html', product=product, categories=Category.get_all_categories())
