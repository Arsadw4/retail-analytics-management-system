"""
models/employee_model.py

Migrated to get_db_cursor() (see database/db.py) and to the new
employees.user_id foreign key added in
database/migrations/002_phase2_schema_redesign.sql.

Before: this model linked an `employees` row to its `users` login row
purely by matching the `email` column in application code -- there
was no foreign key. update_employee() only ever updated
employees.email, never users.email, so editing an employee's email
silently broke the link
delete_employee() then looked up
`DELETE FROM users WHERE email=<employees.email>`, which after such a
drift would delete the wrong account (or none at all). Both bugs are
now structurally impossible: the two rows are tied by user_id, not by
a string comparison that can go stale.
"""

from core.security import hash_password
from database.db import get_db_cursor
from database.errors import translate_integrity_error
import pymysql


class Employee:

    @staticmethod
    def count_employees():
        with get_db_cursor(commit=False) as cur:
            cur.execute("SELECT COUNT(*) FROM employees")
            return cur.fetchone()[0]

    @staticmethod
    def get_all_employees():
        with get_db_cursor(commit=False) as cur:
            cur.execute("""
                SELECT
                    employee_id, employee_name, email,
                    phone, designation, salary, created_at, user_id
                FROM employees
                ORDER BY employee_id DESC
            """)
            return cur.fetchall()

    @staticmethod
    def add_employee(name, email, phone, designation, salary, password,
                     date_of_birth=None, gender=None, blood_group=None, father_name=None,
                     marital_status=None, nationality=None, language=None, alternate_phone=None,
                     address=None, city=None, state=None, pin_code=None, department_id=None):
        """
        Creates both the `users` login row and the `employees` HR
        row in a single transaction (one get_db_cursor block = one
        commit/rollback unit), and links them via user_id. If either
        insert fails (e.g. the email is already taken), BOTH are
        rolled back -- previously these were two separate
        commits, so a failure partway through could leave an orphaned
        `employees` row with no matching login, or vice versa.
        """
        hashed_password = hash_password(password)

        with get_db_cursor() as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO users (full_name, email, password, role)
                    VALUES (%s, %s, %s, 'employee')
                    """,
                    (name, email, hashed_password),
                )
                user_id = cur.lastrowid

                cur.execute(
                    """
                    INSERT INTO employees
                        (user_id, employee_name, email, phone, designation, salary,
                         department_id, date_of_birth, gender, blood_group, father_name,
                         marital_status, nationality, language, alternate_phone, address,
                         city, state, pin_code)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        user_id, name, email, phone, designation, salary, department_id,
                        date_of_birth, gender, blood_group, father_name, marital_status,
                        nationality, language, alternate_phone, address, city, state, pin_code,
                    ),
                )
                employee_id = cur.lastrowid
                employee_code = f"EMP-{employee_id:05d}"
                cur.execute(
                    "UPDATE employees SET employee_code=%s WHERE employee_id=%s",
                    (employee_code, employee_id),
                )
            except pymysql.err.IntegrityError as e:
                translate_integrity_error(e)  # always raises

            return employee_id

    @staticmethod
    def get_employee_id_for_user(user_id):
        if not user_id:
            return None
        with get_db_cursor(commit=False) as cur:
            cur.execute("SELECT employee_id FROM employees WHERE user_id=%s", (user_id,))
            row = cur.fetchone()
            return row[0] if row else None

    @staticmethod
    def get_employee(employee_id):
        with get_db_cursor(commit=False) as cur:
            cur.execute(
                """
                SELECT
                    employee_id, employee_name, email,
                    phone, designation, salary, created_at, user_id,
                    date_of_birth, gender, blood_group, father_name, marital_status, nationality,
                    language, alternate_phone, address, city, state, pin_code
                FROM employees
                WHERE employee_id=%s
                """,
                (employee_id,),
            )
            return cur.fetchone()

    @staticmethod
    def update_employee(employee_id, name, email, phone, designation, salary):
        """
        Updates the HR record AND the linked login row's name/email
        together, in one transaction -- this is the direct fix for
        the drift bug described in the module docstring.
        """
        with get_db_cursor() as cur:
            cur.execute(
                """
                UPDATE employees
                SET employee_name=%s, email=%s, phone=%s, designation=%s, salary=%s
                WHERE employee_id=%s
                """,
                (name, email, phone, designation, salary, employee_id),
            )

            cur.execute(
                "SELECT user_id FROM employees WHERE employee_id=%s",
                (employee_id,),
            )
            row = cur.fetchone()
            user_id = row[0] if row else None

            if user_id:
                cur.execute(
                    "UPDATE users SET full_name=%s, email=%s WHERE user_id=%s",
                    (name, email, user_id),
                )

    @staticmethod
    def update_full_profile(employee_id, name, email, phone, designation, salary,
                            department_id=None, designation_id=None, date_of_joining=None,
                            date_of_birth=None, gender=None, blood_group=None, father_name=None,
                            marital_status=None, nationality=None, language=None, alternate_phone=None,
                            address=None, city=None, state=None, pin_code=None):
        """Atomically update the linked user and the complete employee profile."""
        try:
            with get_db_cursor() as cur:
                cur.execute(
                    """
                    UPDATE employees
                    SET employee_name=%s, email=%s, phone=%s, designation=%s, salary=%s,
                        department_id=%s, designation_id=%s, date_of_joining=%s,
                        date_of_birth=%s, gender=%s, blood_group=%s, father_name=%s,
                        marital_status=%s, nationality=%s, language=%s,
                        alternate_phone=%s, address=%s, city=%s, state=%s, pin_code=%s
                    WHERE employee_id=%s
                    """,
                    (
                        name, email, phone, designation, salary, department_id or None,
                        designation_id or None, date_of_joining or None, date_of_birth or None,
                        gender or None, blood_group or None, father_name or None,
                        marital_status or None, nationality or None, language or None,
                        alternate_phone or None, address or None, city or None, state or None,
                        pin_code or None, employee_id,
                    ),
                )
                cur.execute(
                    "SELECT user_id FROM employees WHERE employee_id=%s", (employee_id,)
                )
                row = cur.fetchone()
                if row and row[0]:
                    cur.execute(
                        "UPDATE users SET full_name=%s, email=%s WHERE user_id=%s",
                        (name, email, row[0]),
                    )
        except pymysql.err.IntegrityError as exc:
            translate_integrity_error(exc)

    @staticmethod
    def update_profile_details(employee_id, *, date_of_birth=None, gender=None, blood_group=None,
                               father_name=None, marital_status=None, nationality=None, language=None,
                               alternate_phone=None, address=None, city=None, state=None, pin_code=None):
        """Persist the extended personal/contact fields added for the HR profile."""
        with get_db_cursor() as cur:
            cur.execute("""
                UPDATE employees SET
                    date_of_birth=%s, gender=%s, blood_group=%s, father_name=%s,
                    marital_status=%s, nationality=%s, language=%s, alternate_phone=%s,
                    address=%s, city=%s, state=%s, pin_code=%s
                WHERE employee_id=%s
            """, (date_of_birth or None, gender or None, blood_group or None, father_name or None,
                  marital_status or None, nationality or None, language or None, alternate_phone or None,
                  address or None, city or None, state or None, pin_code or None, employee_id))

    @staticmethod
    def delete_employee(employee_id):
        """
        Deletes both the employee HR record and its linked `users`
        login row, matching the original behavior (removing an
        employee also revokes their login). The difference from the
        original code is HOW the linked user is found: by user_id
        (the new foreign key) instead of re-looking-up by email,
        which was fragile -- if the email had ever drifted between
        the two tables (see update_employee's old behavior, fixed
        above), the wrong account -- or none -- would be deleted.

        If this employee has existing sales, audit log entries, or
        other records referencing their user_id, MySQL will reject
        the user deletion with a foreign key violation -- this is
        correct behavior (it protects historical transaction data
        from being orphaned), so it's translated into a friendly
        ReferentialIntegrityError rather than allowed to crash the
        request. Deactivating the account instead of deleting it
        (via /admin/edit-user, setting status to inactive) is the
        recommended path once a user has transaction history.
        """
        with get_db_cursor() as cur:
            cur.execute(
                "SELECT user_id FROM employees WHERE employee_id=%s",
                (employee_id,),
            )
            row = cur.fetchone()
            user_id = row[0] if row else None

            cur.execute("DELETE FROM employees WHERE employee_id=%s", (employee_id,))

            if user_id:
                try:
                    cur.execute("DELETE FROM users WHERE user_id=%s", (user_id,))
                except pymysql.err.IntegrityError as e:
                    translate_integrity_error(e)  # always raises

    # ---- Phase 6: employee ID, department/designation, full profile ----

    @staticmethod
    def generate_employee_code(employee_id):
        code = f"EMP-{employee_id:05d}"
        with get_db_cursor() as cur:
            cur.execute("UPDATE employees SET employee_code=%s WHERE employee_id=%s", (code, employee_id))
        return code

    @staticmethod
    def update_hr_details(employee_id, department_id, designation_id, date_of_joining):
        with get_db_cursor() as cur:
            cur.execute("""
                UPDATE employees SET department_id=%s, designation_id=%s, date_of_joining=%s
                WHERE employee_id=%s
            """, (department_id or None, designation_id or None, date_of_joining or None, employee_id))

    @staticmethod
    def get_employee_full(employee_id):
        with get_db_cursor(commit=False) as cur:
            cur.execute("""
                SELECT e.employee_id, e.employee_name, e.email, e.phone, e.designation,
                       e.salary, e.user_id, e.employee_code, e.date_of_joining,
                       d.department_name, des.designation_name, e.department_id, e.designation_id,
                       u.role, e.date_of_birth, e.gender, e.blood_group, e.father_name,
                       e.marital_status, e.nationality, e.language, e.alternate_phone,
                       e.address, e.city, e.state, e.pin_code
                FROM employees e
                LEFT JOIN departments d ON e.department_id = d.department_id
                LEFT JOIN designations des ON e.designation_id = des.designation_id
                LEFT JOIN users u ON e.user_id = u.user_id
                WHERE e.employee_id=%s
            """, (employee_id,))
            return cur.fetchone()

    @staticmethod
    def get_all_directory():
        """Directory-only projection with contact/status fields; keeps the report projection stable."""
        with get_db_cursor(commit=False) as cur:
            cur.execute("""
                SELECT e.employee_id, e.employee_name, e.employee_code, d.department_name,
                       COALESCE(des.designation_name, e.designation), e.phone, e.email, u.status, e.user_id,
                       e.date_of_birth, e.gender, e.blood_group, e.father_name, e.marital_status,
                       e.nationality, e.language, e.alternate_phone, e.address, e.city, e.state, e.pin_code
                FROM employees e
                LEFT JOIN departments d ON e.department_id = d.department_id
                LEFT JOIN designations des ON e.designation_id = des.designation_id
                LEFT JOIN users u ON e.user_id = u.user_id
                ORDER BY e.employee_id DESC
            """)
            return cur.fetchall()

    @staticmethod
    def get_all_full():
        with get_db_cursor(commit=False) as cur:
            cur.execute("""
                SELECT e.employee_id, e.employee_name, e.employee_code, d.department_name,
                       des.designation_name, e.phone, e.salary, e.date_of_joining,
                       e.date_of_birth, e.gender, e.blood_group, e.father_name, e.marital_status,
                       e.nationality, e.language, e.alternate_phone, e.address, e.city, e.state, e.pin_code
                FROM employees e
                LEFT JOIN departments d ON e.department_id = d.department_id
                LEFT JOIN designations des ON e.designation_id = des.designation_id
                ORDER BY e.employee_id DESC
            """)
            return cur.fetchall()
