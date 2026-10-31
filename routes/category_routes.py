from flask import Blueprint, render_template, request, redirect, session, flash

from models.category_model import Category
from core.rbac import role_required
from core.audit import log_action
from database.errors import DatabaseError

category_bp = Blueprint(
    "category",
    __name__
)


@category_bp.route("/admin/categories")
@role_required("admin", "manager")
def categories():

    categories = Category.get_all_categories()

    return render_template(
        "admin/categories/categories.html",
        categories=categories
    )


@category_bp.route(
    "/admin/add-category",
    methods=["GET", "POST"]
)
@role_required("admin", "manager")
def add_category():

    if request.method == "POST":

        category_name = request.form["category_name"]

        Category.add_category(category_name)

        return redirect("/admin/categories")

    return render_template(
        "admin/categories/add_category.html"
    )


@category_bp.route(
    "/admin/edit-category/<int:category_id>",
    methods=["GET", "POST"]
)
@role_required("admin", "manager")
def edit_category(category_id):

    if request.method == "POST":

        category_name = request.form["category_name"]

        Category.update_category(
            category_id,
            category_name
        )

        return redirect("/admin/categories")

    category = Category.get_category_by_id(
        category_id
    )

    return render_template(
        "admin/categories/edit_category.html",
        category=category
    )


@category_bp.route(
    "/admin/delete-category/<int:category_id>",
    methods=["POST"]
)
@role_required("admin", "manager")
def delete_category(category_id):

    try:
        Category.delete_category(category_id)
    except DatabaseError as e:
        flash(str(e))
        return redirect("/admin/categories")

    log_action(session.get("user_id"), "CATEGORY_DELETED", f"category_id={category_id}")

    return redirect("/admin/categories")
