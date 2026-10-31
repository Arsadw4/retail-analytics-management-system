from database.db import mysql
from database.errors import translate_integrity_error
import pymysql


class Category:

    @staticmethod
    def get_all_categories():

        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT
                category_id,
                category_name,
                created_at
            FROM categories
            ORDER BY category_id DESC
        """)

        categories = cur.fetchall()

        cur.close()

        return categories


    @staticmethod
    def add_category(category_name):

        cur = mysql.connection.cursor()

        cur.execute("""
            INSERT INTO categories
            (
                category_name
            )
            VALUES
            (
                %s
            )
        """, (category_name,))

        mysql.connection.commit()

        cur.close()


    @staticmethod
    def get_category_by_id(category_id):

        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT
                category_id,
                category_name
            FROM categories
            WHERE category_id=%s
        """, (category_id,))

        category = cur.fetchone()

        cur.close()

        return category


    @staticmethod
    def update_category(
        category_id,
        category_name
    ):

        cur = mysql.connection.cursor()

        cur.execute("""
            UPDATE categories
            SET category_name=%s
            WHERE category_id=%s
        """, (
            category_name,
            category_id
        ))

        mysql.connection.commit()

        cur.close()


    @staticmethod
    def delete_category(category_id):

        cur = mysql.connection.cursor()

        try:
            cur.execute("""
                DELETE FROM categories
                WHERE category_id=%s
            """, (category_id,))

            mysql.connection.commit()
        except pymysql.err.IntegrityError as e:
            mysql.connection.rollback()
            cur.close()
            translate_integrity_error(e)  # always raises

        cur.close()
