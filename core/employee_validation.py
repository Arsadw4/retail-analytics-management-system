"""Server-side validation for fields submitted by the employee form."""

import re
from datetime import date
from decimal import Decimal, InvalidOperation


_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_PATTERN = re.compile(r"^\+?[0-9()\s.-]{0,19}$")
_MAX_SALARY = Decimal("99999999.99")
_OPTIONAL_FIELD_LIMITS = {
    "gender": 30,
    "blood_group": 10,
    "father_name": 100,
    "marital_status": 30,
    "nationality": 60,
    "language": 100,
    "alternate_phone": 20,
    "address": 255,
    "city": 80,
    "state": 60,
    "pin_code": 10,
}


def is_valid_email(value):
    """Validate the shared email shape used by account and employee forms."""
    return isinstance(value, str) and len(value) <= 100 and bool(_EMAIL_PATTERN.fullmatch(value))


def validate_employee_form(form, department_ids=None, require_password=True):
    """Return normalized employee data and validation errors.

    ``department_ids`` is the set of valid department keys rendered in the
    form. Passing it lets the route reject forged or stale selections before
    they reach the database foreign key.
    """
    data = {
        "name": form.get("name", "").strip(),
        "email": form.get("email", "").strip().lower(),
        "phone": form.get("phone", "").strip(),
        "designation": form.get("designation", "").strip(),
        "salary": None,
        "password": form.get("password", ""),
        "date_of_birth": form.get("date_of_birth", "").strip() or None,
        "gender": form.get("gender", "").strip() or None,
        "blood_group": form.get("blood_group", "").strip() or None,
        "father_name": form.get("father_name", "").strip() or None,
        "marital_status": form.get("marital_status", "").strip() or None,
        "nationality": form.get("nationality", "").strip() or None,
        "language": form.get("language", "").strip() or None,
        "alternate_phone": form.get("alternate_phone", "").strip() or None,
        "address": form.get("address", "").strip() or None,
        "city": form.get("city", "").strip() or None,
        "state": form.get("state", "").strip() or None,
        "pin_code": form.get("pin_code", "").strip() or None,
        "department_id": None,
    }
    errors = []

    if not data["name"]:
        errors.append("Employee name is required.")
    elif len(data["name"]) > 100:
        errors.append("Employee name must be 100 characters or fewer.")

    if not data["email"]:
        errors.append("Email is required.")
    elif not is_valid_email(data["email"]):
        errors.append("Enter a valid email address of 100 characters or fewer.")

    if data["phone"]:
        if len(data["phone"]) > 20 or not _PHONE_PATTERN.fullmatch(data["phone"]):
            errors.append("Enter a valid phone number of 20 characters or fewer.")
        elif not any(character.isdigit() for character in data["phone"]):
            errors.append("Enter at least one digit in the phone number.")

    if len(data["designation"]) > 100:
        errors.append("Designation must be 100 characters or fewer.")

    raw_salary = form.get("salary", "").strip()
    if not raw_salary:
        errors.append("Salary is required.")
    else:
        try:
            salary = Decimal(raw_salary)
            if not salary.is_finite() or salary < 0 or salary > _MAX_SALARY:
                raise InvalidOperation
            if salary * 100 != (salary * 100).to_integral_value():
                errors.append("Salary can have no more than two decimal places.")
            else:
                data["salary"] = salary
        except (InvalidOperation, ValueError):
            errors.append("Enter a valid salary from 0 to 99,999,999.99.")

    if require_password and not data["password"]:
        errors.append("A login password is required.")

    if data["date_of_birth"]:
        try:
            date.fromisoformat(data["date_of_birth"])
        except ValueError:
            errors.append("Enter a valid date of birth.")

    raw_department_id = form.get("department_id", "").strip()
    if raw_department_id:
        try:
            department_id = int(raw_department_id)
        except ValueError:
            department_id = None
        if department_id is None or department_id <= 0:
            errors.append("Select a valid department.")
        elif department_ids is not None and department_id not in department_ids:
            errors.append("The selected department is no longer available.")
        else:
            data["department_id"] = department_id

    for field, limit in _OPTIONAL_FIELD_LIMITS.items():
        value = data[field]
        if value and len(value) > limit:
            label = field.replace("_", " ").capitalize()
            errors.append(f"{label} must be {limit} characters or fewer.")

    return data, errors
