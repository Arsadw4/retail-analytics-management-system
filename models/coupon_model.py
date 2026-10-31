from datetime import date

from database.db import mysql
from database.errors import translate_integrity_error
import pymysql


class Coupon:

    @staticmethod
    def get_all():
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT coupon_id, code, discount_type, discount_value, min_purchase_amount,
                   valid_from, valid_until, usage_limit, times_used, is_active
            FROM coupons ORDER BY coupon_id DESC
        """)
        data = cur.fetchall()
        cur.close()
        return data

    @staticmethod
    def create(code, discount_type, discount_value, min_purchase_amount,
               valid_from, valid_until, usage_limit):
        cur = mysql.connection.cursor()
        try:
            cur.execute("""
                INSERT INTO coupons
                    (code, discount_type, discount_value, min_purchase_amount,
                     valid_from, valid_until, usage_limit)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
            """, (code.upper(), discount_type, discount_value, min_purchase_amount,
                  valid_from, valid_until, usage_limit))
            mysql.connection.commit()
        except pymysql.err.IntegrityError as e:
            mysql.connection.rollback()
            cur.close()
            translate_integrity_error(e)
        cur.close()

    @staticmethod
    def delete(coupon_id):
        cur = mysql.connection.cursor()
        cur.execute("DELETE FROM coupons WHERE coupon_id=%s", (coupon_id,))
        mysql.connection.commit()
        cur.close()

    @staticmethod
    def validate(code, purchase_amount, cur=None):
        """
        Returns (ok: bool, message: str, discount_amount: float, coupon_id|None).
        If `cur` is provided, validation runs on that cursor (so it can be
        called from inside Billing.create_bill's existing transaction);
        otherwise it opens its own read-only lookup.
        """
        owns_cursor = cur is None
        if owns_cursor:
            cur = mysql.connection.cursor()

        cur.execute("""
            SELECT coupon_id, discount_type, discount_value, min_purchase_amount,
                   valid_from, valid_until, usage_limit, times_used, is_active
            FROM coupons WHERE code=%s
        """, (code.upper(),))
        if not owns_cursor:
            cur.execute("""
                SELECT coupon_id, discount_type, discount_value, min_purchase_amount,
                       valid_from, valid_until, usage_limit, times_used, is_active
                FROM coupons WHERE code=%s FOR UPDATE
            """, (code.upper(),))
        row = cur.fetchone()

        if owns_cursor:
            cur.close()

        if row is None:
            return False, "Invalid coupon code.", 0.0, None

        (coupon_id, discount_type, discount_value, min_purchase,
         valid_from, valid_until, usage_limit, times_used, is_active) = row

        if not is_active:
            return False, "This coupon is no longer active.", 0.0, None

        today = date.today()
        if valid_from and today < valid_from:
            return False, "This coupon is not active yet.", 0.0, None
        if valid_until and today > valid_until:
            return False, "This coupon has expired.", 0.0, None
        if usage_limit is not None and times_used >= usage_limit:
            return False, "This coupon has reached its usage limit.", 0.0, None
        if purchase_amount < float(min_purchase):
            return False, f"Minimum purchase of {min_purchase} required for this coupon.", 0.0, None

        if discount_type == "flat":
            discount = float(discount_value)
        else:
            discount = purchase_amount * float(discount_value) / 100.0

        discount = min(discount, purchase_amount)
        return True, "Coupon applied.", discount, coupon_id

    @staticmethod
    def mark_used(cur, coupon_id):
        cur.execute("UPDATE coupons SET times_used = times_used + 1 WHERE coupon_id=%s", (coupon_id,))
