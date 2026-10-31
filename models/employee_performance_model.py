from database.db import mysql


class EmployeePerformance:

    @staticmethod
    def add_review(employee_id, review_period, rating, remarks, reviewed_by):
        cur = mysql.connection.cursor()
        cur.execute("""
            INSERT INTO employee_performance (employee_id, review_period, rating, remarks, reviewed_by)
            VALUES (%s,%s,%s,%s,%s)
        """, (employee_id, review_period, rating, remarks, reviewed_by))
        mysql.connection.commit()
        cur.close()

    @staticmethod
    def get_for_employee(employee_id):
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT review_id, review_period, rating, remarks, created_at
            FROM employee_performance WHERE employee_id=%s ORDER BY created_at DESC
        """, (employee_id,))
        data = cur.fetchall()
        cur.close()
        return data
