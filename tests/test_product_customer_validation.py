import unittest
from decimal import Decimal

from core.customer_validation import validate_customer_form
from core.product_validation import validate_product_form


class ProductValidationTests(unittest.TestCase):
    def test_normalizes_valid_product_and_checks_category(self):
        product, errors = validate_product_form(
            {
                "category_id": "1",
                "product_name": "  Tea  ",
                "purchase_price": "12.50",
                "selling_price": "20.00",
                "stock_quantity": "3",
                "sku": " TEA-001 ",
            },
            {1},
        )

        self.assertEqual(errors, [])
        self.assertEqual(product["product_name"], "Tea")
        self.assertEqual(product["purchase_price"], Decimal("12.50"))
        self.assertEqual(product["sku"], "TEA-001")

    def test_missing_and_out_of_range_product_fields_are_rejected(self):
        _, missing_errors = validate_product_form({})
        _, invalid_errors = validate_product_form(
            {
                "category_id": "999",
                "product_name": "Product",
                "purchase_price": "NaN",
                "selling_price": "100000000.00",
                "stock_quantity": "-1",
            },
            {1},
        )

        self.assertGreaterEqual(len(missing_errors), 4)
        self.assertTrue(any("category" in error.lower() for error in invalid_errors))
        self.assertTrue(any("purchase price" in error.lower() for error in invalid_errors))
        self.assertTrue(any("selling price" in error.lower() for error in invalid_errors))
        self.assertTrue(any("stock" in error.lower() for error in invalid_errors))


class CustomerValidationTests(unittest.TestCase):
    def test_normalizes_valid_customer_fields(self):
        customer, errors = validate_customer_form(
            {"name": "  Taylor Customer ", "email": " TAYLOR@example.com "}
        )

        self.assertEqual(errors, [])
        self.assertEqual(customer["name"], "Taylor Customer")
        self.assertEqual(customer["email"], "taylor@example.com")

    def test_missing_name_and_invalid_contact_values_are_rejected(self):
        _, errors = validate_customer_form(
            {"name": " ", "email": "not-an-email", "phone": "x" * 21}
        )

        self.assertEqual(len(errors), 3)


if __name__ == "__main__":
    unittest.main()
