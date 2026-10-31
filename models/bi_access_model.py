"""
models/bi_access_model.py
Manages `bi_user_store_access` -- the mapping Power BI's Row-Level
Security role uses (via v_bi_user_store_access) to restrict a
store-scoped user to their own warehouse(s). See
database/powerbi/POWER_BI_SETUP_GUIDE.md for how this plugs into the
DAX RLS role. Purely a Flask-side admin convenience for populating
that mapping -- Power BI itself reads it directly from MySQL.
"""

from database.db import mysql
from database.errors import translate_integrity_error
import pymysql


class BIStoreAccess:

    @staticmethod
    def get_all():
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT a.access_id, u.full_name, u.email, w.warehouse_name, a.created_at
            FROM bi_user_store_access a
            JOIN users u ON a.user_id = u.user_id
            JOIN warehouses w ON a.warehouse_id = w.warehouse_id
            ORDER BY u.full_name
        """)
        data = cur.fetchall()
        cur.close()
        return data

    @staticmethod
    def grant(user_id, warehouse_id):
        cur = mysql.connection.cursor()
        try:
            cur.execute(
                "INSERT INTO bi_user_store_access (user_id, warehouse_id) VALUES (%s,%s)",
                (user_id, warehouse_id)
            )
            mysql.connection.commit()
        except pymysql.err.IntegrityError as e:
            mysql.connection.rollback()
            cur.close()
            translate_integrity_error(e)
        cur.close()

    @staticmethod
    def revoke(access_id):
        cur = mysql.connection.cursor()
        cur.execute("DELETE FROM bi_user_store_access WHERE access_id=%s", (access_id,))
        mysql.connection.commit()
        cur.close()
