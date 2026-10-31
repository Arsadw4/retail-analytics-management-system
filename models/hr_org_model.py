from database.db import mysql
from database.errors import translate_integrity_error
import pymysql


class Department:

    @staticmethod
    def get_all():
        cur = mysql.connection.cursor()
        cur.execute("SELECT department_id, department_name, description, created_at FROM departments ORDER BY department_name")
        data = cur.fetchall()
        cur.close()
        return data

    @staticmethod
    def create(name, description):
        cur = mysql.connection.cursor()
        try:
            cur.execute("INSERT INTO departments (department_name, description) VALUES (%s,%s)", (name, description))
            mysql.connection.commit()
        except pymysql.err.IntegrityError as e:
            mysql.connection.rollback()
            cur.close()
            translate_integrity_error(e)
        cur.close()

    @staticmethod
    def delete(department_id):
        cur = mysql.connection.cursor()
        try:
            cur.execute("DELETE FROM departments WHERE department_id=%s", (department_id,))
            mysql.connection.commit()
        except pymysql.err.IntegrityError as e:
            mysql.connection.rollback()
            cur.close()
            translate_integrity_error(e)
        cur.close()

    @staticmethod
    def report():
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM v_department_report ORDER BY department_name")
        data = cur.fetchall()
        cur.close()
        return data


class Designation:

    @staticmethod
    def get_all():
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT d.designation_id, d.designation_name, d.department_id, dep.department_name
            FROM designations d LEFT JOIN departments dep ON d.department_id = dep.department_id
            ORDER BY d.designation_name
        """)
        data = cur.fetchall()
        cur.close()
        return data

    @staticmethod
    def create(name, department_id):
        cur = mysql.connection.cursor()
        try:
            cur.execute("INSERT INTO designations (designation_name, department_id) VALUES (%s,%s)",
                        (name, department_id))
            mysql.connection.commit()
        except pymysql.err.IntegrityError as e:
            mysql.connection.rollback()
            cur.close()
            translate_integrity_error(e)
        cur.close()

    @staticmethod
    def delete(designation_id):
        cur = mysql.connection.cursor()
        try:
            cur.execute("DELETE FROM designations WHERE designation_id=%s", (designation_id,))
            mysql.connection.commit()
        except pymysql.err.IntegrityError as e:
            mysql.connection.rollback()
            cur.close()
            translate_integrity_error(e)
        cur.close()
