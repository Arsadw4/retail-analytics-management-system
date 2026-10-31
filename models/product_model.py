from database.db import mysql, get_db_cursor
from database.errors import translate_integrity_error
import pymysql


class Product:

    @staticmethod
    def get_all_products():

        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT
                p.product_id,
                c.category_name,
                p.product_name,
                p.purchase_price,
                p.selling_price,
                p.stock_quantity,
                p.product_image
            FROM products p
            LEFT JOIN categories c
            ON p.category_id = c.category_id
            ORDER BY p.product_id DESC
        """)

        products = cur.fetchall()

        cur.close()

        return products


    @staticmethod
    def dashboard_low_stock(limit=5):
        """Return the most urgent low-stock products from the real inventory view."""
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT p.product_name, COALESCE(p.sku,'—'), p.stock_quantity,
                   COALESCE(i.minimum_stock,0),
                   CASE WHEN p.stock_quantity=0 THEN 'Out' ELSE 'Low' END
            FROM products p
            LEFT JOIN inventory i ON i.product_id=p.product_id
            WHERE p.is_active=TRUE AND i.inventory_id IS NOT NULL
              AND p.stock_quantity <= i.minimum_stock
            ORDER BY p.stock_quantity ASC, p.product_name
            LIMIT %s
        """, (int(limit),))
        rows=cur.fetchall()
        cur.close()
        return rows

    @staticmethod
    def get_pos_catalog():
        """Return the POS catalog with SKU/barcode for scan and manual lookup.
        This is intentionally separate from get_all_products() so existing tuple
        contracts used by the rest of the application remain unchanged.
        """
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT product_id, category_id, product_name, sku, barcode,
                   purchase_price, selling_price, stock_quantity, product_image
            FROM products
            WHERE is_active=TRUE
            ORDER BY product_name ASC, product_id ASC
        """)
        rows = cur.fetchall()
        cur.close()
        return rows

    @staticmethod
    def get_product_by_id(product_id):

        cur = mysql.connection.cursor()

        cur.execute(
            "SELECT * FROM products WHERE product_id=%s",
            (product_id,)
        )

        product = cur.fetchone()

        cur.close()

        return product

    @staticmethod
    def create_product(
        category_id,
        product_name,
        purchase_price,
        selling_price,
        stock_quantity,
        product_image,
        performed_by=None,
        sku=None,
    ):
        if float(purchase_price) < 0 or float(selling_price) < 0 or int(stock_quantity) < 0:
            raise ValueError("Prices and stock quantity cannot be negative.")

        try:
            with get_db_cursor() as cur:
                cur.execute("""
                    INSERT INTO products
                        (category_id, product_name, purchase_price, selling_price,
                         stock_quantity, product_image)
                    VALUES (%s,%s,%s,%s,%s,%s)
                """, (
                    category_id, product_name, purchase_price, selling_price,
                    stock_quantity, product_image,
                ))

                new_id = cur.lastrowid
                resolved_sku = sku or f"SKU{new_id:08d}"
                barcode = f"890{new_id:09d}"
                cur.execute(
                    "UPDATE products SET sku=%s, barcode=%s WHERE product_id=%s",
                    (resolved_sku, barcode, new_id),
                )

                initial_stock = int(stock_quantity)
                if initial_stock > 0:
                    cur.execute("""
                        INSERT INTO stock_movements
                            (product_id, movement_type, quantity, reason, reference_type,
                             reference_id, performed_by)
                        VALUES (%s,'in',%s,%s,'product_create',%s,%s)
                    """, (new_id, initial_stock, 'Initial product stock', new_id, performed_by))
        except pymysql.err.IntegrityError as exc:
            translate_integrity_error(exc)
        return new_id

    @staticmethod
    def update_product(
        product_id,
        category_id,
        product_name,
        purchase_price,
        selling_price,
        stock_quantity,
        product_image,
        performed_by=None
    ):

        cur = mysql.connection.cursor()

        cur.execute("SELECT stock_quantity FROM products WHERE product_id=%s FOR UPDATE", (product_id,))
        current = cur.fetchone()
        if current is None:
            cur.close()
            return False
        current_stock = int(current[0])
        new_stock = int(stock_quantity)
        if new_stock < 0:
            cur.close()
            raise ValueError("Stock quantity cannot be negative.")

        cur.execute("""
            UPDATE products
            SET
                category_id=%s,
                product_name=%s,
                purchase_price=%s,
                selling_price=%s,
                stock_quantity=%s,
                product_image=%s
            WHERE product_id=%s
        """,
        (category_id, product_name, purchase_price, selling_price, new_stock, product_image, product_id))

        delta = new_stock - current_stock
        if delta:
            cur.execute("""
                INSERT INTO stock_movements
                    (product_id, movement_type, quantity, reason, reference_type, reference_id, performed_by)
                VALUES (%s,'adjustment',%s,%s,'product_edit',%s,%s)
            """, (product_id, abs(delta), 'Product stock adjustment', product_id, performed_by))

        mysql.connection.commit()

        cur.close()

    @staticmethod
    def delete_product(product_id):

        cur = mysql.connection.cursor()

        try:
            cur.execute(
                "DELETE FROM products WHERE product_id=%s",
                (product_id,)
            )

            mysql.connection.commit()
        except pymysql.err.IntegrityError as e:
            mysql.connection.rollback()
            cur.close()
            translate_integrity_error(e)  # always raises

        cur.close()

    @staticmethod
    def count_products():

        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT COUNT(*) FROM products
        """)

        count = cur.fetchone()[0]

        cur.close()

        return count
    

    @staticmethod
    def get_by_barcode(barcode):
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT product_id, product_name, sku, barcode,
                   purchase_price, selling_price, stock_quantity
            FROM products
            WHERE barcode=%s OR sku=%s
        """, (barcode, barcode))
        data = cur.fetchone()
        cur.close()
        return data

    @staticmethod
    def set_sku_barcode(product_id, sku, barcode):
        cur = mysql.connection.cursor()
        try:
            cur.execute(
                "UPDATE products SET sku=%s, barcode=%s WHERE product_id=%s",
                (sku, barcode, product_id)
            )
            mysql.connection.commit()
        except pymysql.err.IntegrityError as e:
            mysql.connection.rollback()
            cur.close()
            translate_integrity_error(e)
        cur.close()

    @staticmethod
    def auto_generate_codes_if_missing(product_id):
        """
        Phase 3: if a product was created without a SKU/barcode,
        generate deterministic ones from its product_id so every
        product is scannable. Called right after product creation.
        """
        sku = f"SKU{product_id:08d}"
        barcode = f"890{product_id:09d}"  # Code128-compatible numeric string
        Product.set_sku_barcode(product_id, sku, barcode)
        return sku, barcode
