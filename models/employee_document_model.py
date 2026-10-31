from database.db import mysql


class EmployeeDocument:

    @staticmethod
    def add(employee_id, document_type, file_name, notes, uploaded_by):
        cur = mysql.connection.cursor()
        cur.execute("""
            INSERT INTO employee_documents (employee_id, document_type, file_name, notes, uploaded_by)
            VALUES (%s,%s,%s,%s,%s)
        """, (employee_id, document_type, file_name, notes, uploaded_by))
        mysql.connection.commit()
        cur.close()

    @staticmethod
    def get_for_employee(employee_id):
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT document_id, document_type, file_name, notes, created_at
            FROM employee_documents WHERE employee_id=%s ORDER BY created_at DESC
        """, (employee_id,))
        data = cur.fetchall()
        cur.close()
        return data

    @staticmethod
    def delete(document_id):
        cur = mysql.connection.cursor()
        cur.execute("DELETE FROM employee_documents WHERE document_id=%s", (document_id,))
        mysql.connection.commit()
        cur.close()
