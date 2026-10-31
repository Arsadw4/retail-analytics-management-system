from database.db import get_db_cursor, mysql


class SalesReturn:

    @staticmethod
    def get_returnable_items(sale_id):
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT si.product_id, p.product_name, si.quantity, si.unit_price,
                   si.quantity - COALESCE((
                       SELECT SUM(sr.quantity) FROM sales_returns sr
                       WHERE sr.sale_id = si.sale_id AND sr.product_id = si.product_id
                   ), 0) AS returnable_qty
            FROM sale_items si
            JOIN products p ON si.product_id = p.product_id
            WHERE si.sale_id=%s
        """, (sale_id,))
        data = cur.fetchall()
        cur.close()
        return data

    @staticmethod
    def create_return(sale_id, items, reason, user_id):
        """
        items: [{"product_id": int, "quantity": int}, ...]
        Restocks products, logs a 'return' stock movement, records the
        return, and updates the sale's status to reflect a full or
        partial refund.
        """
        if not items:
            return {"ok": False, "message": "Select at least one item to return."}

        quantities = {}
        for item in items:
            try:
                pid = int(item["product_id"])
                qty = int(item["quantity"])
            except (KeyError, TypeError, ValueError):
                return {"ok": False, "message": "Invalid return item."}
            if qty <= 0:
                continue
            quantities[pid] = quantities.get(pid, 0) + qty
        if not quantities:
            return {"ok": False, "message": "Return quantity must be greater than zero."}

        with get_db_cursor() as cur:
            cur.execute("""
                SELECT status, total_amount, discount_amount, customer_state, taxable_amount, cgst_amount, sgst_amount, igst_amount, customer_id
                FROM sales WHERE sale_id=%s FOR UPDATE
            """, (sale_id,))
            sale_row = cur.fetchone()
            if sale_row is None:
                return {"ok": False, "message": "Sale not found."}
            if sale_row[0] not in ("completed", "partially_refunded"):
                return {"ok": False, "message": "This sale is not eligible for return."}

            _, _, sale_discount, _, _, _, _, _, customer_id = sale_row
            cur.execute("SELECT COALESCE(SUM(si.subtotal),0) FROM sale_items si WHERE si.sale_id=%s", (sale_id,))
            sale_gross = float(cur.fetchone()[0])
            discount_ratio = (float(sale_discount or 0) / sale_gross) if sale_gross > 0 else 0.0

            total_refund = 0.0

            for pid, qty in quantities.items():

                cur.execute("""
                    SELECT si.unit_price, si.quantity, p.gst_rate,
                           si.quantity - COALESCE((
                               SELECT SUM(sr.quantity) FROM sales_returns sr
                               WHERE sr.sale_id=%s AND sr.product_id=%s
                           ),0) AS returnable_qty
                    FROM sale_items si
                    JOIN products p ON p.product_id=si.product_id
                    WHERE si.sale_id=%s AND si.product_id=%s
                """, (sale_id, pid, sale_id, pid))
                row = cur.fetchone()

                if row is None:
                    return {"ok": False, "message": f"Product {pid} was not part of this sale."}

                unit_price, sold_qty, gst_rate, returnable_qty = row
                unit_price = float(unit_price)
                gst_rate = float(gst_rate or 0)

                if qty > returnable_qty:
                    return {"ok": False,
                            "message": f"Cannot return {qty} units -- only {returnable_qty} eligible."}

                gross_return = unit_price * qty
                taxable_return = gross_return * (1.0 - discount_ratio)
                tax_return = taxable_return * gst_rate / 100.0
                refund_amount = taxable_return + tax_return
                total_refund += refund_amount

                cur.execute("""
                    INSERT INTO sales_returns (sale_id, product_id, quantity, refund_amount, reason, refunded_by)
                    VALUES (%s,%s,%s,%s,%s,%s)
                """, (sale_id, pid, qty, refund_amount, reason, user_id))

                cur.execute("""
                    UPDATE products SET stock_quantity = stock_quantity + %s WHERE product_id=%s
                """, (qty, pid))

                cur.execute("""
                    INSERT INTO stock_movements
                        (product_id, movement_type, quantity, reason, reference_type, reference_id, performed_by)
                    VALUES (%s,'return',%s,%s,'sales_return',%s,%s)
                """, (pid, qty, reason or "Sales return", sale_id, user_id))

            cur.execute("""
                SELECT SUM(si.quantity) AS total_sold,
                       COALESCE((SELECT SUM(quantity) FROM sales_returns WHERE sale_id=%s),0) AS total_returned
                FROM sale_items si WHERE si.sale_id=%s
            """, (sale_id, sale_id))
            total_sold, total_returned = cur.fetchone()

            new_status = "refunded" if total_returned >= total_sold else "partially_refunded"
            cur.execute("UPDATE sales SET status=%s WHERE sale_id=%s", (new_status, sale_id))
            if customer_id:
                from models.customer_ledger_model import CustomerLedger
                CustomerLedger.recalculate_membership(cur, customer_id)

            return {"ok": True, "message": "Return processed successfully.",
                    "refund_amount": total_refund, "status": new_status}

    @staticmethod
    def get_all_returns():
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT r.return_id, s.invoice_number, p.product_name, r.quantity,
                   r.refund_amount, r.reason, u.full_name, r.created_at
            FROM sales_returns r
            JOIN sales s ON r.sale_id = s.sale_id
            JOIN products p ON r.product_id = p.product_id
            LEFT JOIN users u ON r.refunded_by = u.user_id
            ORDER BY r.created_at DESC
        """)
        data = cur.fetchall()
        cur.close()
        return data
