from database.db import mysql
from database.errors import translate_integrity_error
import pymysql


class Warehouse:

    @staticmethod
    def get_all():
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT warehouse_id, warehouse_name, location,
                   contact_person, contact_phone, is_active, created_at
            FROM warehouses
            ORDER BY warehouse_id DESC
        """)
        data = cur.fetchall()
        cur.close()
        return data

    @staticmethod
    def get_active():
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT warehouse_id, warehouse_name, location
            FROM warehouses
            WHERE is_active = TRUE
            ORDER BY warehouse_name ASC
        """)
        data = cur.fetchall()
        cur.close()
        return data

    @staticmethod
    def get_by_id(warehouse_id):
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT warehouse_id, warehouse_name, location,
                   contact_person, contact_phone, is_active, created_at
            FROM warehouses
            WHERE warehouse_id=%s
        """, (warehouse_id,))
        data = cur.fetchone()
        cur.close()
        return data

    @staticmethod
    def create(name, location, contact_person, contact_phone):
        cur = mysql.connection.cursor()
        try:
            cur.execute("""
                INSERT INTO warehouses (warehouse_name, location, contact_person, contact_phone)
                VALUES (%s, %s, %s, %s)
            """, (name, location, contact_person, contact_phone))
            mysql.connection.commit()
            new_id = cur.lastrowid
        except pymysql.err.IntegrityError as e:
            mysql.connection.rollback()
            cur.close()
            translate_integrity_error(e)
        cur.close()
        return new_id

    @staticmethod
    def update(warehouse_id, name, location, contact_person, contact_phone, is_active):
        cur = mysql.connection.cursor()
        try:
            cur.execute("""
                UPDATE warehouses
                SET warehouse_name=%s, location=%s, contact_person=%s,
                    contact_phone=%s, is_active=%s
                WHERE warehouse_id=%s
            """, (name, location, contact_person, contact_phone, is_active, warehouse_id))
            mysql.connection.commit()
        except pymysql.err.IntegrityError as e:
            mysql.connection.rollback()
            cur.close()
            translate_integrity_error(e)
        cur.close()

    @staticmethod
    def delete(warehouse_id):
        cur = mysql.connection.cursor()
        try:
            cur.execute("DELETE FROM warehouses WHERE warehouse_id=%s", (warehouse_id,))
            mysql.connection.commit()
        except pymysql.err.IntegrityError as e:
            mysql.connection.rollback()
            cur.close()
            translate_integrity_error(e)
        cur.close()
