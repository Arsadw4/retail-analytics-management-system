from database.db import mysql


class CompanySettings:

    @staticmethod
    def get():
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT setting_id, company_name, gst_number, address, state, phone, email
            FROM company_settings WHERE setting_id=1
        """)
        data = cur.fetchone()
        cur.close()
        return data

    @staticmethod
    def update(company_name, gst_number, address, state, phone, email):
        cur = mysql.connection.cursor()
        cur.execute("""
            UPDATE company_settings
            SET company_name=%s, gst_number=%s, address=%s, state=%s, phone=%s, email=%s
            WHERE setting_id=1
        """, (company_name, gst_number, address, state, phone, email))
        mysql.connection.commit()
        cur.close()
