from database.db import mysql, get_db_cursor
from database.errors import translate_integrity_error
import pymysql


class Supplier:

    @staticmethod
    def get_all(query=None):
        cur = mysql.connection.cursor()
        sql = "SELECT * FROM suppliers WHERE 1=1"
        params = []
        if query:
            sql += " AND (supplier_name LIKE %s OR phone LIKE %s OR email LIKE %s)"
            params += [f"%{query}%", f"%{query}%", f"%{query}%"]
        sql += " ORDER BY supplier_id DESC"
        cur.execute(sql, tuple(params))
        data = cur.fetchall()
        cur.close()
        return data

    @staticmethod
    def get_by_id(supplier_id):
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM suppliers WHERE supplier_id=%s", (supplier_id,))
        data = cur.fetchone()
        cur.close()
        return data

    @staticmethod
    def create(name, contact_person, phone, email, address, gst_number):
        cur = mysql.connection.cursor()
        cur.execute("""
            INSERT INTO suppliers (supplier_name, contact_person, phone, email, address, gst_number)
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (name, contact_person, phone, email, address, gst_number))
        mysql.connection.commit()
        new_id = cur.lastrowid
        cur.close()
        return new_id

    @staticmethod
    def update(supplier_id, name, contact_person, phone, email, address, gst_number, is_active):
        cur = mysql.connection.cursor()
        cur.execute("""
            UPDATE suppliers
            SET supplier_name=%s, contact_person=%s, phone=%s, email=%s,
                address=%s, gst_number=%s, is_active=%s
            WHERE supplier_id=%s
        """, (name, contact_person, phone, email, address, gst_number, is_active, supplier_id))
        mysql.connection.commit()
        cur.close()

    @staticmethod
    def delete(supplier_id):
        cur = mysql.connection.cursor()
        try:
            cur.execute("DELETE FROM suppliers WHERE supplier_id=%s", (supplier_id,))
            mysql.connection.commit()
        except pymysql.err.IntegrityError as e:
            mysql.connection.rollback()
            cur.close()
            translate_integrity_error(e)
        cur.close()

    @staticmethod
    def get_ledger(supplier_id):
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT ledger_id, transaction_type, amount, balance_after, notes, created_at
            FROM supplier_ledger WHERE supplier_id=%s ORDER BY created_at DESC
        """, (supplier_id,))
        data = cur.fetchall()
        cur.close()
        return data

    @staticmethod
    def record_payment(supplier_id, amount, payment_method, reference_no, notes, performed_by):
        if amount is None or float(amount) <= 0:
            return {"ok": False, "message": "Payment amount must be positive."}
        with get_db_cursor() as cur:
            cur.execute("SELECT outstanding_balance FROM suppliers WHERE supplier_id=%s FOR UPDATE",
                        (supplier_id,))
            row = cur.fetchone()
            if row is None:
                return {"ok": False, "message": "Supplier not found."}

            new_balance = max(0.0, float(row[0]) - amount)
            cur.execute("UPDATE suppliers SET outstanding_balance=%s WHERE supplier_id=%s",
                        (new_balance, supplier_id))

            cur.execute("""
                INSERT INTO supplier_payments (supplier_id, amount, payment_method, reference_no, notes, created_by)
                VALUES (%s,%s,%s,%s,%s,%s)
            """, (supplier_id, amount, payment_method, reference_no, notes, performed_by))

            cur.execute("""
                INSERT INTO supplier_ledger
                    (supplier_id, transaction_type, amount, balance_after, reference_type, notes, created_by)
                VALUES (%s,'payment',%s,%s,'payment',%s,%s)
            """, (supplier_id, amount, new_balance, notes, performed_by))

            return {"ok": True, "message": "Payment recorded."}

    @staticmethod
    def get_performance():
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM v_supplier_performance ORDER BY total_purchase_value DESC")
        data = cur.fetchall()
        cur.close()
        return data

    @staticmethod
    def get_single_performance(supplier_id):
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM v_supplier_performance WHERE supplier_id=%s", (supplier_id,))
        data = cur.fetchone()
        cur.close()
        return data
