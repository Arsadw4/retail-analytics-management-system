from database.db import mysql, get_db_cursor
from database.errors import translate_integrity_error
import pymysql


class Batch:

    @staticmethod
    def get_for_product(product_id):
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT batch_id, batch_number, quantity, manufacture_date,
                   expiry_date, warehouse_id
            FROM product_batches
            WHERE product_id=%s
            ORDER BY expiry_date IS NULL, expiry_date ASC
        """, (product_id,))
        data = cur.fetchall()
        cur.close()
        return data

    @staticmethod
    def get_all():
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT b.batch_id, p.product_name, b.batch_number, b.quantity,
                   b.manufacture_date, b.expiry_date, w.warehouse_name
            FROM product_batches b
            JOIN products p ON b.product_id = p.product_id
            LEFT JOIN warehouses w ON b.warehouse_id = w.warehouse_id
            ORDER BY b.expiry_date IS NULL, b.expiry_date ASC
        """)
        data = cur.fetchall()
        cur.close()
        return data

    @staticmethod
    def get_expiring(days=None):
        cur = mysql.connection.cursor()
        if days is not None:
            cur.execute("""
                SELECT batch_id, product_id, product_name, batch_number,
                       quantity, expiry_date, days_until_expiry, warehouse_name
                FROM v_expiring_batches
                WHERE days_until_expiry <= %s
            """, (days,))
        else:
            cur.execute("""
                SELECT batch_id, product_id, product_name, batch_number,
                       quantity, expiry_date, days_until_expiry, warehouse_name
                FROM v_expiring_batches
            """)
        data = cur.fetchall()
        cur.close()
        return data

    @staticmethod
    def add_batch(product_id, batch_number, quantity, manufacture_date, expiry_date, warehouse_id):
        """
        Adding a batch also increases the product's total stock
        (stock_in), and logs a stock movement referencing the new
        batch -- batches are a sub-ledger on top of the single
        authoritative stock_quantity from Phase 2, not a replacement
        for it.
        """
        with get_db_cursor() as cur:
            try:
                cur.execute("""
                    INSERT INTO product_batches
                        (product_id, warehouse_id, batch_number, quantity,
                         manufacture_date, expiry_date)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (product_id, warehouse_id, batch_number, quantity,
                      manufacture_date, expiry_date))
                batch_id = cur.lastrowid
            except pymysql.err.IntegrityError as e:
                translate_integrity_error(e)

            cur.execute(
                "UPDATE products SET stock_quantity = stock_quantity + %s WHERE product_id=%s",
                (quantity, product_id)
            )

            cur.execute("""
                INSERT INTO stock_movements
                    (product_id, warehouse_id, movement_type, quantity,
                     reason, reference_type, reference_id)
                VALUES (%s, %s, 'in', %s, %s, 'batch', %s)
            """, (product_id, warehouse_id, quantity,
                  f"Batch {batch_number} received", batch_id))

            return batch_id

    @staticmethod
    def delete_batch(batch_id, performed_by=None):
        with get_db_cursor() as cur:
            cur.execute("SELECT product_id, warehouse_id, quantity, batch_number FROM product_batches WHERE batch_id=%s FOR UPDATE", (batch_id,))
            row = cur.fetchone()
            if row is None:
                return False
            product_id, warehouse_id, quantity, batch_number = row
            cur.execute("SELECT stock_quantity FROM products WHERE product_id=%s FOR UPDATE", (product_id,))
            product = cur.fetchone()
            if product is None:
                return False
            if int(quantity) > int(product[0]):
                raise ValueError("Batch quantity exceeds current product stock; batch cannot be deleted safely.")
            if int(quantity) > 0:
                cur.execute("UPDATE products SET stock_quantity=stock_quantity-%s WHERE product_id=%s", (quantity, product_id))
                cur.execute("""
                    INSERT INTO stock_movements
                        (product_id, warehouse_id, movement_type, quantity, reason, reference_type, reference_id, performed_by)
                    VALUES (%s,%s,'out',%s,%s,'batch_delete',%s,%s)
                """, (product_id, warehouse_id, quantity, f"Deleted batch {batch_number}", batch_id, performed_by))
            cur.execute("DELETE FROM product_batches WHERE batch_id=%s", (batch_id,))
            return True
