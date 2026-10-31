import os

from flask import Blueprint, render_template, request, redirect, session, flash, send_file, current_app
from werkzeug.utils import secure_filename

from models.backup_model import create_backup, restore_backup, list_backups, list_restores, verify_backup
from core.rbac import role_required
from core.audit import log_action

backup_bp = Blueprint("backup", __name__)


@backup_bp.route("/admin/system/backups")
@role_required("admin", "super_admin")
def backups():
    return render_template("admin/system/backups.html",
                           backups=list_backups(), restores=list_restores())


@backup_bp.route("/admin/system/backups/create", methods=["POST"])
@role_required("admin", "super_admin")
def create_backup_route():
    ok, message, path = create_backup(triggered_by=session.get("user_id"), backup_type="manual")
    flash(message)
    if ok:
        log_action(session.get("user_id"), "BACKUP_CREATED", os.path.basename(path) if path else "")
    return redirect("/admin/system/backups")


@backup_bp.route("/admin/system/backups/download/<filename>")
@role_required("admin", "super_admin")
def download_backup(filename):
    safe_name = secure_filename(filename)
    path = os.path.join(current_app.config.get("BACKUP_DIR", "backups"), safe_name)
    if not os.path.exists(path):
        flash("Backup file not found.")
        return redirect("/admin/system/backups")
    log_action(session.get("user_id"), "BACKUP_DOWNLOADED", safe_name)
    return send_file(path, as_attachment=True, download_name=safe_name)


@backup_bp.route("/admin/system/backups/verify/<filename>", methods=["POST"])
@role_required("admin", "super_admin")
def verify_backup_route(filename):
    safe_name = secure_filename(filename)
    path = os.path.join(current_app.config.get("BACKUP_DIR", "backups"), safe_name)
    ok, message = verify_backup(path)
    flash(("Verified: " if ok else "Verification failed: ") + message)
    return redirect("/admin/system/backups")


@backup_bp.route("/admin/system/restore", methods=["GET", "POST"])
@role_required("super_admin", "admin")
def restore():
    if request.method == "POST":
        confirmation = request.form.get("confirmation", "")
        if confirmation != "RESTORE":
            flash('You must type RESTORE exactly to confirm this irreversible action.')
            return redirect("/admin/system/restore")

        source = request.form.get("source")

        if source == "upload":
            file = request.files.get("backup_file")
            if not file or not file.filename.endswith(".sql"):
                flash("Please upload a .sql backup file.")
                return redirect("/admin/system/restore")

            safe_name = secure_filename(file.filename)
            upload_path = os.path.join(current_app.config.get("BACKUP_DIR", "backups"), f"upload_{safe_name}")
            file.save(upload_path)
            target_path = upload_path
        else:
            safe_name = secure_filename(request.form.get("existing_file", ""))
            target_path = os.path.join(current_app.config.get("BACKUP_DIR", "backups"), safe_name)
            if not os.path.exists(target_path):
                flash("Selected backup file not found.")
                return redirect("/admin/system/restore")

        ok, message = restore_backup(target_path, triggered_by=session.get("user_id"))
        flash(message)
        log_action(session.get("user_id"), "DATABASE_RESTORED" if ok else "DATABASE_RESTORE_FAILED",
                   os.path.basename(target_path))
        return redirect("/admin/system/backups")

    return render_template("admin/system/restore.html", backups=list_backups())
