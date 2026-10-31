"""Validate product form values before creating or updating a product."""

from decimal import Decimal, InvalidOperation

_MAX_PRICE = Decimal("99999999.99")
_MAX_STOCK = 2_147_483_647


def validate_product_form(form, category_ids=None):
    """Return normalized product values and validation errors."""
    product = {
        "category_id": None,
        "product_name": form.get("product_name", "").strip(),
        "purchase_price": None,
        "selling_price": None,
        "stock_quantity": None,
        "sku": form.get("sku", "").strip(),
    }
    errors = []

    try:
        product["category_id"] = int(form.get("category_id", ""))
        if (product["category_id"] <= 0
                or (category_ids is not None and product["category_id"] not in category_ids)):
            raise ValueError
    except (TypeError, ValueError):
        errors.append("Select a valid product category.")

    if not product["product_name"]:
        errors.append("Product name is required.")
    elif len(product["product_name"]) > 150:
        errors.append("Product name must be 150 characters or fewer.")

    if len(product["sku"]) > 64:
        errors.append("SKU must be 64 characters or fewer.")

    for field, label in (("purchase_price", "Purchase price"), ("selling_price", "Selling price")):
        try:
            amount = Decimal(form.get(field, ""))
            if (not amount.is_finite() or amount < 0 or amount > _MAX_PRICE
                    or amount.as_tuple().exponent < -2):
                raise InvalidOperation
            product[field] = amount
        except (InvalidOperation, TypeError, ValueError):
            errors.append(f"{label} must be a nonnegative amount with at most two decimal places.")

    try:
        product["stock_quantity"] = int(form.get("stock_quantity", ""))
        if not 0 <= product["stock_quantity"] <= _MAX_STOCK:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("Stock quantity must be a nonnegative whole number within the database limit.")

    return product, errors
