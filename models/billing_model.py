from datetime import datetime

from database.db import get_db_cursor, mysql
from models.stock_movement_model import StockMovement
from models.coupon_model import Coupon


class Billing:

    @staticmethod
    def _get_company_state(cur):
        cur.execute("SELECT state FROM company_settings WHERE setting_id=1")
        row = cur.fetchone()
        return row[0] if row else "Same State"

    @staticmethod
    def create_bill(items, customer_id, user_id, payment_methods,
                     coupon_code=None, customer_state=None, warehouse_id=None):
        """
        items: [{"product_id": int, "quantity": int}, ...]
        payment_methods: [{"method": "cash"|"upi"|"card"|"wallet", "amount": float, "reference_no": str|None}, ...]

        Returns dict: {"ok": bool, "message": str, "sale_id": int|None, "invoice_number": str|None}

        Locks every product row (in a stable product_id order, to avoid
        deadlocks between two simultaneous multi-item bills) inside one
        transaction -- the same SELECT ... FOR UPDATE pattern Phase 2/3
        already established for single-item sales and stock in/out.
        """
        if not items:
            return {"ok": False, "message": "Cart is empty.", "sale_id": None, "invoice_number": None}

        quantities = {}
        for item in items:
            try:
                pid = int(item["product_id"])
                qty = int(item["quantity"])
            except (KeyError, TypeError, ValueError):
                return {"ok": False, "message": "Invalid cart item.", "sale_id": None, "invoice_number": None}
            if qty <= 0:
                return {"ok": False, "message": "Quantity must be greater than zero.", "sale_id": None, "invoice_number": None}
            quantities[pid] = quantities.get(pid, 0) + qty

        items = [{"product_id": pid, "quantity": qty} for pid, qty in quantities.items()]
        product_ids = sorted(quantities)

        allowed_methods = {"cash", "upi", "card", "wallet"}
        normalized_payments = []
        for payment in payment_methods or []:
            try:
                method = str(payment.get("method", "")).strip().lower()
                amount = float(payment.get("amount", 0))
            except (AttributeError, TypeError, ValueError):
                return {"ok": False, "message": "Invalid payment details.", "sale_id": None, "invoice_number": None}
            if method not in allowed_methods or amount <= 0:
                return {"ok": False, "message": "Invalid payment method or amount.", "sale_id": None, "invoice_number": None}
            normalized_payments.append({"method": method, "amount": amount, "reference_no": payment.get("reference_no")})
        payment_methods = normalized_payments

        with get_db_cursor() as cur:
            placeholders = ",".join(["%s"] * len(product_ids))
            cur.execute(f"""
                SELECT product_id, product_name, selling_price, purchase_price,
                       stock_quantity, gst_rate
                FROM products
                WHERE product_id IN ({placeholders})
                FOR UPDATE
            """, tuple(product_ids))

            products_by_id = {row[0]: row for row in cur.fetchall()}

            if len(products_by_id) != len(product_ids):
                return {"ok": False, "message": "One or more products were not found.",
                        "sale_id": None, "invoice_number": None}

            line_items = []
            subtotal = 0.0
            profit_total = 0.0

            for item in items:
                pid = int(item["product_id"])
                qty = int(item["quantity"])
                if qty <= 0:
                    return {"ok": False, "message": "Quantity must be greater than zero.",
                            "sale_id": None, "invoice_number": None}

                row = products_by_id[pid]
                _, name, selling_price, purchase_price, stock, gst_rate = row
                selling_price = float(selling_price)
                purchase_price = float(purchase_price)
                gst_rate = float(gst_rate)

                if qty > stock:
                    return {"ok": False,
                            "message": f"Insufficient stock for {name} (available: {stock}).",
                            "sale_id": None, "invoice_number": None}

                line_subtotal = selling_price * qty
                line_profit = (selling_price - purchase_price) * qty
                line_gst = line_subtotal * gst_rate / 100.0

                subtotal += line_subtotal
                profit_total += line_profit

                line_items.append({
                    "product_id": pid, "quantity": qty, "unit_price": selling_price,
                    "purchase_price": purchase_price,
                    "subtotal": line_subtotal, "gst_rate": gst_rate, "gst_amount": line_gst
                })

            # --- Coupon / discount ---
            discount_amount = 0.0
            coupon_id = None
            if coupon_code:
                ok, message, discount_amount, coupon_id = Coupon.validate(coupon_code, subtotal, cur=cur)
                if not ok:
                    return {"ok": False, "message": message, "sale_id": None, "invoice_number": None}

            discount_ratio = (discount_amount / subtotal) if subtotal > 0 else 0.0

            taxable_amount = 0.0
            total_gst = 0.0
            profit_total = 0.0
            for li in line_items:
                line_discount = li["subtotal"] * discount_ratio
                li["taxable_amount"] = li["subtotal"] - line_discount
                li["gst_amount"] = li["taxable_amount"] * li["gst_rate"] / 100.0
                taxable_amount += li["taxable_amount"]
                total_gst += li["gst_amount"]
                profit_total += li["taxable_amount"] - (li["purchase_price"] * li["quantity"])

            company_state = Billing._get_company_state(cur)
            same_state = (customer_state is None) or (customer_state.strip().lower() == company_state.strip().lower())

            if same_state:
                cgst = total_gst / 2.0
                sgst = total_gst / 2.0
                igst = 0.0
            else:
                cgst = 0.0
                sgst = 0.0
                igst = total_gst

            grand_total = taxable_amount + total_gst

            # --- Payment validation (supports split payments) ---
            total_paid = sum(float(p["amount"]) for p in payment_methods) if payment_methods else 0.0
            if round(total_paid, 2) != round(grand_total, 2):
                return {"ok": False,
                        "message": f"Payment total ({total_paid:.2f}) does not match bill total ({grand_total:.2f}).",
                        "sale_id": None, "invoice_number": None}

            wallet_amount = sum(float(p["amount"]) for p in payment_methods if p["method"] == "wallet")
            if wallet_amount > 0:
                if not customer_id:
                    return {"ok": False, "message": "A customer must be selected to pay by wallet.",
                            "sale_id": None, "invoice_number": None}
                cur.execute("SELECT wallet_balance FROM customers WHERE customer_id=%s FOR UPDATE",
                            (customer_id,))
                wrow = cur.fetchone()
                if wrow is None or float(wrow[0]) < wallet_amount:
                    available = float(wrow[0]) if wrow else 0.0
                    return {"ok": False,
                            "message": f"Insufficient wallet balance (available: {available:.2f}).",
                            "sale_id": None, "invoice_number": None}

            cur.execute("""
                INSERT INTO sales
                    (customer_id, user_id, total_amount, profit_amount, status,
                     taxable_amount, cgst_amount, sgst_amount, igst_amount,
                     discount_amount, coupon_code, customer_state)
                VALUES (%s,%s,%s,%s,'completed',%s,%s,%s,%s,%s,%s,%s)
            """, (customer_id, user_id, grand_total, profit_total,
                  taxable_amount, cgst, sgst, igst,
                  discount_amount, coupon_code, customer_state))

            sale_id = cur.lastrowid

            invoice_number = f"INV-{datetime.now().year}-{sale_id:06d}"
            cur.execute("UPDATE sales SET invoice_number=%s WHERE sale_id=%s", (invoice_number, sale_id))

            for li in line_items:
                cur.execute("""
                    INSERT INTO sale_items (sale_id, product_id, quantity, unit_price, subtotal)
                    VALUES (%s,%s,%s,%s,%s)
                """, (sale_id, li["product_id"], li["quantity"], li["unit_price"], li["subtotal"]))

                cur.execute("""
                    UPDATE products SET stock_quantity = stock_quantity - %s WHERE product_id=%s
                """, (li["quantity"], li["product_id"]))

                StockMovement.log_sale_movement(cur, li["product_id"], li["quantity"], sale_id, user_id)

            for p in payment_methods:
                cur.execute("""
                    INSERT INTO sale_payments (sale_id, payment_method, amount, reference_no)
                    VALUES (%s,%s,%s,%s)
                """, (sale_id, p["method"], p["amount"], p.get("reference_no")))

                if p["method"] == "wallet":
                    cur.execute(
                        "UPDATE customers SET wallet_balance = wallet_balance - %s WHERE customer_id=%s",
                        (p["amount"], customer_id)
                    )
                    cur.execute("SELECT wallet_balance FROM customers WHERE customer_id=%s", (customer_id,))
                    new_wallet_balance = cur.fetchone()[0]
                    cur.execute("""
                        INSERT INTO customer_ledger
                            (customer_id, transaction_type, amount, balance_after,
                             reference_type, reference_id, notes, created_by)
                        VALUES (%s,'wallet_debit',%s,%s,'sale',%s,%s,%s)
                    """, (customer_id, p["amount"], new_wallet_balance, sale_id,
                          f"Paid via wallet for invoice {invoice_number}", user_id))

            if coupon_id:
                Coupon.mark_used(cur, coupon_id)

            return {"ok": True, "message": "Bill created successfully.",
                    "sale_id": sale_id, "invoice_number": invoice_number}

    @staticmethod
    def preview_totals(items, coupon_code=None, customer_state=None):
        """Calculate checkout totals without writing to the database."""
        if not items:
            return {"ok": False, "message": "Cart is empty."}

        quantities = {}
        for item in items:
            try:
                pid = int(item["product_id"])
                qty = int(item["quantity"])
            except (KeyError, TypeError, ValueError):
                return {"ok": False, "message": "Invalid cart item."}
            if qty <= 0:
                return {"ok": False, "message": "Quantity must be greater than zero."}
            quantities[pid] = quantities.get(pid, 0) + qty

        with get_db_cursor() as cur:
            ids = sorted(quantities)
            placeholders = ",".join(["%s"] * len(ids))
            cur.execute(f"""
                SELECT product_id, product_name, selling_price, purchase_price,
                       stock_quantity, gst_rate
                FROM products WHERE product_id IN ({placeholders})
            """, tuple(ids))
            rows = {r[0]: r for r in cur.fetchall()}

            if len(rows) != len(ids):
                return {"ok": False, "message": "One or more products were not found."}

            subtotal = 0.0
            gst_by_line = []
            for pid, qty in quantities.items():
                row = rows[pid]
                price, stock, rate = float(row[2]), int(row[4]), float(row[5])
                if qty > stock:
                    return {"ok": False, "message": f"Insufficient stock for {row[1]} (available: {stock})."}
                line = price * qty
                subtotal += line
                gst_by_line.append((line, rate))

            discount = 0.0
            if coupon_code:
                ok, message, discount, _ = Coupon.validate(coupon_code, subtotal, cur=cur)
                if not ok:
                    return {"ok": False, "message": message}

            ratio = discount / subtotal if subtotal else 0.0
            taxable = sum(line * (1 - ratio) for line, _ in gst_by_line)
            gst = sum(line * (1 - ratio) * rate / 100 for line, rate in gst_by_line)
            company_state = Billing._get_company_state(cur)
            same_state = (customer_state is None or
                          customer_state.strip().lower() == company_state.strip().lower())
            cgst = gst / 2 if same_state else 0.0
            sgst = gst / 2 if same_state else 0.0
            igst = gst if not same_state else 0.0
            total = taxable + gst
            return {"ok": True, "subtotal": round(subtotal, 2),
                    "discount": round(discount, 2), "taxable": round(taxable, 2),
                    "cgst": round(cgst, 2), "sgst": round(sgst, 2),
                    "igst": round(igst, 2), "total": round(total, 2)}

    @staticmethod
    def get_invoice(sale_id):
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT s.sale_id, s.invoice_number, s.sale_date, s.total_amount, s.profit_amount,
                   s.status, s.taxable_amount, s.cgst_amount, s.sgst_amount, s.igst_amount,
                   s.discount_amount, s.coupon_code, s.customer_state,
                   c.customer_name, c.phone, c.email, c.address,
                   u.full_name
            FROM sales s
            LEFT JOIN customers c ON s.customer_id = c.customer_id
            LEFT JOIN users u ON s.user_id = u.user_id
            WHERE s.sale_id=%s
        """, (sale_id,))
        sale = cur.fetchone()

        cur.execute("""
            SELECT si.product_id, p.product_name, si.quantity, si.unit_price, si.subtotal, p.gst_rate, p.product_image, p.sku
            FROM sale_items si
            JOIN products p ON si.product_id = p.product_id
            WHERE si.sale_id=%s
        """, (sale_id,))
        items = cur.fetchall()

        cur.execute("""
            SELECT payment_method, amount, reference_no FROM sale_payments WHERE sale_id=%s
        """, (sale_id,))
        payments = cur.fetchall()

        cur.close()
        return sale, items, payments

    @staticmethod
    def find_by_invoice_number(invoice_number):
        cur = mysql.connection.cursor()
        cur.execute("SELECT sale_id FROM sales WHERE invoice_number=%s", (invoice_number,))
        row = cur.fetchone()
        cur.close()
        return row[0] if row else None

    @staticmethod
    def search_invoices(query=None, date_from=None, date_to=None, customer_id=None, limit=200):
        cur = mysql.connection.cursor()
        sql = """
            SELECT s.sale_id, s.invoice_number, s.sale_date, s.total_amount, s.status,
                   c.customer_name, u.full_name
            FROM sales s
            LEFT JOIN customers c ON s.customer_id = c.customer_id
            LEFT JOIN users u ON s.user_id = u.user_id
            WHERE 1=1
        """
        params = []
        if query:
            sql += " AND (s.invoice_number LIKE %s OR c.customer_name LIKE %s)"
            params += [f"%{query}%", f"%{query}%"]
        if date_from:
            sql += " AND DATE(s.sale_date) >= %s"
            params.append(date_from)
        if date_to:
            sql += " AND DATE(s.sale_date) <= %s"
            params.append(date_to)
        if customer_id:
            sql += " AND s.customer_id=%s"
            params.append(customer_id)

        sql += " ORDER BY s.sale_date DESC LIMIT %s"
        params.append(limit)

        cur.execute(sql, tuple(params))
        data = cur.fetchall()
        cur.close()
        return data

    @staticmethod
    def get_customer_billing_history(customer_id):
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT sale_id, invoice_number, sale_date, total_amount, status
            FROM sales
            WHERE customer_id=%s
            ORDER BY sale_date DESC
        """, (customer_id,))
        data = cur.fetchall()
        cur.close()
        return data

    @staticmethod
    def dashboard_summary():
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN DATE(sale_date)=CURDATE() THEN total_amount END),0),
                COALESCE(SUM(CASE WHEN YEARWEEK(sale_date,3)=YEARWEEK(CURDATE(),3) THEN total_amount END),0),
                COALESCE(SUM(CASE WHEN DATE_FORMAT(sale_date,'%%Y-%%m')=DATE_FORMAT(CURDATE(),'%%Y-%%m') THEN total_amount END),0),
                COUNT(CASE WHEN DATE(sale_date)=CURDATE() THEN 1 END),
                COALESCE(SUM(CASE WHEN DATE(sale_date)=CURDATE() THEN cgst_amount+sgst_amount+igst_amount END),0)
            FROM sales WHERE status='completed'
        """)
        row = cur.fetchone()
        cur.close()
        return {
            "today_revenue": row[0], "week_revenue": row[1], "month_revenue": row[2],
            "today_bills": row[3], "today_tax": row[4]
        }
