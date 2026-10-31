import os
from datetime import date
from urllib.parse import urlsplit

from flask import Blueprint, render_template, request, redirect, session, flash, current_app

from models.employee_model import Employee
from models.hr_org_model import Department, Designation
from models.attendance_model import Attendance
from models.leave_model import Leave
from models.salary_model import Salary
from models.employee_performance_model import EmployeePerformance
from models.employee_document_model import EmployeeDocument
from database.errors import DatabaseError
from database.db import get_db_cursor
from core.rbac import role_required, permission_required
from core.audit import log_action
from core.profile import get_profile_photo_filename, get_profile_photo_version, save_profile_photo, remove_profile_photo
from core.export_utils import export_csv, export_excel, export_pdf

hr_bp = Blueprint("hr", __name__)


def _safe_local_referrer(fallback):
    referrer = request.referrer
    if referrer:
        parsed = urlsplit(referrer)
        if not parsed.scheme and not parsed.netloc and referrer.startswith("/") and not referrer.startswith("//"):
            return referrer
    return fallback


# ---------------------------------------------------------------
# Departments / Designations
# ---------------------------------------------------------------
@hr_bp.route("/admin/departments")
@role_required("admin", "manager", "hr")
def departments():
    return render_template("admin/hr/departments.html",
                           departments=Department.get_all(), designations=Designation.get_all())


@hr_bp.route("/admin/departments/add", methods=["POST"])
@role_required("admin", "manager", "hr")
@permission_required("manage_departments")
def add_department():
    from models.permission_model import Permission
    if session.get("role") != "super_admin" and not Permission.has_permission(session.get("role"), "manage_departments"):
        return "Forbidden", 403
    try:
        Department.create(request.form["department_name"], request.form.get("description", ""))
    except DatabaseError as e:
        flash(str(e))
        return redirect("/admin/departments")
    log_action(session.get("user_id"), "DEPARTMENT_CREATED", request.form["department_name"])
    return redirect("/admin/departments")


@hr_bp.route("/admin/departments/delete/<int:id>", methods=["POST"])
@role_required("admin", "manager", "hr")
@permission_required("manage_departments")
def delete_department(id):
    from models.permission_model import Permission
    if session.get("role") != "super_admin" and not Permission.has_permission(session.get("role"), "manage_departments"):
        return "Forbidden", 403
    try:
        Department.delete(id)
    except DatabaseError as e:
        flash(str(e))
    return redirect("/admin/departments")


@hr_bp.route("/admin/designations/add", methods=["POST"])
@role_required("admin", "manager", "hr")
@permission_required("manage_departments")
def add_designation():
    from models.permission_model import Permission
    if session.get("role") != "super_admin" and not Permission.has_permission(session.get("role"), "manage_departments"):
        return "Forbidden", 403
    try:
        Designation.create(request.form["designation_name"], request.form.get("department_id") or None)
    except DatabaseError as e:
        flash(str(e))
    return redirect("/admin/departments")


@hr_bp.route("/admin/designations/delete/<int:id>", methods=["POST"])
@role_required("admin", "manager", "hr")
@permission_required("manage_departments")
def delete_designation(id):
    from models.permission_model import Permission
    if session.get("role") != "super_admin" and not Permission.has_permission(session.get("role"), "manage_departments"):
        return "Forbidden", 403
    try:
        Designation.delete(id)
    except DatabaseError as e:
        flash(str(e))
    return redirect("/admin/departments")


# ---------------------------------------------------------------
# Employee directory / full profile
# ---------------------------------------------------------------
@hr_bp.route("/admin/hr/employees")
@role_required("admin", "manager", "hr")
def employee_directory():
    employees = Employee.get_all_directory()
    from core.profile import get_profile_photo_filename, get_profile_photo_version
    profile_photos = {e[8]: get_profile_photo_filename(e[8]) for e in employees if e[8]}
    profile_photo_versions = {e[8]: get_profile_photo_version(e[8]) for e in employees if e[8]}
    return render_template("admin/hr/employee_directory.html", employees=employees, profile_photos=profile_photos, profile_photo_versions=profile_photo_versions)


@hr_bp.route("/admin/hr/employees/<int:employee_id>")
@role_required("admin", "manager", "hr")
def employee_full_profile(employee_id):
    employee = Employee.get_employee_full(employee_id)
    if employee is None:
        flash("Employee not found.")
        return redirect("/admin/hr/employees")

    departments = Department.get_all()
    designations = Designation.get_all()
    attendance = Attendance.get_for_employee(employee_id)
    leaves = Leave.get_for_employee(employee_id)
    salary_history = Salary.get_for_employee(employee_id)
    performance = EmployeePerformance.get_for_employee(employee_id)
    documents = EmployeeDocument.get_for_employee(employee_id)
    from core.profile import get_profile_photo_filename, get_profile_photo_version
    profile_photo = get_profile_photo_filename(employee[6]) if employee[6] else None
    profile_photo_version = get_profile_photo_version(employee[6]) if employee[6] else ""

    return render_template(
        "admin/hr/employee_profile.html",
        employee=employee, departments=departments, designations=designations,
        attendance=attendance, leaves=leaves, salary_history=salary_history,
        performance=performance, documents=documents,
        profile_photo=profile_photo, profile_photo_version=profile_photo_version
    )


@hr_bp.route("/admin/hr/employees/<int:employee_id>/photo", methods=["POST"])
@role_required("admin", "super_admin")
def employee_photo_update(employee_id):
    employee = Employee.get_employee_full(employee_id)
    if employee is None:
        flash("Employee not found.", "error")
        return redirect("/admin/hr/employees")
    if not employee[6]:
        flash("This employee does not have a linked login account, so no profile photo can be associated.", "error")
        return redirect(f"/admin/hr/employees/{employee_id}")
    try:
        filename = save_profile_photo(employee[6], request.files.get("profile_photo"))
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(f"/admin/hr/employees/{employee_id}")
    except OSError:
        current_app.logger.exception(
            "Employee profile photo update failed for employee_id=%s.", employee_id
        )
        flash("The profile photo could not be saved. Please try again.", "error")
        return redirect(f"/admin/hr/employees/{employee_id}")
    flash("Employee profile photo updated successfully.", "success")
    log_action(session.get("user_id"), "EMPLOYEE_PHOTO_UPDATED", f"employee_id={employee_id}")
    return redirect(f"/admin/hr/employees/{employee_id}")


@hr_bp.route("/admin/hr/employees/<int:employee_id>/photo/remove", methods=["POST"])
@role_required("admin", "super_admin")
def employee_photo_remove(employee_id):
    employee = Employee.get_employee_full(employee_id)
    if employee is None:
        flash("Employee not found.", "error")
        return redirect("/admin/hr/employees")
    if employee[6]:
        remove_profile_photo(employee[6])
    flash("Employee profile photo removed.", "success")
    log_action(session.get("user_id"), "EMPLOYEE_PHOTO_REMOVED", f"employee_id={employee_id}")
    return redirect(f"/admin/hr/employees/{employee_id}")


@hr_bp.route("/admin/hr/employees/<int:employee_id>/update-details", methods=["POST"])
@role_required("admin", "manager", "hr")
def update_employee_hr_details(employee_id):
    Employee.update_hr_details(
        employee_id,
        request.form.get("department_id") or None,
        request.form.get("designation_id") or None,
        request.form.get("date_of_joining") or None
    )
    Employee.update_profile_details(
        employee_id,
        date_of_birth=request.form.get("date_of_birth"),
        gender=request.form.get("gender"),
        blood_group=request.form.get("blood_group"),
        father_name=request.form.get("father_name"),
        marital_status=request.form.get("marital_status"),
        nationality=request.form.get("nationality"),
        language=request.form.get("language"),
        alternate_phone=request.form.get("alternate_phone"),
        address=request.form.get("address"),
        city=request.form.get("city"),
        state=request.form.get("state"),
        pin_code=request.form.get("pin_code"),
    )
    log_action(session.get("user_id"), "EMPLOYEE_HR_DETAILS_UPDATED", f"employee_id={employee_id}")
    return redirect(f"/admin/hr/employees/{employee_id}")


@hr_bp.route("/admin/hr/employees/<int:employee_id>/id-card")
@role_required("admin", "manager", "hr")
def employee_id_card(employee_id):
    employee = Employee.get_employee_full(employee_id)
    if employee is None:
        flash("Employee not found.")
        return redirect("/admin/hr/employees")
    return render_template("admin/hr/id_card.html", employee=employee)


# ---------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------
@hr_bp.route("/admin/hr/attendance", methods=["GET", "POST"])
@role_required("admin", "manager", "hr")
def attendance_page():
    selected_date = request.args.get("date") or date.today().isoformat()

    if request.method == "POST":
        for key, value in request.form.items():
            if key.startswith("status_"):
                employee_id = int(key.replace("status_", ""))
                Attendance.mark(
                    employee_id, request.form.get("date", selected_date), value,
                    request.form.get(f"checkin_{employee_id}") or None,
                    request.form.get(f"checkout_{employee_id}") or None,
                    ""
                )
        log_action(session.get("user_id"), "ATTENDANCE_MARKED", f"date={selected_date}")
        return redirect(f"/admin/hr/attendance?date={selected_date}")

    data = Attendance.get_for_date(selected_date)
    return render_template("admin/hr/attendance.html", records=data, selected_date=selected_date)


@hr_bp.route("/admin/hr/attendance/summary")
@role_required("admin", "manager", "hr", "accountant")
def attendance_summary():
    month = request.args.get("month")
    data = Attendance.monthly_summary(month)
    return render_template("admin/hr/attendance_summary.html", rows=data, month=month)


# ---------------------------------------------------------------
# Leave
# ---------------------------------------------------------------
@hr_bp.route("/admin/hr/leaves")
@role_required("admin", "manager", "hr")
def leaves():
    status = request.args.get("status")
    return render_template("admin/hr/leaves.html", leaves=Leave.get_all(status), status=status)


@hr_bp.route("/admin/hr/leaves/request", methods=["GET", "POST"])
@role_required("admin", "manager", "hr", "employee", "cashier", "inventory_manager", "accountant")
def request_leave():
    current_role = session.get("role")
    if request.method == "POST":
        if current_role in ("admin", "manager", "hr"):
            employee_id = int(request.form["employee_id"])
        else:
            employee_id = Employee.get_employee_id_for_user(session.get("user_id"))
            if employee_id is None:
                flash("No employee record is linked to your account.")
                return redirect("/employee/profile")
        try:
            Leave.request(
                employee_id, request.form["leave_type"],
                request.form["start_date"], request.form["end_date"], request.form.get("reason", "")
            )
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect("/admin/hr/leaves/request")
        flash("Leave request submitted.")
        return redirect("/admin/hr/leaves" if current_role in ("admin", "manager", "hr") else "/admin/hr/leaves/request")

    employees = (Employee.get_all_employees() if current_role in ("admin", "manager", "hr")
                 else ([Employee.get_employee(employee_id)] if (employee_id := Employee.get_employee_id_for_user(session.get("user_id"))) else []))
    return render_template("admin/hr/request_leave.html", employees=employees)


@hr_bp.route("/admin/hr/leaves/<int:leave_id>/decide", methods=["POST"])
@role_required("admin", "manager", "hr")
@permission_required("approve_leave")
def decide_leave(leave_id):
    status = request.form.get("decision")
    if status not in ("approved", "rejected"):
        flash("Invalid decision.")
        return redirect("/admin/hr/leaves")

    Leave.set_status(leave_id, status, session.get("user_id"))
    log_action(session.get("user_id"), "LEAVE_DECISION", f"leave_id={leave_id} status={status}")
    return redirect("/admin/hr/leaves")


# ---------------------------------------------------------------
# Salary
# ---------------------------------------------------------------
@hr_bp.route("/admin/hr/salary", methods=["GET", "POST"])
@role_required("admin", "manager", "hr", "accountant")
def salary_page():
    month = request.args.get("month") or date.today().strftime("%Y-%m")

    if request.method == "POST":
        from models.permission_model import Permission
        if session.get("role") != "super_admin" and not Permission.has_permission(session.get("role"), "process_salary"):
            return "Forbidden", 403
        Salary.generate(
            int(request.form["employee_id"]), month,
            float(request.form["basic_salary"]), float(request.form.get("allowances") or 0),
            float(request.form.get("deductions") or 0)
        )
        log_action(session.get("user_id"), "SALARY_GENERATED",
                   f"employee_id={request.form['employee_id']} month={month}")
        return redirect(f"/admin/hr/salary?month={month}")

    records = Salary.get_for_month(month)
    employees = Employee.get_all_employees()
    return render_template("admin/hr/salary.html", records=records, employees=employees, month=month)


@hr_bp.route("/admin/hr/salary/<int:salary_id>/mark-paid", methods=["POST"])
@role_required("admin", "manager", "hr", "accountant")
@permission_required("process_salary")
def mark_salary_paid(salary_id):
    Salary.mark_paid(salary_id)
    log_action(session.get("user_id"), "SALARY_PAID", f"salary_id={salary_id}")
    return redirect(_safe_local_referrer("/admin/hr/salary"))


# ---------------------------------------------------------------
# Performance
# ---------------------------------------------------------------
@hr_bp.route("/admin/hr/employees/<int:employee_id>/review", methods=["POST"])
@role_required("admin", "manager", "hr")
def add_performance_review(employee_id):
    EmployeePerformance.add_review(
        employee_id, request.form["review_period"], float(request.form["rating"]),
        request.form.get("remarks", ""), session.get("user_id")
    )
    log_action(session.get("user_id"), "PERFORMANCE_REVIEW_ADDED", f"employee_id={employee_id}")
    return redirect(f"/admin/hr/employees/{employee_id}")


# ---------------------------------------------------------------
# Documents
# ---------------------------------------------------------------
def _allowed_doc(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in {"pdf", "png", "jpg", "jpeg"}


@hr_bp.route("/admin/hr/employees/<int:employee_id>/documents", methods=["POST"])
@role_required("admin", "manager", "hr")
def upload_document(employee_id):
    file = request.files.get("document")
    if not file or file.filename == "" or not _allowed_doc(file.filename):
        flash("Please upload a PDF, PNG, or JPG file.")
        return redirect(f"/admin/hr/employees/{employee_id}")

    import uuid
    ext = file.filename.rsplit(".", 1)[1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"
    docs_dir = os.path.join(current_app.static_folder, "uploads", "employee_docs")
    os.makedirs(docs_dir, exist_ok=True)
    file.save(os.path.join(docs_dir, filename))

    EmployeeDocument.add(employee_id, request.form.get("document_type", "Other"),
                         filename, request.form.get("notes", ""), session.get("user_id"))
    log_action(session.get("user_id"), "EMPLOYEE_DOCUMENT_UPLOADED", f"employee_id={employee_id}")
    return redirect(f"/admin/hr/employees/{employee_id}")


@hr_bp.route("/admin/hr/documents/<int:document_id>/delete", methods=["POST"])
@role_required("admin", "manager", "hr")
def delete_document(document_id):
    existing = None
    # Fetch the stored filename before deleting the DB row so the
    # filesystem object cannot become orphaned.
    with get_db_cursor(commit=False) as cur:
        cur.execute("SELECT file_name FROM employee_documents WHERE document_id=%s", (document_id,))
        row = cur.fetchone()
        existing = row[0] if row else None
    EmployeeDocument.delete(document_id)
    if existing:
        try:
            os.remove(os.path.join(current_app.static_folder, "uploads", "employee_docs", existing))
        except OSError:
            pass
    return redirect(_safe_local_referrer("/admin/hr/employees"))


# ---------------------------------------------------------------
# Reports
# ---------------------------------------------------------------
@hr_bp.route("/admin/hr/reports/employees")
@role_required("admin", "manager", "hr", "accountant")
def report_employees():
    return render_template("admin/hr/report_employees.html", employees=Employee.get_all_full())


@hr_bp.route("/admin/hr/reports/departments")
@role_required("admin", "manager", "hr", "accountant")
def report_departments():
    return render_template("admin/hr/report_departments.html", rows=Department.report())


_EMP_HEADERS = ["Employee ID", "Name", "Code", "Department", "Designation", "Phone", "Salary", "Date of Joining", "Date of Birth", "Gender", "Blood Group", "Father's Name", "Marital Status", "Nationality", "Language", "Alternate Phone", "Address", "City", "State", "PIN Code"]


@hr_bp.route("/admin/hr/reports/employees/export/<fmt>")
@role_required("admin", "manager", "hr", "accountant")
def export_employees(fmt):
    rows = [[e[0], e[1], e[2] or "-", e[3] or "-", e[4] or "-", e[5] or "-",
             float(e[6]) if e[6] else 0, str(e[7]) if e[7] else "-",
             str(e[8]) if e[8] else "-", e[9] or "-", e[10] or "-", e[11] or "-",
             e[12] or "-", e[13] or "-", e[14] or "-", e[15] or "-", e[16] or "-",
             e[17] or "-", e[18] or "-", e[19] or "-"] for e in Employee.get_all_full()]
    if fmt == "csv":
        return export_csv(_EMP_HEADERS, rows, "employees.csv")
    if fmt == "excel":
        return export_excel(_EMP_HEADERS, rows, "employees.xlsx", "Employees")
    return export_pdf(_EMP_HEADERS, rows, "employees.pdf", "Employee Report")


_ATT_HEADERS = ["Employee", "Month", "Present", "Absent", "On Leave", "Half Days"]


@hr_bp.route("/admin/hr/reports/attendance/export/<fmt>")
@role_required("admin", "manager", "hr", "accountant")
def export_attendance(fmt):
    rows = [[r[1], r[2], r[3], r[4], r[5], r[6]] for r in Attendance.monthly_summary()]
    if fmt == "csv":
        return export_csv(_ATT_HEADERS, rows, "attendance.csv")
    if fmt == "excel":
        return export_excel(_ATT_HEADERS, rows, "attendance.xlsx", "Attendance")
    return export_pdf(_ATT_HEADERS, rows, "attendance.pdf", "Attendance Report")


_SAL_HEADERS = ["Employee", "Basic", "Allowances", "Deductions", "Net Salary", "Status"]


@hr_bp.route("/admin/hr/reports/salary/export/<fmt>")
@role_required("admin", "manager", "hr", "accountant")
def export_salary(fmt):
    month = request.args.get("month") or date.today().strftime("%Y-%m")
    rows = [[r[1], float(r[2]), float(r[3]), float(r[4]), float(r[5]), r[6]] for r in Salary.get_for_month(month)]
    if fmt == "csv":
        return export_csv(_SAL_HEADERS, rows, f"salary_{month}.csv")
    if fmt == "excel":
        return export_excel(_SAL_HEADERS, rows, f"salary_{month}.xlsx", "Salary")
    return export_pdf(_SAL_HEADERS, rows, f"salary_{month}.pdf", f"Salary Report {month}")


_DEPT_HEADERS = ["Department", "Total Employees", "Total Monthly Salary"]


@hr_bp.route("/admin/hr/reports/departments/export/<fmt>")
@role_required("admin", "manager", "hr", "accountant")
def export_departments(fmt):
    rows = [[r[1], r[2], float(r[3])] for r in Department.report()]
    if fmt == "csv":
        return export_csv(_DEPT_HEADERS, rows, "departments.csv")
    if fmt == "excel":
        return export_excel(_DEPT_HEADERS, rows, "departments.xlsx", "Departments")
    return export_pdf(_DEPT_HEADERS, rows, "departments.pdf", "Department Report")
