"""
models/inventory_model.py

Rewritten against the Phase 2 schema redesign. `inventory` no longer
stores its own current_stock/purchase_price/selling_price/status --
those are read live from `v_inventory_full`, a view that joins
`inventory` with `products` (see
database/migrations/002_phase2_schema_redesign.sql for the full
reasoning). Column order in every SELECT below is deliberately kept
identical to the pre-Phase-2 shape (inventory_id, product_name,
current_stock, minimum_stock, maximum_stock, purchase_price,
selling_price, stock_value, status) so the existing templates --
which read these rows by position (item[0], item[1], ...) -- keep
working unchanged.
"""

from database.db import mysql
from database.errors import translate_integrity_error
import pymysql


class Inventory:

    @staticmethod
    def get_all_inventory():

        cursor = mysql.connection.cursor()

        cursor.execute("""
            SELECT
                inventory_id,
                product_name,
                current_stock,
                minimum_stock,
                maximum_stock,
                purchase_price,
                selling_price,
                stock_value,
                status
            FROM v_inventory_full
            ORDER BY inventory_id DESC
        """)

        data = cursor.fetchall()

        cursor.close()

        return data

    @staticmethod
    def get_low_stock():

        cursor = mysql.connection.cursor()

        cursor.execute("""
            SELECT
                inventory_id,
                product_name,
                current_stock,
                minimum_stock
            FROM v_inventory_full
            WHERE current_stock <= minimum_stock
            ORDER BY current_stock ASC
        """)

        data = cursor.fetchall()

        cursor.close()

        return data

    @staticmethod
    def total_inventory_value():

        cursor = mysql.connection.cursor()

        cursor.execute("""
            SELECT COALESCE(SUM(stock_value), 0)
            FROM v_inventory_full
        """)

        total = cursor.fetchone()[0]

        cursor.close()

        return total

    @staticmethod
    def get_inventory_by_id(inventory_id):

        cursor = mysql.connection.cursor()

        cursor.execute("""
            SELECT
                inventory_id,
                product_id,
                product_name,
                current_stock,
                purchase_price,
                selling_price,
                minimum_stock,
                maximum_stock
            FROM v_inventory_full
            WHERE inventory_id=%s
        """, (inventory_id,))

        data = cursor.fetchone()

        cursor.close()

        return data

    @staticmethod
    def create_inventory(
        product_id,
        minimum_stock,
        maximum_stock
    ):
        """
        No longer takes current_stock/purchase_price/selling_price --
        those belong to the product itself (set via Add/Edit Product)
        and are no longer duplicated here. Only the reorder thresholds
        are inventory-specific data.
        """

        cursor = mysql.connection.cursor()

        try:
            cursor.execute("""
                INSERT INTO inventory
                (
                    product_id,
                    minimum_stock,
                    maximum_stock
                )
                VALUES(%s,%s,%s)
            """,
            (
                product_id,
                minimum_stock,
                maximum_stock
            ))

            mysql.connection.commit()
        except pymysql.err.IntegrityError as e:
            mysql.connection.rollback()
            cursor.close()
            # Most likely cause: an inventory record already exists
            # for this product (product_id is now UNIQUE -- one
            # inventory row per product, matching the 1:1 relationship
            # the old schema never actually enforced).
            translate_integrity_error(e)  # always raises

        cursor.close()

    @staticmethod
    def delete_inventory(inventory_id):

        cursor = mysql.connection.cursor()

        cursor.execute(
            "DELETE FROM inventory WHERE inventory_id=%s",
            (inventory_id,)
        )

        mysql.connection.commit()

        cursor.close()

    @staticmethod
    def update_inventory(
        inventory_id,
        minimum_stock,
        maximum_stock
    ):

        cursor = mysql.connection.cursor()

        cursor.execute("""
            UPDATE inventory
            SET
                minimum_stock=%s,
                maximum_stock=%s
            WHERE inventory_id=%s
        """,
        (
            minimum_stock,
            maximum_stock,
            inventory_id
        ))

        mysql.connection.commit()

        cursor.close()

    @staticmethod
    def inventory_summary():

        cursor = mysql.connection.cursor()

        cursor.execute("""
            SELECT
                COUNT(*) as total_items,
                COALESCE(SUM(current_stock),0) as total_stock,
                COALESCE(SUM(stock_value),0) as total_value,
                COALESCE(SUM((selling_price-purchase_price)*current_stock),0) as profit_potential
            FROM v_inventory_full
        """)

        row = cursor.fetchone()

        cursor.close()

        return {
            "total_items": row[0],
            "total_stock": row[1],
            "total_value": row[2],
            # NOTE: templates read `summary.profit` (stock_report.html /
            # admin/reports/stock_report.html) -- this key was
            # previously named "profit_potential", which meant the
            # "Profit Potential" card always silently rendered blank.
            # Named `profit` here to match what's actually read.
            "profit": row[3]
        }

    @staticmethod
    def low_stock_count():

        cursor = mysql.connection.cursor()

        cursor.execute("""
            SELECT COUNT(*)
            FROM v_inventory_full
            WHERE current_stock <= minimum_stock
        """)

        count = cursor.fetchone()[0]

        cursor.close()

        return count

    @staticmethod
    def out_of_stock_count():

        cursor = mysql.connection.cursor()

        cursor.execute("""
            SELECT COUNT(*)
            FROM v_inventory_full
            WHERE current_stock = 0
        """)

        count = cursor.fetchone()[0]

        cursor.close()

        return count
