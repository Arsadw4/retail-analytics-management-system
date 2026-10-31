from datetime import date

from database.db import mysql
from database.errors import translate_integrity_error
import pymysql


class Salary:

    @staticmethod
    def generate(employee_id, salary_month, basic_salary, allowances, deductions):
        net = float(basic_salary) + float(allowances) - float(deductions)
        cur = mysql.connection.cursor()
        try:
            cur.execute("""
                INSERT INTO salary_records
                    (employee_id, salary_month, basic_salary, allowances, deductions, net_salary)
                VALUES (%s,%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE basic_salary=VALUES(basic_salary), allowances=VALUES(allowances),
                    deductions=VALUES(deductions), net_salary=VALUES(net_salary)
            """, (employee_id, salary_month, basic_salary, allowances, deductions, net))
            mysql.connection.commit()
        except pymysql.err.IntegrityError as e:
            mysql.connection.rollback()
            cur.close()
            translate_integrity_error(e)
        cur.close()

    @staticmethod
    def mark_paid(salary_id):
        cur = mysql.connection.cursor()
        cur.execute("UPDATE salary_records SET payment_status='paid', paid_date=%s WHERE salary_id=%s",
                    (date.today(), salary_id))
        mysql.connection.commit()
        cur.close()

    @staticmethod
    def get_for_month(month):
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT s.salary_id, e.employee_name, s.basic_salary, s.allowances,
                   s.deductions, s.net_salary, s.payment_status, s.paid_date
            FROM salary_records s JOIN employees e ON s.employee_id = e.employee_id
            WHERE s.salary_month=%s ORDER BY e.employee_name
        """, (month,))
        data = cur.fetchall()
        cur.close()
        return data

    @staticmethod
    def get_for_employee(employee_id):
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT salary_id, salary_month, basic_salary, allowances, deductions,
                   net_salary, payment_status, paid_date
            FROM salary_records WHERE employee_id=%s ORDER BY salary_month DESC
        """, (employee_id,))
        data = cur.fetchall()
        cur.close()
        return data
