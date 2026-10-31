import io

from flask import Blueprint, render_template, request, redirect, session, flash, send_file, current_app

from models.mfa_model import MFA
from core.rbac import role_required
from core.audit import log_action

security_bp = Blueprint("security", __name__)


@security_bp.route("/account/security")
@role_required("admin", "manager", "cashier", "inventory_manager", "hr", "accountant", "employee", "super_admin")
def security_settings():
    status = MFA.get_status(session["user_id"])
    mfa_enabled = bool(status[0]) if status else False
    return render_template("account/security_settings.html", mfa_enabled=mfa_enabled)


@security_bp.route("/account/security/mfa/setup", methods=["GET", "POST"])
@role_required("admin", "manager", "cashier", "inventory_manager", "hr", "accountant", "employee", "super_admin")
def mfa_setup():
    user_id = session["user_id"]

    if request.method == "POST":
        code = request.form.get("code", "").strip()
        secret = MFA.get_pending_secret(user_id)

        if secret and MFA.verify_code(secret, code):
            MFA.enable(user_id)
            log_action(user_id, "MFA_ENABLED", "", request.remote_addr)
            flash("Two-factor authentication enabled.")
            return redirect("/account/security")

        flash("Invalid code -- please try again.")

    secret = MFA.generate_secret()
    MFA.save_pending_secret(user_id, secret)
    uri = MFA.provisioning_uri(session.get("name", "user"), secret, current_app.config["MFA_ISSUER_NAME"])

    return render_template("account/mfa_setup.html", secret=secret, uri=uri)


@security_bp.route("/account/security/mfa/qrcode.png")
@role_required("admin", "manager", "cashier", "inventory_manager", "hr", "accountant", "employee", "super_admin")
def mfa_qrcode():
    import qrcode

    user_id = session["user_id"]
    secret = MFA.get_pending_secret(user_id)
    if not secret:
        return "No pending MFA setup", 404

    uri = MFA.provisioning_uri(session.get("name", "user"), secret, current_app.config["MFA_ISSUER_NAME"])
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


@security_bp.route("/account/security/mfa/disable", methods=["POST"])
@role_required("admin", "manager", "cashier", "inventory_manager", "hr", "accountant", "employee", "super_admin")
def mfa_disable():
    MFA.disable(session["user_id"])
    log_action(session["user_id"], "MFA_DISABLED", "", request.remote_addr)
    flash("Two-factor authentication disabled.")
    return redirect("/account/security")
