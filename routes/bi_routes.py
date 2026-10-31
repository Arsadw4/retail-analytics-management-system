from flask import Blueprint, render_template, request, redirect, session, flash

from models.bi_access_model import BIStoreAccess
from models.user_model import User
from models.warehouse_model import Warehouse
from database.errors import DatabaseError
from core.rbac import role_required
from core.audit import log_action

bi_bp = Blueprint("bi", __name__)


@bi_bp.route("/admin/bi/store-access")
@role_required("admin", "super_admin")
def store_access():
    return render_template(
        "admin/bi/store_access.html",
        access_list=BIStoreAccess.get_all(),
        users=User.get_all_users(),
        warehouses=Warehouse.get_active()
    )


@bi_bp.route("/admin/bi/store-access/grant", methods=["POST"])
@role_required("admin", "super_admin")
def grant_store_access():
    try:
        BIStoreAccess.grant(int(request.form["user_id"]), int(request.form["warehouse_id"]))
    except DatabaseError as e:
        flash(str(e))
        return redirect("/admin/bi/store-access")

    log_action(session.get("user_id"), "BI_STORE_ACCESS_GRANTED",
               f"user_id={request.form['user_id']} warehouse_id={request.form['warehouse_id']}")
    return redirect("/admin/bi/store-access")


@bi_bp.route("/admin/bi/store-access/revoke/<int:access_id>", methods=["POST"])
@role_required("admin", "super_admin")
def revoke_store_access(access_id):
    BIStoreAccess.revoke(access_id)
    log_action(session.get("user_id"), "BI_STORE_ACCESS_REVOKED", f"access_id={access_id}")
    return redirect("/admin/bi/store-access")
