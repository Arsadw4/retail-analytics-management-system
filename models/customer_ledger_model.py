"""
models/customer_ledger_model.py
Loyalty points, membership levels, wallet, and credit/due management
for customers. Kept as its own module (not appended into
customer_model.py) since it's a distinct concern (financial ledger)
from basic customer CRUD.
"""

from database.db import get_db_cursor, mysql

LOYALTY_EARN_RATE = 100   # 1 point per 100 spent
LOYALTY_REDEEM_VALUE = 1  # 1 point = 1 currency unit when redeemed to wallet

MEMBERSHIP_THRESHOLDS = [
    ("Platinum", 20000),
    ("Gold", 5000),
    ("Silver", 0),
]


class CustomerLedger:

    @staticmethod
    def _write_ledger(cur, customer_id, txn_type, amount, balance_after,
                       reference_type=None, reference_id=None, notes=None, created_by=None):
        cur.execute("""
            INSERT INTO customer_ledger
                (customer_id, transaction_type, amount, balance_after,
                 reference_type, reference_id, notes, created_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """, (customer_id, txn_type, amount, balance_after,
              reference_type, reference_id, notes, created_by))

    @staticmethod
    def get_ledger(customer_id):
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT ledger_id, transaction_type, amount, balance_after,
                   reference_type, notes, created_at
            FROM customer_ledger
            WHERE customer_id=%s
            ORDER BY created_at DESC
        """, (customer_id,))
        data = cur.fetchall()
        cur.close()
        return data

    @staticmethod
    def recalculate_membership(cur, customer_id):
        cur.execute("""
            SELECT COALESCE(SUM(total_amount),0) FROM sales
            WHERE customer_id=%s AND status='completed'
        """, (customer_id,))
        lifetime_spend = float(cur.fetchone()[0])

        new_level = "Silver"
        for level, threshold in MEMBERSHIP_THRESHOLDS:
            if lifetime_spend >= threshold:
                new_level = level
                break

        cur.execute("UPDATE customers SET membership_level=%s WHERE customer_id=%s",
                    (new_level, customer_id))
        return new_level

    @staticmethod
    def earn_loyalty_for_sale(customer_id, sale_amount, sale_id, performed_by=None):
        """Called (best-effort) right after a completed sale. Never
        raises -- a loyalty-earning failure should not roll back or
        break an already-completed sale."""
        if not customer_id:
            return
        try:
            with get_db_cursor() as cur:
                points_earned = int(float(sale_amount) // LOYALTY_EARN_RATE)
                if points_earned > 0:
                    cur.execute(
                        "UPDATE customers SET loyalty_points = loyalty_points + %s WHERE customer_id=%s",
                        (points_earned, customer_id)
                    )
                    cur.execute("SELECT loyalty_points FROM customers WHERE customer_id=%s", (customer_id,))
                    new_balance = cur.fetchone()[0]
                    CustomerLedger._write_ledger(
                        cur, customer_id, "loyalty_earned", points_earned, new_balance,
                        "sale", sale_id, f"Earned on sale #{sale_id}", performed_by
                    )
                CustomerLedger.recalculate_membership(cur, customer_id)
        except Exception:
            import logging
            logging.getLogger("app").exception("Failed to award loyalty points for sale %s", sale_id)

    @staticmethod
    def redeem_points(customer_id, points, performed_by=None):
        """Converts loyalty points to wallet balance at LOYALTY_REDEEM_VALUE."""
        with get_db_cursor() as cur:
            cur.execute("SELECT loyalty_points, wallet_balance FROM customers WHERE customer_id=%s FOR UPDATE",
                        (customer_id,))
            row = cur.fetchone()
            if row is None:
                return {"ok": False, "message": "Customer not found."}

            current_points, wallet_balance = row
            if points <= 0 or points > current_points:
                return {"ok": False, "message": "Invalid points amount."}

            credit_value = points * LOYALTY_REDEEM_VALUE
            new_points = current_points - points
            new_wallet = float(wallet_balance) + credit_value

            cur.execute("UPDATE customers SET loyalty_points=%s, wallet_balance=%s WHERE customer_id=%s",
                        (new_points, new_wallet, customer_id))

            CustomerLedger._write_ledger(cur, customer_id, "loyalty_redeemed", points, new_points,
                                          "redemption", None, "Redeemed to wallet", performed_by)
            CustomerLedger._write_ledger(cur, customer_id, "wallet_topup", credit_value, new_wallet,
                                          "redemption", None, "From loyalty redemption", performed_by)

            return {"ok": True, "message": f"Redeemed {points} points for {credit_value:.2f} wallet credit."}

    @staticmethod
    def wallet_topup(customer_id, amount, performed_by=None, notes="Manual top-up"):
        if amount <= 0:
            return {"ok": False, "message": "Amount must be positive."}

        with get_db_cursor() as cur:
            cur.execute("SELECT wallet_balance FROM customers WHERE customer_id=%s FOR UPDATE", (customer_id,))
            row = cur.fetchone()
            if row is None:
                return {"ok": False, "message": "Customer not found."}

            new_balance = float(row[0]) + amount
            cur.execute("UPDATE customers SET wallet_balance=%s WHERE customer_id=%s",
                        (new_balance, customer_id))
            CustomerLedger._write_ledger(cur, customer_id, "wallet_topup", amount, new_balance,
                                          "manual", None, notes, performed_by)
            return {"ok": True, "message": "Wallet topped up successfully."}

    @staticmethod
    def record_credit_sale(customer_id, amount, reference_notes, performed_by=None):
        if amount is None or float(amount) <= 0:
            return {"ok": False, "message": "Credit sale amount must be positive."}
        with get_db_cursor() as cur:
            cur.execute("SELECT credit_limit, credit_balance FROM customers WHERE customer_id=%s FOR UPDATE",
                        (customer_id,))
            row = cur.fetchone()
            if row is None:
                return {"ok": False, "message": "Customer not found."}

            credit_limit, credit_balance = float(row[0]), float(row[1])
            if credit_balance + amount > credit_limit:
                return {"ok": False,
                        "message": f"This exceeds the customer's credit limit "
                                   f"(limit {credit_limit:.2f}, current due {credit_balance:.2f})."}

            new_balance = credit_balance + amount
            cur.execute("UPDATE customers SET credit_balance=%s WHERE customer_id=%s",
                        (new_balance, customer_id))
            CustomerLedger._write_ledger(cur, customer_id, "credit_sale", amount, new_balance,
                                          "manual", None, reference_notes, performed_by)
            return {"ok": True, "message": "Credit sale recorded."}

    @staticmethod
    def record_credit_payment(customer_id, amount, performed_by=None, notes="Due payment received"):
        if amount is None or float(amount) <= 0:
            return {"ok": False, "message": "Payment amount must be positive."}
        with get_db_cursor() as cur:
            cur.execute("SELECT credit_balance FROM customers WHERE customer_id=%s FOR UPDATE", (customer_id,))
            row = cur.fetchone()
            if row is None:
                return {"ok": False, "message": "Customer not found."}

            new_balance = max(0.0, float(row[0]) - amount)
            cur.execute("UPDATE customers SET credit_balance=%s WHERE customer_id=%s",
                        (new_balance, customer_id))
            CustomerLedger._write_ledger(cur, customer_id, "credit_payment", amount, new_balance,
                                          "manual", None, notes, performed_by)
            return {"ok": True, "message": "Payment recorded."}
