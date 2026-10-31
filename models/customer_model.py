from database.db import mysql
from database.errors import translate_integrity_error
import pymysql


class Customer:

    @staticmethod
    def count_customers():
        cur = mysql.connection.cursor()
        cur.execute("SELECT COUNT(*) FROM customers")
        count = cur.fetchone()[0]
        cur.close()
        return count


    @staticmethod
    def dashboard_recent(limit=5, start_date=None, end_date=None):
        cur=mysql.connection.cursor()
        where=[]
        params=[]
        if start_date: where.append("created_at >= %s"); params.append(start_date)
        if end_date: where.append("created_at < DATE_ADD(%s, INTERVAL 1 DAY)"); params.append(end_date)
        params.append(int(limit))
        condition=('WHERE '+ ' AND '.join(where)) if where else ''
        cur.execute(f"""
            SELECT customer_name, COALESCE(phone,'—'), created_at
            FROM customers {condition}
            ORDER BY created_at DESC, customer_id DESC
            LIMIT %s
        """, tuple(params))
        rows=cur.fetchall()
        cur.close()
        return rows

    @staticmethod
    def get_all_customers():
        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT *
            FROM customers
            ORDER BY customer_id DESC
        """)

        data = cur.fetchall()
        cur.close()

        return data

    @staticmethod
    def add_customer(name, phone, email, address):

        cur = mysql.connection.cursor()

        cur.execute("""
            INSERT INTO customers
            (
                customer_name,
                phone,
                email,
                address
            )
            VALUES
            (%s, %s, %s, %s)
        """, (
            name,
            phone,
            email,
            address
        ))

        mysql.connection.commit()
        cur.close()

    @staticmethod
    def get_customer(customer_id):

        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT *
            FROM customers
            WHERE customer_id = %s
        """, (customer_id,))

        data = cur.fetchone()
        cur.close()

        return data

    @staticmethod
    def update_customer(customer_id, name, phone, email, address):

        cur = mysql.connection.cursor()

        cur.execute("""
            UPDATE customers
            SET
                customer_name = %s,
                phone = %s,
                email = %s,
                address = %s
            WHERE customer_id = %s
        """, (
            name,
            phone,
            email,
            address,
            customer_id
        ))

        mysql.connection.commit()
        cur.close()

    @staticmethod
    def delete_customer(customer_id):

        cur = mysql.connection.cursor()

        try:
            cur.execute("""
                DELETE FROM customers
                WHERE customer_id = %s
            """, (customer_id,))

            mysql.connection.commit()
        except pymysql.err.IntegrityError as e:
            mysql.connection.rollback()
            cur.close()
            translate_integrity_error(e)  # always raises

        cur.close()

    # ---- Phase 5: search/filter, analytics passthrough ----------

    @staticmethod
    def search(query=None, membership_level=None):
        cur = mysql.connection.cursor()
        sql = "SELECT * FROM customers WHERE 1=1"
        params = []
        if query:
            sql += " AND (customer_name LIKE %s OR phone LIKE %s OR email LIKE %s)"
            params += [f"%{query}%", f"%{query}%", f"%{query}%"]
        if membership_level:
            sql += " AND membership_level=%s"
            params.append(membership_level)
        sql += " ORDER BY customer_id DESC"
        cur.execute(sql, tuple(params))
        data = cur.fetchall()
        cur.close()
        return data

    @staticmethod
    def get_analytics(customer_id):
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM v_customer_analytics WHERE customer_id=%s", (customer_id,))
        data = cur.fetchone()
        cur.close()
        return data

    @staticmethod
    def get_all_analytics():
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM v_customer_analytics ORDER BY total_spent DESC")
        data = cur.fetchall()
        cur.close()
        return data
