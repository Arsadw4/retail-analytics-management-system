from database.db import mysql
from database.errors import translate_integrity_error
import pymysql


class Attendance:

    @staticmethod
    def mark(employee_id, attendance_date, status, check_in, check_out, notes):
        cur = mysql.connection.cursor()
        try:
            cur.execute("""
                INSERT INTO attendance (employee_id, attendance_date, status, check_in, check_out, notes)
                VALUES (%s,%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE status=VALUES(status), check_in=VALUES(check_in),
                    check_out=VALUES(check_out), notes=VALUES(notes)
            """, (employee_id, attendance_date, status, check_in or None, check_out or None, notes))
            mysql.connection.commit()
        except pymysql.err.IntegrityError as e:
            mysql.connection.rollback()
            cur.close()
            translate_integrity_error(e)
        cur.close()

    @staticmethod
    def get_for_date(attendance_date):
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT e.employee_id, e.employee_name, a.status, a.check_in, a.check_out, a.notes
            FROM employees e
            LEFT JOIN attendance a ON a.employee_id = e.employee_id AND a.attendance_date=%s
            ORDER BY e.employee_name
        """, (attendance_date,))
        data = cur.fetchall()
        cur.close()
        return data

    @staticmethod
    def get_for_employee(employee_id, month=None):
        cur = mysql.connection.cursor()
        if month:
            cur.execute("""
                SELECT attendance_date, status, check_in, check_out, notes
                FROM attendance WHERE employee_id=%s AND DATE_FORMAT(attendance_date,'%%Y-%%m')=%s
                ORDER BY attendance_date DESC
            """, (employee_id, month))
        else:
            cur.execute("""
                SELECT attendance_date, status, check_in, check_out, notes
                FROM attendance WHERE employee_id=%s ORDER BY attendance_date DESC LIMIT 60
            """, (employee_id,))
        data = cur.fetchall()
        cur.close()
        return data

    @staticmethod
    def monthly_summary(month=None):
        cur = mysql.connection.cursor()
        if month:
            cur.execute("SELECT * FROM v_attendance_summary WHERE month=%s ORDER BY employee_name", (month,))
        else:
            cur.execute("SELECT * FROM v_attendance_summary ORDER BY month DESC, employee_name")
        data = cur.fetchall()
        cur.close()
        return data
