"""Normalize and validate customer fields before database writes."""

from core.employee_validation import is_valid_email


def validate_customer_form(form):
    """Return normalized customer fields and user-facing validation errors."""
    customer = {
        "name": form.get("name", "").strip(),
        "phone": form.get("phone", "").strip(),
        "email": form.get("email", "").strip().lower(),
        "address": form.get("address", "").strip(),
    }
    errors = []

    if not customer["name"]:
        errors.append("Customer name is required.")
    elif len(customer["name"]) > 100:
        errors.append("Customer name must be 100 characters or fewer.")

    if len(customer["phone"]) > 20:
        errors.append("Phone number must be 20 characters or fewer.")

    if customer["email"] and not is_valid_email(customer["email"]):
        errors.append("Enter a valid email address of 100 characters or fewer.")

    return customer, errors
