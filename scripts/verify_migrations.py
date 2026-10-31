#!/usr/bin/env python3
"""
scripts/verify_migrations.py
Confirms the connected database has every table/view this application
expects, using the consolidated schema.sql / migration file (with optional
star_schema.sql for Power BI). Run this after any deployment or migration
to catch a missed/failed migration step before the app itself hits a
"table doesn't exist" error in production.

Usage:
    python scripts/verify_migrations.py
Exit code 0 = all present, 1 = something is missing (details printed).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from database.db import mysql

EXPECTED_TABLES = [
    # Phase 1
    "users", "categories", "products", "customers", "employees",
    "inventory_logs", "activity_logs", "audit_logs", "sales", "sale_items",
    # Phase 2
    "inventory",
    # Phase 3
    "warehouses", "stock_movements", "product_batches",
    # Phase 4
    "company_settings", "coupons", "sale_payments", "sales_returns", "held_bills",
    # Phase 5
    "customer_ledger", "suppliers", "supplier_ledger", "supplier_payments",
    "purchase_orders", "purchase_order_items", "grn", "grn_items",
    # Phase 6
    "departments", "designations", "attendance", "leave_requests",
    "salary_records", "employee_performance", "employee_documents",
    "permissions", "role_permissions", "user_sessions",
    # Phase 7
    "bi_user_store_access",
    # User profile data is created by migration 003_user_profile_fields.sql.
    "user_profiles",
    # Phase 9
    "backup_logs", "restore_logs",
]

EXPECTED_VIEWS = [
    "v_inventory_full", "v_reorder_suggestions", "v_expiring_batches",
    "v_daily_sales", "v_weekly_sales", "v_monthly_sales", "v_tax_report",
    "v_customer_analytics", "v_supplier_performance",
    "v_login_history", "v_attendance_summary", "v_department_report",
    "v_daily_product_sales",
    # v_bi_user_store_access is provided by the optional Power BI star schema.
]

STAR_SCHEMA_VIEWS = [
    "v_bi_user_store_access", "dim_date", "dim_product", "dim_customer", "dim_supplier",
    "dim_employee", "dim_store", "fact_sales", "fact_inventory_snapshot",
    "fact_purchases", "fact_payments",
]


def main():
    app = create_app()
    with app.app_context():
        cur = mysql.connection.cursor()
        cur.execute("SHOW FULL TABLES")
        rows = cur.fetchall()
        cur.close()

        existing_tables = {r[0] for r in rows if r[1] == "BASE TABLE"}
        existing_views = {r[0] for r in rows if r[1] == "VIEW"}

    missing_tables = [t for t in EXPECTED_TABLES if t not in existing_tables]
    missing_views = [v for v in EXPECTED_VIEWS if v not in existing_views]
    missing_star_schema = [v for v in STAR_SCHEMA_VIEWS if v not in existing_views]

    ok = True

    if missing_tables:
        ok = False
        print("MISSING TABLES (run the corresponding migration):")
        for t in missing_tables:
            print(f"  - {t}")

    if missing_views:
        ok = False
        print("MISSING VIEWS (run the corresponding migration):")
        for v in missing_views:
            print(f"  - {v}")

    if missing_star_schema:
        print("NOTE: star_schema.sql (Power BI) views not found -- optional, "
              "only needed if you're using the Power BI integration:")
        for v in missing_star_schema:
            print(f"  - {v}")

    if ok:
        print(f"OK: all {len(EXPECTED_TABLES)} required tables and {len(EXPECTED_VIEWS)} "
              f"required views are present.")
        sys.exit(0)
    else:
        print("\nRun database/schema.sql (fresh install) or database/migrations/001_initial_database_migration.sql "
              "(existing database) -- see INSTALLATION_GUIDE.md.")
        sys.exit(1)


if __name__ == "__main__":
    main()
