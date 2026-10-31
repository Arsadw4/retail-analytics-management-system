"""Database-backed profile data for users without an HR employee row.

Employee records remain the source of truth for linked employees. This table
provides the same profile/contact/quick-info fields for administrator and
other account types that intentionally do not have an employees row.
"""

from database.db import get_db_cursor


class UserProfile:
    @staticmethod
    def get(user_id):
        if not user_id:
            return None
        with get_db_cursor(commit=False) as cur:
            cur.execute("""
                SELECT user_id, date_of_birth, gender, blood_group, father_name,
                       marital_status, nationality, language, phone, designation, alternate_phone,
                       address, city, state, pin_code,
                       department_id, designation_id, date_of_joining
                FROM user_profiles
                WHERE user_id=%s
            """, (user_id,))
            return cur.fetchone()

    @staticmethod
    def ensure(user_id):
        """Create the 1:1 profile row if it does not exist, then return it."""
        if not user_id:
            return None
        with get_db_cursor() as cur:
            cur.execute(
                "INSERT IGNORE INTO user_profiles (user_id) VALUES (%s)",
                (user_id,),
            )
            cur.execute("""
                SELECT user_id, date_of_birth, gender, blood_group, father_name,
                       marital_status, nationality, language, phone, designation, alternate_phone,
                       address, city, state, pin_code,
                       department_id, designation_id, date_of_joining
                FROM user_profiles WHERE user_id=%s
            """, (user_id,))
            return cur.fetchone()

    @staticmethod
    def upsert(user_id, *, date_of_birth=None, gender=None, blood_group=None,
               father_name=None, marital_status=None, nationality=None, language=None,
               phone=None, designation=None, alternate_phone=None, address=None, city=None, state=None,
               pin_code=None, department_id=None, designation_id=None, date_of_joining=None):
        """Persist the complete profile/contact/quick-info payload."""
        with get_db_cursor() as cur:
            cur.execute("""
                INSERT INTO user_profiles
                    (user_id, date_of_birth, gender, blood_group, father_name,
                     marital_status, nationality, language, phone, designation, alternate_phone,
                     address, city, state, pin_code,
                     department_id, designation_id, date_of_joining)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                    date_of_birth=VALUES(date_of_birth), gender=VALUES(gender),
                    blood_group=VALUES(blood_group), father_name=VALUES(father_name),
                    marital_status=VALUES(marital_status), nationality=VALUES(nationality),
                    language=VALUES(language), phone=VALUES(phone),
                    designation=VALUES(designation), alternate_phone=VALUES(alternate_phone), address=VALUES(address),
                    city=VALUES(city), state=VALUES(state), pin_code=VALUES(pin_code),
                    department_id=VALUES(department_id), designation_id=VALUES(designation_id),
                    date_of_joining=VALUES(date_of_joining)
            """, (
                user_id, date_of_birth or None, gender or None, blood_group or None,
                father_name or None, marital_status or None, nationality or None,
                language or None, phone or None, designation or None, alternate_phone or None,
                address or None, city or None, state or None, pin_code or None,
                department_id or None, designation_id or None, date_of_joining or None,
            ))
