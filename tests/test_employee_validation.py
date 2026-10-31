import unittest
from decimal import Decimal

from core.employee_validation import validate_employee_form


def valid_employee_form(**overrides):
    data = {
        "name": "  Taylor Employee  ",
        "email": "  TAYLOR@example.com  ",
        "phone": "+1 (555) 123-4567",
        "designation": "Store Associate",
        "salary": "42000.50",
        "password": "ValidPass123!",
        "date_of_birth": "1995-04-12",
        "department_id": "7",
    }
    data.update(overrides)
    return data


class EmployeeValidationTests(unittest.TestCase):
    def test_valid_form_is_normalized_for_persistence(self):
        employee, errors = validate_employee_form(valid_employee_form(), {7})

        self.assertEqual(errors, [])
        self.assertEqual(employee["name"], "Taylor Employee")
        self.assertEqual(employee["email"], "taylor@example.com")
        self.assertEqual(employee["salary"], Decimal("42000.50"))
        self.assertEqual(employee["department_id"], 7)

    def test_missing_required_fields_return_errors_without_raising(self):
        employee, errors = validate_employee_form({})

        self.assertIsNone(employee["salary"])
        self.assertTrue(any("name is required" in error.lower() for error in errors))
        self.assertTrue(any("email is required" in error.lower() for error in errors))
        self.assertTrue(any("salary is required" in error.lower() for error in errors))
        self.assertTrue(any("password is required" in error.lower() for error in errors))

    def test_invalid_email_salary_date_and_department_are_rejected(self):
        _, errors = validate_employee_form(
            valid_employee_form(
                email="not-an-email",
                salary="NaN",
                date_of_birth="not-a-date",
                department_id="999",
            ),
            {7},
        )

        self.assertTrue(any("valid email" in error.lower() for error in errors))
        self.assertTrue(any("valid salary" in error.lower() for error in errors))
        self.assertTrue(any("valid date" in error.lower() for error in errors))
        self.assertTrue(any("department" in error.lower() for error in errors))

    def test_edit_validation_does_not_require_a_password(self):
        data = valid_employee_form()
        data.pop("password")

        _, errors = validate_employee_form(data, {7}, require_password=False)

        self.assertFalse(any("password" in error.lower() for error in errors))


if __name__ == "__main__":
    unittest.main()
