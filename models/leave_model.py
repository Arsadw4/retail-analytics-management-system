from database.db import get_db_cursor, mysql
from datetime import date


class Leave:

    @staticmethod
    def request(employee_id, leave_type, start_date, end_date, reason):
        allowed_types = {"sick", "casual", "earned", "unpaid"}
        if leave_type not in allowed_types:
            raise ValueError("Invalid leave type.")
        try:
            start = date.fromisoformat(start_date)
            end = date.fromisoformat(end_date)
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid leave dates.") from exc
        if end < start:
            raise ValueError("End date cannot be before start date.")
        cur = mysql.connection.cursor()
        cur.execute("""
            INSERT INTO leave_requests (employee_id, leave_type, start_date, end_date, reason)
            VALUES (%s,%s,%s,%s,%s)
        """, (employee_id, leave_type, start_date, end_date, reason))
        mysql.connection.commit()
        new_id = cur.lastrowid
        cur.close()
        return new_id

    @staticmethod
    def get_all(status=None):
        cur = mysql.connection.cursor()
        sql = """
            SELECT l.leave_id, e.employee_name, l.leave_type, l.start_date, l.end_date,
                   l.reason, l.status, u.full_name, l.created_at
            FROM leave_requests l
            JOIN employees e ON l.employee_id = e.employee_id
            LEFT JOIN users u ON l.approved_by = u.user_id
            WHERE 1=1
        """
        params = []
        if status:
            sql += " AND l.status=%s"
            params.append(status)
        sql += " ORDER BY l.created_at DESC"
        cur.execute(sql, tuple(params))
        data = cur.fetchall()
        cur.close()
        return data

    @staticmethod
    def get_for_employee(employee_id):
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT leave_id, leave_type, start_date, end_date, reason, status, created_at
            FROM leave_requests WHERE employee_id=%s ORDER BY created_at DESC
        """, (employee_id,))
        data = cur.fetchall()
        cur.close()
        return data

    @staticmethod
    def set_status(leave_id, status, approved_by):
        """When approved, also marks attendance rows as 'leave' for each day
        in the range (best-effort -- doesn't fail the approval if this part
        errors)."""
        from datetime import timedelta

        with get_db_cursor() as cur:
            cur.execute("UPDATE leave_requests SET status=%s, approved_by=%s WHERE leave_id=%s",
                        (status, approved_by, leave_id))

            if status == "approved":
                cur.execute("SELECT employee_id, start_date, end_date FROM leave_requests WHERE leave_id=%s",
                            (leave_id,))
                row = cur.fetchone()
                if row:
                    employee_id, start_date, end_date = row
                    day = start_date
                    while day <= end_date:
                        cur.execute("""
                            INSERT IGNORE INTO attendance (employee_id, attendance_date, status)
                            VALUES (%s, %s, 'leave')
                        """, (employee_id, day))
                        day += timedelta(days=1)
