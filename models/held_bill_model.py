from database.db import mysql


class HeldBill:

    @staticmethod
    def hold(cart_json, customer_id, user_id, note=""):
        cur = mysql.connection.cursor()
        cur.execute("""
            INSERT INTO held_bills (customer_id, cart_data, note, created_by)
            VALUES (%s,%s,%s,%s)
        """, (customer_id, cart_json, note, user_id))
        mysql.connection.commit()
        new_id = cur.lastrowid
        cur.close()
        return new_id

    @staticmethod
    def get_all():
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT h.hold_id, c.customer_name, h.note, u.full_name, h.created_at
            FROM held_bills h
            LEFT JOIN customers c ON h.customer_id = c.customer_id
            LEFT JOIN users u ON h.created_by = u.user_id
            ORDER BY h.created_at DESC
        """)
        data = cur.fetchall()
        cur.close()
        return data

    @staticmethod
    def get_cart(hold_id):
        cur = mysql.connection.cursor()
        cur.execute("SELECT cart_data, customer_id FROM held_bills WHERE hold_id=%s", (hold_id,))
        data = cur.fetchone()
        cur.close()
        return data

    @staticmethod
    def delete(hold_id):
        cur = mysql.connection.cursor()
        cur.execute("DELETE FROM held_bills WHERE hold_id=%s", (hold_id,))
        mysql.connection.commit()
        cur.close()
