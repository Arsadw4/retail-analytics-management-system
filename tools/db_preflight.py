"""Database preflight validator for Enterprise Retail Management System.

Usage: python tools/db_preflight.py
Requires the project's normal environment/.env and does not modify data.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
import pymysql

load_dotenv(ROOT / ".env")

REQUIRED_TABLES = {
    "users", "categories", "products", "customers", "employees", "warehouses",
    "inventory", "stock_movements", "sales", "sale_items", "suppliers",
    "supplier_ledger", "supplier_payments", "purchase_orders", "purchase_order_items",
    "grn", "grn_items", "attendance", "leave_requests", "salary_records",
    "permissions", "role_permissions", "user_sessions", "user_profiles",
    "audit_logs", "backup_logs", "restore_logs",
}

REQUIRED_COLUMNS = {
    "users": {"user_id", "email", "password", "role", "status", "failed_login_attempts", "locked_until", "last_login_at", "password_changed_at", "mfa_enabled", "mfa_secret"},
    "products": {"product_id", "category_id", "product_name", "sku", "barcode", "purchase_price", "selling_price", "stock_quantity", "is_active", "gst_rate"},
    "customers": {"customer_id", "customer_name", "phone", "email", "loyalty_points", "membership_level", "wallet_balance", "credit_limit", "credit_balance"},
    "employees": {"employee_id", "user_id", "employee_name", "email", "department_id", "designation_id", "employee_code", "date_of_birth", "gender", "blood_group", "father_name", "marital_status", "nationality", "language", "alternate_phone", "address", "city", "state", "pin_code"},
    "user_profiles": {"user_id", "date_of_birth", "gender", "blood_group", "father_name", "marital_status", "nationality", "language", "phone", "designation", "alternate_phone", "address", "city", "state", "pin_code", "department_id", "designation_id", "date_of_joining"},
    "inventory": {"inventory_id", "product_id", "minimum_stock", "maximum_stock", "warehouse_id"},
    "sales": {"sale_id", "customer_id", "user_id", "total_amount", "profit_amount", "status", "invoice_number", "taxable_amount", "cgst_amount", "sgst_amount", "igst_amount", "discount_amount", "coupon_code", "sale_date"},
    "sale_items": {"item_id", "sale_id", "product_id", "quantity", "unit_price", "subtotal"},
    "suppliers": {"supplier_id", "supplier_name", "contact_person", "phone", "email", "address", "gst_number", "outstanding_balance", "is_active"},
}

def main() -> int:
    required_env = ["MYSQL_HOST", "MYSQL_PORT", "MYSQL_USER", "MYSQL_DB"]
    missing = [k for k in required_env if not os.getenv(k)]
    if missing:
        print("FAIL: missing environment variables: " + ", ".join(missing))
        return 2
    try:
        conn = pymysql.connect(
            host=os.getenv("MYSQL_HOST"), port=int(os.getenv("MYSQL_PORT", "3306")),
            user=os.getenv("MYSQL_USER"), password=os.getenv("MYSQL_PASSWORD", ""),
            database=os.getenv("MYSQL_DB"), charset="utf8mb4", connect_timeout=5,
        )
    except Exception as exc:
        print(f"FAIL: database connection: {exc}")
        return 3
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DATABASE()")
            db = cur.fetchone()[0]
            cur.execute("SHOW TABLES")
            tables = {row[0] for row in cur.fetchall()}
            missing_tables = sorted(REQUIRED_TABLES - tables)
            if missing_tables:
                print("FAIL: missing tables: " + ", ".join(missing_tables))
                return 4
            missing_cols = {}
            for table, required in REQUIRED_COLUMNS.items():
                cur.execute(f"SHOW COLUMNS FROM `{table}`")
                cols = {row[0] for row in cur.fetchall()}
                diff = sorted(required - cols)
                if diff:
                    missing_cols[table] = diff
            if missing_cols:
                for table, cols in missing_cols.items():
                    print(f"FAIL: {table} missing columns: {', '.join(cols)}")
                return 5
            print(f"PASS: connected to {db}")
            print(f"PASS: required tables present ({len(REQUIRED_TABLES)})")
            print(f"PASS: required model columns present ({len(REQUIRED_COLUMNS)} tables checked)")
            return 0
    finally:
        conn.close()

if __name__ == "__main__":
    raise SystemExit(main())
