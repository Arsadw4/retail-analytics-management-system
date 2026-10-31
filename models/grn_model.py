from datetime import datetime

from database.db import get_db_cursor, mysql
from models.purchase_order_model import PurchaseOrder


class GRN:

    @staticmethod
    def get_all():
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT g.grn_id, g.grn_number, s.supplier_name, po.po_number,
                   g.received_date, g.total_amount, u.full_name, g.created_at
            FROM grn g
            JOIN suppliers s ON g.supplier_id = s.supplier_id
            LEFT JOIN purchase_orders po ON g.po_id = po.po_id
            LEFT JOIN users u ON g.received_by = u.user_id
            ORDER BY g.grn_id DESC
        """)
        data = cur.fetchall()
        cur.close()
        return data

    @staticmethod
    def create(supplier_id, po_id, received_date, notes, items, received_by, warehouse_id=None):
        """
        items: [{"product_id": int, "quantity": int, "unit_cost": float, "po_item_id": int|None}, ...]
        Increases each product's stock, logs a stock movement, updates
        the linked PO's received quantities/status (if any), and posts
        a 'purchase' entry to the supplier ledger increasing their
        outstanding balance (goods received on standard trade credit).
        """
        if not supplier_id or not received_by or not items:
            raise ValueError("Supplier, receiver and at least one GRN item are required.")

        normalized = []
        for item in items:
            try:
                pid = int(item["product_id"])
                qty = int(item["quantity"])
                unit_cost = float(item["unit_cost"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("Invalid GRN item.") from exc
            if pid <= 0 or qty <= 0 or unit_cost < 0:
                raise ValueError("Quantity must be positive and unit cost cannot be negative.")
            normalized.append({**item, "product_id": pid, "quantity": qty, "unit_cost": unit_cost})

        with get_db_cursor() as cur:
            cur.execute("SELECT supplier_id FROM suppliers WHERE supplier_id=%s", (supplier_id,))
            if cur.fetchone() is None:
                raise ValueError("Supplier not found.")

            po_item_ids = [i.get("po_item_id") for i in normalized if i.get("po_item_id")]
            if po_id:
                cur.execute("SELECT supplier_id, status FROM purchase_orders WHERE po_id=%s FOR UPDATE", (po_id,))
                po_row = cur.fetchone()
                if po_row is None:
                    raise ValueError("Purchase order not found.")
                if po_row[0] != supplier_id:
                    raise ValueError("Purchase order does not belong to the selected supplier.")
                if po_row[1] == "cancelled":
                    raise ValueError("Cancelled purchase orders cannot receive goods.")

            for item in normalized:
                cur.execute("SELECT product_id FROM products WHERE product_id=%s FOR UPDATE", (item["product_id"],))
                if cur.fetchone() is None:
                    raise ValueError(f"Product {item['product_id']} not found.")
                poi_id = item.get("po_item_id")
                if poi_id:
                    if not po_id:
                        raise ValueError("A purchase-order item requires a purchase order.")
                    cur.execute("""
                        SELECT product_id, quantity_ordered, quantity_received
                        FROM purchase_order_items
                        WHERE po_item_id=%s AND po_id=%s
                        FOR UPDATE
                    """, (poi_id, po_id))
                    poi = cur.fetchone()
                    if poi is None:
                        raise ValueError("Purchase-order item does not belong to the selected purchase order.")
                    if int(poi[0]) != int(item["product_id"]):
                        raise ValueError("GRN product does not match the selected purchase-order item.")
                    if int(item["quantity"]) > int(poi[1]) - int(poi[2]):
                        raise ValueError("Received quantity exceeds the remaining purchase-order quantity.")

            if warehouse_id:
                cur.execute("SELECT warehouse_id FROM warehouses WHERE warehouse_id=%s AND is_active=TRUE", (warehouse_id,))
                if cur.fetchone() is None:
                    raise ValueError("Selected warehouse is not active or does not exist.")

            total = sum(i["unit_cost"] * i["quantity"] for i in normalized)

            cur.execute("""
                INSERT INTO grn (po_id, supplier_id, received_date, total_amount, notes, received_by)
                VALUES (%s,%s,%s,%s,%s,%s)
            """, (po_id, supplier_id, received_date, total, notes, received_by))
            grn_id = cur.lastrowid

            grn_number = f"GRN-{datetime.now().year}-{grn_id:05d}"
            cur.execute("UPDATE grn SET grn_number=%s WHERE grn_id=%s", (grn_number, grn_id))

            for i in normalized:
                pid = int(i["product_id"])
                qty = int(i["quantity"])
                unit_cost = float(i["unit_cost"])
                po_item_id = i.get("po_item_id")

                cur.execute("""
                    INSERT INTO grn_items (grn_id, po_item_id, product_id, quantity_received, unit_cost)
                    VALUES (%s,%s,%s,%s,%s)
                """, (grn_id, po_item_id, pid, qty, unit_cost))

                cur.execute(
                    "UPDATE products SET stock_quantity = stock_quantity + %s WHERE product_id=%s",
                    (qty, pid)
                )

                StockMovement_reason = f"GRN {grn_number}"
                cur.execute("""
                    INSERT INTO stock_movements
                        (product_id, warehouse_id, movement_type, quantity, reason,
                         reference_type, reference_id, performed_by)
                    VALUES (%s,%s,'in',%s,%s,'grn',%s,%s)
                """, (pid, warehouse_id, qty, StockMovement_reason, grn_id, received_by))

                if po_item_id:
                    cur.execute("""
                        UPDATE purchase_order_items SET quantity_received = quantity_received + %s
                        WHERE po_item_id=%s
                    """, (qty, po_item_id))

            if po_id:
                PurchaseOrder.update_status_from_receipts(cur, po_id)

            cur.execute("SELECT outstanding_balance FROM suppliers WHERE supplier_id=%s FOR UPDATE",
                        (supplier_id,))
            row = cur.fetchone()
            new_balance = float(row[0]) + total if row else total
            cur.execute("UPDATE suppliers SET outstanding_balance=%s WHERE supplier_id=%s",
                        (new_balance, supplier_id))

            cur.execute("""
                INSERT INTO supplier_ledger
                    (supplier_id, transaction_type, amount, balance_after, reference_type, reference_id, notes, created_by)
                VALUES (%s,'purchase',%s,%s,'grn',%s,%s,%s)
            """, (supplier_id, total, new_balance, grn_id, f"Goods received: {grn_number}", received_by))

            return grn_id, grn_number

    @staticmethod
    def get_by_id(grn_id):
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT g.grn_id, g.grn_number, s.supplier_name, g.received_date, g.total_amount, g.notes
            FROM grn g JOIN suppliers s ON g.supplier_id = s.supplier_id WHERE g.grn_id=%s
        """, (grn_id,))
        grn = cur.fetchone()

        cur.execute("""
            SELECT gi.grn_item_id, p.product_name, gi.quantity_received, gi.unit_cost
            FROM grn_items gi JOIN products p ON gi.product_id = p.product_id
            WHERE gi.grn_id=%s
        """, (grn_id,))
        items = cur.fetchall()
        cur.close()
        return grn, items
