from datetime import datetime

from database.db import mysql, get_db_cursor


class PurchaseOrder:

    @staticmethod
    def get_all():
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT po.po_id, po.po_number, s.supplier_name, po.status,
                   po.expected_date, po.total_amount, po.created_at
            FROM purchase_orders po
            JOIN suppliers s ON po.supplier_id = s.supplier_id
            ORDER BY po.po_id DESC
        """)
        data = cur.fetchall()
        cur.close()
        return data

    @staticmethod
    def get_by_supplier(supplier_id):
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT po_id, po_number, status, expected_date, total_amount, created_at
            FROM purchase_orders WHERE supplier_id=%s ORDER BY po_id DESC
        """, (supplier_id,))
        data = cur.fetchall()
        cur.close()
        return data

    @staticmethod
    def get_by_id(po_id):
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT po.po_id, po.po_number, po.supplier_id, s.supplier_name, po.status,
                   po.expected_date, po.total_amount, po.notes, po.created_at
            FROM purchase_orders po
            JOIN suppliers s ON po.supplier_id = s.supplier_id
            WHERE po.po_id=%s
        """, (po_id,))
        po = cur.fetchone()

        cur.execute("""
            SELECT poi.po_item_id, poi.product_id, p.product_name, poi.quantity_ordered,
                   poi.quantity_received, poi.unit_cost, poi.subtotal
            FROM purchase_order_items poi
            JOIN products p ON poi.product_id = p.product_id
            WHERE poi.po_id=%s
        """, (po_id,))
        items = cur.fetchall()
        cur.close()
        return po, items

    @staticmethod
    def create(supplier_id, expected_date, notes, items, created_by):
        """Create a purchase order atomically after validating all line items."""
        if not supplier_id or not created_by or not items:
            raise ValueError("Supplier, creator and at least one item are required.")

        normalized = []
        for item in items:
            try:
                pid = int(item["product_id"])
                qty = int(item["quantity"])
                unit_cost = float(item["unit_cost"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("Invalid purchase-order item.") from exc
            if pid <= 0 or qty <= 0 or unit_cost < 0:
                raise ValueError("Quantity must be positive and unit cost cannot be negative.")
            normalized.append({"product_id": pid, "quantity": qty, "unit_cost": unit_cost})

        with get_db_cursor() as cur:
            cur.execute("SELECT supplier_id FROM suppliers WHERE supplier_id=%s", (supplier_id,))
            if cur.fetchone() is None:
                raise ValueError("Supplier not found.")

            for item in normalized:
                cur.execute("SELECT product_id FROM products WHERE product_id=%s", (item["product_id"],))
                if cur.fetchone() is None:
                    raise ValueError(f"Product {item['product_id']} not found.")

            total = sum(i["unit_cost"] * i["quantity"] for i in normalized)

            cur.execute("""
                INSERT INTO purchase_orders (supplier_id, status, expected_date, total_amount, notes, created_by)
                VALUES (%s,'ordered',%s,%s,%s,%s)
            """, (supplier_id, expected_date, total, notes, created_by))
            po_id = cur.lastrowid

            po_number = f"PO-{datetime.now().year}-{po_id:05d}"
            cur.execute("UPDATE purchase_orders SET po_number=%s WHERE po_id=%s", (po_number, po_id))

            for i in normalized:
                subtotal = i["unit_cost"] * i["quantity"]
                cur.execute("""
                    INSERT INTO purchase_order_items (po_id, product_id, quantity_ordered, unit_cost, subtotal)
                    VALUES (%s,%s,%s,%s,%s)
                """, (po_id, i["product_id"], i["quantity"], i["unit_cost"], subtotal))

            return po_id, po_number

    @staticmethod
    def cancel(po_id):
        cur = mysql.connection.cursor()
        cur.execute("SELECT status FROM purchase_orders WHERE po_id=%s FOR UPDATE", (po_id,))
        row = cur.fetchone()
        if row is None:
            cur.close()
            return False
        if row[0] == "received":
            cur.close()
            return False
        cur.execute("UPDATE purchase_orders SET status='cancelled' WHERE po_id=%s", (po_id,))
        mysql.connection.commit()
        cur.close()
        return True

    @staticmethod
    def update_status_from_receipts(cur, po_id):
        cur.execute("""
            SELECT SUM(quantity_ordered), SUM(quantity_received) FROM purchase_order_items WHERE po_id=%s
        """, (po_id,))
        ordered, received = cur.fetchone()
        ordered = ordered or 0
        received = received or 0

        if received <= 0:
            status = "ordered"
        elif received < ordered:
            status = "partially_received"
        else:
            status = "received"

        cur.execute("UPDATE purchase_orders SET status=%s WHERE po_id=%s", (status, po_id))
