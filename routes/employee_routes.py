import logging

from flask import Blueprint, render_template, request, redirect, session, flash

from models.employee_model import Employee
from models.customer_model import Customer
from models.product_model import Product
from models.sales_model import Sale
from models.user_model import User
from models.user_profile_model import UserProfile
from models.hr_org_model import Department
from core.rbac import role_required
from core.security import verify_password, hash_password, validate_password_strength
from core.employee_validation import validate_employee_form
from core.customer_validation import validate_customer_form
from core.audit import log_action
from database.errors import DatabaseError
from core.profile import get_profile_photo_filename, get_profile_photo_version, save_profile_photo, remove_profile_photo

employee_bp = Blueprint("employee", __name__)
logger = logging.getLogger(__name__)


# -------------------------------
# HR: Employee records (admin/manager only)
# -------------------------------
@employee_bp.route("/admin/employees")
@role_required("admin", "manager")
def employees():
    # Canonical employee directory lives under the Phase 6 HR route.
    # Keep this legacy URL as a compatibility redirect so bookmarks/API
    # consumers are not broken while the old duplicate UI is retired.
    return redirect("/admin/hr/employees")


@employee_bp.route("/admin/add-employee", methods=["GET", "POST"])
@role_required("admin", "manager")
def add_employee():
    departments = Department.get_all()
    department_ids = {department[0] for department in departments}

    if request.method == "POST":
        employee_data, errors = validate_employee_form(request.form, department_ids)
        violations = validate_password_strength(employee_data["password"])
        errors.extend(violations)
        if errors:
            for error in errors:
                flash(error, "error")
            return render_template(
                "admin/employees/add_employee.html",
                departments=departments,
                employee_form=request.form,
            )

        try:
            new_employee_id = Employee.add_employee(
                employee_data["name"],
                employee_data["email"],
                employee_data["phone"],
                employee_data["designation"],
                employee_data["salary"],
                employee_data["password"],
                employee_data["date_of_birth"],
                employee_data["gender"],
                employee_data["blood_group"],
                employee_data["father_name"],
                employee_data["marital_status"],
                employee_data["nationality"],
                employee_data["language"],
                employee_data["alternate_phone"],
                employee_data["address"],
                employee_data["city"],
                employee_data["state"],
                employee_data["pin_code"],
                department_id=employee_data["department_id"],
            )
            initial_photo = request.files.get("profile_photo")
            if initial_photo and initial_photo.filename:
                try:
                    employee_full = Employee.get_employee_full(new_employee_id)
                    if employee_full and employee_full[6]:
                        save_profile_photo(employee_full[6], initial_photo)
                except ValueError as exc:
                    flash(f"Employee created, but profile photo was not saved: {exc}", "error")
                except Exception:
                    logger.exception("Profile photo could not be saved for employee_id=%s", new_employee_id)
                    flash("Employee created, but the profile photo could not be saved.", "error")
        except DatabaseError as e:
            flash(str(e), "error")
            return render_template(
                "admin/employees/add_employee.html",
                departments=departments,
                employee_form=request.form,
            )

        employee_code = f"EMP-{new_employee_id:05d}"
        log_action(session.get("user_id"), "EMPLOYEE_CREATED", f"employee_code={employee_code}")
        flash(f"Employee {employee_code} and the linked login account were created successfully.", "success")

        return redirect("/admin/hr/employees")

    return render_template(
        "admin/employees/add_employee.html",
        departments=departments,
        employee_form={},
    )


@employee_bp.route("/admin/edit-employee/<int:id>", methods=["GET", "POST"])
@role_required("admin", "manager")
def edit_employee(id):
    if request.method == "POST":
        employee_before = Employee.get_employee_full(id)
        if employee_before is None:
            flash("Employee not found.", "error")
            return redirect("/admin/employees")
        employee_data, errors = validate_employee_form(
            request.form,
            require_password=False,
        )
        if errors:
            for error in errors:
                flash(error, "error")
            return redirect(f"/admin/edit-employee/{id}")

        try:
            Employee.update_full_profile(
                id, employee_data["name"], employee_data["email"], employee_data["phone"],
                employee_data["designation"], employee_data["salary"],
                employee_before[11], employee_before[12], employee_before[8],
                employee_data["date_of_birth"], employee_data["gender"],
                employee_data["blood_group"], employee_data["father_name"],
                employee_data["marital_status"], employee_data["nationality"],
                employee_data["language"], employee_data["alternate_phone"],
                employee_data["address"], employee_data["city"],
                employee_data["state"], employee_data["pin_code"],
            )
        except DatabaseError as exc:
            flash(str(exc), "error")
            return redirect(f"/admin/edit-employee/{id}")

        employee_record = Employee.get_employee(id)
        photo = request.files.get("profile_photo")
        try:
            if employee_record and employee_record[7]:
                if photo and photo.filename:
                    save_profile_photo(employee_record[7], photo)
                elif request.form.get("remove_profile_photo") == "1":
                    remove_profile_photo(employee_record[7])
        except ValueError as exc:
            flash(f"Employee details saved, but profile photo was not updated: {exc}", "error")
        except OSError:
            logger.exception("Employee details saved but photo update failed for employee_id=%s.", id)
            flash("Employee details saved, but the profile photo could not be updated.", "error")

        log_action(session.get("user_id"), "EMPLOYEE_UPDATED", f"employee_id={id}")

        return redirect("/admin/employees")

    employee = Employee.get_employee(id)
    if employee is None:
        flash("Employee not found.")
        return redirect("/admin/employees")
    return render_template("admin/employees/edit_employee.html", employee=employee)


@employee_bp.route("/admin/delete-employee/<int:id>", methods=["POST"])
@role_required("admin", "manager")
def delete_employee(id):
    employee = Employee.get_employee(id)
    try:
        Employee.delete_employee(id)
    except DatabaseError as e:
        flash(str(e))
        return redirect("/admin/employees")

    if employee and employee[7]:
        remove_profile_photo(employee[7])

    log_action(session.get("user_id"), "EMPLOYEE_DELETED", f"employee_id={id}")
    return redirect("/admin/employees")


# -------------------------------
# Employee-facing workspace (any authenticated staff)
# -------------------------------
@employee_bp.route("/employee/dashboard")
@role_required("employee", "manager", "admin")
def employee_dashboard():
    total_products = Product.count_products()
    total_customers = Customer.count_customers()
    total_sales = Sale.total_sales_amount()

    return render_template(
        "employee/dashboard.html",
        total_products=total_products,
        total_customers=total_customers,
        total_sales=total_sales
    )


@employee_bp.route("/employee/customers")
@role_required("employee", "manager", "admin")
def employee_customers():
    customers = Customer.get_all_customers()
    return render_template("admin/customers/customers.html", customers=customers)


@employee_bp.route("/employee/add-customer", methods=["GET", "POST"])
@role_required("employee", "manager", "admin")
def employee_add_customer():
    if request.method == "POST":
        customer, errors = validate_customer_form(request.form)
        if errors:
            for error in errors:
                flash(error, "error")
            return redirect("/employee/add-customer")
        Customer.add_customer(
            customer["name"], customer["phone"],
            customer["email"], customer["address"]
        )
        log_action(session.get("user_id"), "CUSTOMER_CREATED", f"name={customer['name']}")
        return redirect("/employee/customers")

    return render_template("admin/customers/add_customer.html")


@employee_bp.route("/employee/edit-customer/<int:id>", methods=["GET", "POST"])
@role_required("employee", "manager", "admin")
def employee_edit_customer(id):
    customer_record = Customer.get_customer(id)
    if customer_record is None:
        flash("Customer not found.", "error")
        return redirect("/employee/customers")
    if request.method == "POST":
        customer, errors = validate_customer_form(request.form)
        if errors:
            for error in errors:
                flash(error, "error")
            return redirect(f"/employee/edit-customer/{id}")
        Customer.update_customer(
            id,
            customer["name"], customer["phone"],
            customer["email"], customer["address"]
        )
        log_action(session.get("user_id"), "CUSTOMER_UPDATED", f"customer_id={id}")
        return redirect("/employee/customers")

    return render_template("admin/customers/edit_customer.html", customer=customer_record)


@employee_bp.route("/employee/delete-customer/<int:id>", methods=["POST"])
@role_required("employee", "manager", "admin")
def employee_delete_customer(id):
    try:
        Customer.delete_customer(id)
    except DatabaseError as e:
        flash(str(e))
        return redirect("/employee/customers")

    log_action(session.get("user_id"), "CUSTOMER_DELETED", f"customer_id={id}")
    return redirect("/employee/customers")


@employee_bp.route("/employee/products")
@role_required("employee", "manager", "admin")
def employee_products():
    products = Product.get_all_products()
    return render_template("admin/products/products.html", products=products)


@employee_bp.route("/employee/sales")
@role_required("employee", "manager", "admin")
def employee_sales():
    sales = Sale.get_all_sales()
    return render_template("admin/sales/sales.html", sales=sales)


@employee_bp.route("/employee/create-sale", methods=["GET", "POST"])
@role_required("employee", "manager", "admin")
def create_sale():
    if request.method == "POST":
        success = Sale.create_sale(
            int(request.form["customer_id"]),
            session["user_id"],
            int(request.form["product_id"]),
            int(request.form["quantity"])
        )

        if success:
            log_action(session.get("user_id"), "SALE_CREATED",
                       f"product_id={request.form['product_id']} qty={request.form['quantity']}")
            return redirect("/employee/sales")

        flash("Insufficient Stock")

    customers = Sale.get_customers()
    products = Sale.get_products()

    return render_template(
        "admin/sales/create_sale.html",
        customers=customers,
        products=products
    )


@employee_bp.route("/employee/invoice/<int:sale_id>")
@role_required("employee", "manager", "admin")
def employee_invoice(sale_id):
    sale = Sale.get_sale_by_id(sale_id)
    if sale is None:
        flash("Sale not found.")
        return redirect("/employee/sales")
    return redirect(f"/admin/billing/invoice/{sale_id}")


@employee_bp.route("/employee/profile")
@role_required("employee", "manager", "admin", "cashier", "inventory_manager", "hr", "accountant", "super_admin")
def employee_profile():
    user_id = session["user_id"]
    user = User.get_user_by_id(user_id)
    if user is None:
        session.clear()
        return redirect("/login")

    employee_id = Employee.get_employee_id_for_user(user_id)
    employee = Employee.get_employee_full(employee_id) if employee_id else None
    user_profile = UserProfile.ensure(user_id)

    # Employee rows remain the source of truth for HR-linked users; the
    # user_profiles row supplies the same fields for administrators/accounts
    # that intentionally do not have an employees row.
    profile_data = _build_profile_data(user, employee, user_profile)
    photo = get_profile_photo_filename(user_id)
    session["profile_photo"] = photo or ""
    session["profile_photo_version"] = get_profile_photo_version(user_id)
    return render_template(
        "employee/profile.html",
        user=user, employee=employee, profile_photo=photo,
        profile_data=profile_data,
        can_edit=session.get("role") in ("admin", "super_admin"),
    )


def _build_profile_data(user, employee, user_profile):
    """Normalize employee/user-profile tuples for the profile templates."""
    ep = user_profile or [None] * 18
    # user_profiles: user_id, dob, gender, blood, father, marital, nationality,
    # language, phone, designation, alt_phone, address, city, state, pin,
    # department_id, designation_id, joining
    return {
        "employee_id": employee[0] if employee else None,
        "employee_code": employee[7] if employee else None,
        "department": employee[9] if employee else None,
        "designation": employee[10] if employee else ep[9],
        "join_date": employee[8] if employee else ep[17],
        "department_id": employee[11] if employee else ep[15],
        "designation_id": employee[12] if employee else ep[16],
        "salary": employee[5] if employee else None,
        "role": employee[13] if employee else user[4],
        "date_of_birth": employee[14] if employee else ep[1],
        "gender": employee[15] if employee else ep[2],
        "blood_group": employee[16] if employee else ep[3],
        "father_name": employee[17] if employee else ep[4],
        "marital_status": employee[18] if employee else ep[5],
        "nationality": employee[19] if employee else ep[6],
        "language": employee[20] if employee else ep[7],
        "phone": employee[3] if employee else ep[8],
        "alternate_phone": employee[21] if employee else ep[10],
        "address": employee[22] if employee else ep[11],
        "city": employee[23] if employee else ep[12],
        "state": employee[24] if employee else ep[13],
        "pin_code": employee[25] if employee else ep[14],
        "quick_id": employee[7] if employee and employee[7] else user[0],
    }


@employee_bp.route("/employee/profile/photo", methods=["POST"])
@role_required("admin", "super_admin")
def employee_profile_photo():
    """Change the logged-in administrator's profile photo."""
    user_id = session.get("user_id")
    if not user_id:
        return redirect("/login")
    try:
        save_profile_photo(user_id, request.files.get("profile_photo"))
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect("/employee/profile/edit")
    except OSError:
        logger.exception("Profile photo update failed for user_id=%s.", user_id)
        flash("The profile photo could not be saved. Please try again.", "error")
        return redirect("/employee/profile/edit")
    session["profile_photo_version"] = get_profile_photo_version(user_id)
    flash("Profile photo updated successfully.", "success")
    log_action(user_id, "PROFILE_PHOTO_UPDATED", "profile photo changed")
    return redirect("/employee/profile")


@employee_bp.route("/employee/profile/photo/remove", methods=["POST"])
@role_required("admin", "super_admin")
def employee_profile_photo_remove():
    """Remove the logged-in administrator's profile photo."""
    user_id = session.get("user_id")
    if not user_id:
        return redirect("/login")
    removed = remove_profile_photo(user_id)
    session["profile_photo"] = ""
    session["profile_photo_version"] = ""
    flash("Profile photo removed." if removed else "No profile photo was set.", "success")
    log_action(user_id, "PROFILE_PHOTO_REMOVED", "profile photo removed")
    return redirect("/employee/profile")


@employee_bp.route("/employee/profile/edit", methods=["GET", "POST"])
@role_required("admin", "super_admin")
def employee_profile_edit():
    user_id = session["user_id"]
    user = User.get_user_by_id(user_id)
    if user is None:
        session.clear()
        return redirect("/login")

    employee_id = Employee.get_employee_id_for_user(user_id)
    employee = Employee.get_employee_full(employee_id) if employee_id else None
    user_profile = UserProfile.ensure(user_id)

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        designation = request.form.get("designation", "").strip()
        department_id = request.form.get("department_id") or None
        designation_id = request.form.get("designation_id") or None
        date_of_joining = request.form.get("date_of_joining") or None
        profile_kwargs = dict(
            date_of_birth=request.form.get("date_of_birth") or None,
            gender=request.form.get("gender", "").strip() or None,
            blood_group=request.form.get("blood_group", "").strip() or None,
            father_name=request.form.get("father_name", "").strip() or None,
            marital_status=request.form.get("marital_status", "").strip() or None,
            nationality=request.form.get("nationality", "").strip() or None,
            language=request.form.get("language", "").strip() or None,
            phone=phone or None,
            designation=designation or None,
            alternate_phone=request.form.get("alternate_phone", "").strip() or None,
            address=request.form.get("address", "").strip() or None,
            city=request.form.get("city", "").strip() or None,
            state=request.form.get("state", "").strip() or None,
            pin_code=request.form.get("pin_code", "").strip() or None,
            department_id=department_id,
            designation_id=designation_id,
            date_of_joining=date_of_joining,
        )

        if not full_name or not email:
            flash("Full name and email are required.", "error")
            return redirect("/employee/profile/edit")

        try:
            if employee_id:
                Employee.update_full_profile(
                    employee_id, full_name, email, phone, designation, employee[5],
                    department_id, designation_id, date_of_joining,
                    profile_kwargs["date_of_birth"], profile_kwargs["gender"],
                    profile_kwargs["blood_group"], profile_kwargs["father_name"],
                    profile_kwargs["marital_status"], profile_kwargs["nationality"],
                    profile_kwargs["language"], profile_kwargs["alternate_phone"],
                    profile_kwargs["address"], profile_kwargs["city"],
                    profile_kwargs["state"], profile_kwargs["pin_code"],
                )
                UserProfile.upsert(user_id, **profile_kwargs)
            else:
                User.update_profile(user_id, full_name, email)
                UserProfile.upsert(user_id, **profile_kwargs)
        except DatabaseError as exc:
            flash(str(exc), "error")
            return redirect("/employee/profile/edit")

        session["name"] = full_name
        flash("Profile updated successfully.", "success")
        log_action(user_id, "PROFILE_UPDATED", "complete admin profile update")
        return redirect("/employee/profile")

    departments = []
    designations = []
    if employee_id or user_profile:
        from models.hr_org_model import Department, Designation
        departments = Department.get_all()
        designations = Designation.get_all()
    profile_data = _build_profile_data(user, employee, user_profile)
    profile_photo = get_profile_photo_filename(user_id)
    return render_template(
        "employee/profile_edit.html", user=user, employee=employee,
        profile_data=profile_data, departments=departments, designations=designations,
        profile_photo=profile_photo,
        profile_photo_version=get_profile_photo_version(user_id),
    )


@employee_bp.route("/employee/change-password", methods=["GET", "POST"])
@role_required("employee", "manager", "admin", "cashier", "inventory_manager", "hr", "accountant", "super_admin")
def employee_change_password():
    if request.method == "POST":
        old_password = request.form.get("old_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        user = User.get_user_by_id(session["user_id"])

        if user is None or not verify_password(user[3], old_password):
            flash("Current Password Incorrect")
            return redirect("/employee/change-password")

        if new_password != confirm_password:
            flash("Passwords Do Not Match")
            return redirect("/employee/change-password")

        violations = validate_password_strength(new_password)
        if violations:
            for v in violations:
                flash(v)
            return redirect("/employee/change-password")

        User.update_password(session["user_id"], hash_password(new_password))
        log_action(session.get("user_id"), "PASSWORD_CHANGED", "self-service change")

        session.clear()
        flash("Password Updated Successfully")
        return redirect("/login")

    return render_template("employee/change_password.html")


@employee_bp.route("/employee/my-sales")
@role_required("employee", "manager", "admin")
def employee_my_sales():
    sales = Sale.get_employee_sales(session["user_id"])
    return render_template("employee/sales/my_sales.html", sales=sales)
