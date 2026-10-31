from flask import Blueprint, render_template, request

from models import monitoring_model as mon
from core.rbac import role_required
from core.perf_monitor import get_stats

monitoring_bp = Blueprint("monitoring", __name__)


@monitoring_bp.route("/admin/system/health")
@role_required("admin", "super_admin")
def health_dashboard():
    db_ok = mon.database_ping()
    return render_template(
        "admin/system/health.html",
        db_ok=db_ok,
        db_size_mb=mon.database_size_mb() if db_ok else 0,
        table_sizes=mon.table_sizes() if db_ok else [],
        storage=mon.storage_usage(),
        active_sessions=mon.active_session_count() if db_ok else 0,
        perf=get_stats(),
        error_count=mon.recent_error_count()
    )


@monitoring_bp.route("/admin/system/logs")
@role_required("admin", "super_admin")
def logs_viewer():
    level = request.args.get("level")
    lines = mon.recent_log_lines(n=200, level_filter=level)
    return render_template("admin/system/logs.html", lines=lines, level=level)


@monitoring_bp.route("/admin/system/performance")
@role_required("admin", "super_admin")
def performance_dashboard():
    return render_template("admin/system/performance.html", stats=get_stats())
