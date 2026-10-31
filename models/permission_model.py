from database.db import mysql


class Permission:

    @staticmethod
    def get_all_permissions():
        cur = mysql.connection.cursor()
        cur.execute("SELECT permission_key, description FROM permissions ORDER BY permission_key")
        data = cur.fetchall()
        cur.close()
        return data

    @staticmethod
    def get_matrix():
        """Returns {role: set(permission_key, ...)}"""
        cur = mysql.connection.cursor()
        cur.execute("SELECT role, permission_key FROM role_permissions")
        rows = cur.fetchall()
        cur.close()
        matrix = {}
        for role, key in rows:
            matrix.setdefault(role, set()).add(key)
        return matrix

    @staticmethod
    def has_permission(role, permission_key):
        if role in ("super_admin",):
            return True
        cur = mysql.connection.cursor()
        cur.execute("SELECT 1 FROM role_permissions WHERE role=%s AND permission_key=%s", (role, permission_key))
        found = cur.fetchone() is not None
        cur.close()
        return found

    @staticmethod
    def set_permission(role, permission_key, granted):
        cur = mysql.connection.cursor()
        if granted:
            cur.execute("INSERT IGNORE INTO role_permissions (role, permission_key) VALUES (%s,%s)",
                        (role, permission_key))
        else:
            cur.execute("DELETE FROM role_permissions WHERE role=%s AND permission_key=%s", (role, permission_key))
        mysql.connection.commit()
        cur.close()
