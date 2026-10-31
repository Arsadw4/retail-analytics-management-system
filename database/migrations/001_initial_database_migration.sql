-- Retail Analytics System: Consolidated Initial Database Migration
-- Ordered content from the original 001-009 migrations.
-- The target database is selected by the mysql command line.
-- Run this file once against a database that does not already have these migrations applied.


-- =============================================================
-- Source migration: 001_phase1_security_rbac.sql
-- =============================================================
-- =============================================================
-- Migration 001: Phase 1 security + RBAC upgrade
-- Safe to run against an EXISTING database with real data.
-- Run once: mysql -u <user> -p <database_name> < 001_phase1_security_rbac.sql
-- =============================================================

-- The mysql client selects the target database; this migration does not override it.

-- Add 'manager' to the role hierarchy without dropping existing rows.
-- MySQL requires redefining the ENUM; existing 'admin'/'employee'
-- values are preserved automatically.
ALTER TABLE users
    MODIFY COLUMN role ENUM('admin', 'manager', 'employee') NOT NULL;

-- Account lockout / brute-force defense columns (see core/security.py)
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS failed_login_attempts INT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS locked_until DATETIME NULL,
    ADD COLUMN IF NOT EXISTS last_login_at DATETIME NULL,
    ADD COLUMN IF NOT EXISTS password_changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

ALTER TABLE users
    ADD INDEX IF NOT EXISTS idx_users_role (role),
    ADD INDEX IF NOT EXISTS idx_users_status (status);

-- Product catalog additions used by inventory/barcode features (Phase 3)
-- added now so the column exists before that phase's code ships.
ALTER TABLE products
    ADD COLUMN IF NOT EXISTS sku VARCHAR(64) UNIQUE,
    ADD COLUMN IF NOT EXISTS barcode VARCHAR(64) UNIQUE,
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE products
    ADD INDEX IF NOT EXISTS idx_products_name (product_name),
    ADD INDEX IF NOT EXISTS idx_products_category (category_id),
    ADD INDEX IF NOT EXISTS idx_products_active (is_active);

ALTER TABLE customers
    ADD INDEX IF NOT EXISTS idx_customers_phone (phone),
    ADD INDEX IF NOT EXISTS idx_customers_email (email);

ALTER TABLE sales
    ADD COLUMN IF NOT EXISTS status ENUM('completed', 'voided') NOT NULL DEFAULT 'completed';

ALTER TABLE sales
    ADD INDEX IF NOT EXISTS idx_sales_date (sale_date),
    ADD INDEX IF NOT EXISTS idx_sales_customer (customer_id),
    ADD INDEX IF NOT EXISTS idx_sales_status (status);

ALTER TABLE sale_items
    ADD INDEX IF NOT EXISTS idx_sale_items_sale (sale_id),
    ADD INDEX IF NOT EXISTS idx_sale_items_product (product_id);

ALTER TABLE inventory
    ADD INDEX IF NOT EXISTS idx_inventory_status (status);

ALTER TABLE inventory_logs
    ADD INDEX IF NOT EXISTS idx_inventory_logs_product (product_id, updated_at);

-- New append-only audit trail (see core/audit.py)
CREATE TABLE IF NOT EXISTS audit_logs (
    audit_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NULL,
    action VARCHAR(64) NOT NULL,
    details TEXT,
    ip_address VARCHAR(45),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL,

    INDEX idx_audit_user (user_id),
    INDEX idx_audit_action (action),
    INDEX idx_audit_created (created_at)
);

-- IMPORTANT MANUAL STEP: this migration does NOT touch existing
-- password hashes. If any account in your `users` table was ever
-- created with a plaintext or weakly-hashed password, force a reset
-- for that account rather than trusting the migration to fix it.


-- =============================================================
-- Source migration: 002_phase2_schema_redesign.sql
-- =============================================================
-- =============================================================
-- Migration 002: Phase 2 -- Database architecture redesign
-- Safe to run against an EXISTING database with real data.
-- Run once, AFTER migration 001:
--   mysql -u <user> -p <database_name> < 002_phase2_schema_redesign.sql
-- =============================================================
--
-- This migration does three things:
--   1. Links `employees` to `users` with a real foreign key instead
--      of matching rows by email string.
--   2. Removes duplicated stock/price data from `inventory` (it was
--      a second, independently-editable copy of data that already
--      lives on `products`, and nothing kept the two in sync -- see
--      the database design documentation section 2 for the full explanation of the
--      bug this caused).
--   3. Adds indexes/constraints Phase 1 didn't cover, and creates
--      the Power BI star-schema views (additive only -- see
--      database/star_schema.sql).
--
-- Nothing in this file DROPs a table or deletes rows. Column drops
-- below only remove columns being replaced by a VIEW that recomputes
-- the same values live from `products`, so no information is lost.
--
-- Idempotency note: statements that add/drop COLUMNs or INDEXes use
-- IF [NOT] EXISTS and are safe to re-run. MySQL does not support
-- IF NOT EXISTS on ADD CONSTRAINT (FOREIGN KEY / CHECK), so those
-- specific statements are NOT safe to re-run -- run this file once.
-- =============================================================

-- The mysql client selects the target database; this migration does not override it.

-- -------------------------------------------------------------
-- 1. employees <-> users relationship
-- -------------------------------------------------------------
-- Before: employee_model.py matched rows between `employees` and
-- `users` by comparing the `email` column in application code. If an
-- employee's email was edited in one table (update_employee only
-- updated `employees.email`, never `users.email`), the two rows
-- silently fell out of sync and delete_employee's
-- `DELETE FROM users WHERE email=<employees.email>` would then
-- delete the wrong user (or nobody). A real foreign key removes the
-- possibility of that drift entirely.
ALTER TABLE employees
    ADD COLUMN IF NOT EXISTS user_id INT NULL UNIQUE;

-- Backfill existing rows by matching on email (the only link that
-- existed before). Rows with no matching user (e.g. an "employee"
-- record for someone without system login access) are left NULL,
-- which the column allows.
UPDATE employees e
JOIN users u ON u.email = e.email
SET e.user_id = u.user_id
WHERE e.user_id IS NULL;

ALTER TABLE employees
    ADD CONSTRAINT fk_employees_user
        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL;

-- -------------------------------------------------------------
-- 2. inventory: remove duplicated stock/price columns
-- -------------------------------------------------------------
-- Before: `inventory` stored its OWN current_stock, purchase_price,
-- and selling_price, entered separately by an admin on the "Add
-- Inventory" form -- a full second copy of data `products` already
-- owns. Worse: when a sale was made, sales_model.create_sale()
-- decremented products.stock_quantity but had no idea `inventory`
-- existed, so it never touched inventory.current_stock. The
-- Inventory page's numbers silently drifted from reality after the
-- very first sale and never corrected themselves.
--
-- Fix: `products` becomes the single source of truth for stock and
-- price. `inventory` keeps only genuinely inventory-specific data
-- (reorder thresholds, supplier, warehouse). Reads that need
-- stock/price go through the `v_inventory_full` view (see below),
-- which computes them live from `products` -- so they can never be
-- stale again.
--
-- IMPORTANT: back up your database before running this block if you
-- have inventory records whose purchase_price/selling_price were
-- edited to differ from the matching product's price -- those
-- inventory-specific overrides are not preserved (there was no way
-- to know, from data alone, whether a difference was an intentional
-- override or drift; `products` is treated as authoritative since
-- it's the value actually used at checkout).

ALTER TABLE inventory
    DROP COLUMN IF EXISTS stock_value;   -- generated column; depended on the columns below

ALTER TABLE inventory
    DROP COLUMN IF EXISTS current_stock,
    DROP COLUMN IF EXISTS purchase_price,
    DROP COLUMN IF EXISTS selling_price,
    DROP COLUMN IF EXISTS status;        -- now computed live in the view instead of stored

-- Enforce the intended 1:1 relationship between inventory and
-- products (previously unenforced -- nothing stopped two inventory
-- rows pointing at the same product, which would have made
-- "the" stock level for that product ambiguous).
ALTER TABLE inventory
    ADD UNIQUE INDEX IF NOT EXISTS uq_inventory_product (product_id);

-- -------------------------------------------------------------
-- v_inventory_full: read model reconstructing the old inventory
-- shape (current_stock, purchase_price, selling_price, stock_value,
-- status), computed live from products so it is always correct.
-- -------------------------------------------------------------
CREATE OR REPLACE VIEW v_inventory_full AS
SELECT
    i.inventory_id,
    i.product_id,
    p.product_name,
    p.stock_quantity                              AS current_stock,
    i.minimum_stock,
    i.maximum_stock,
    p.purchase_price,
    p.selling_price,
    p.stock_quantity * p.purchase_price            AS stock_value,
    i.supplier_name,
    i.supplier_contact,
    i.warehouse_location,
    i.last_restock_date,
    CASE
        WHEN p.stock_quantity = 0 THEN 'Out Of Stock'
        WHEN p.stock_quantity <= i.minimum_stock THEN 'Low Stock'
        ELSE 'In Stock'
    END                                              AS status,
    i.created_at,
    i.updated_at
FROM inventory i
JOIN products p ON i.product_id = p.product_id;

-- -------------------------------------------------------------
-- 3. Additional constraints & indexes
-- -------------------------------------------------------------

-- Non-negative price/stock guards. Nothing previously stopped a
-- negative purchase_price or a sale for -5 units from being saved.
ALTER TABLE products
    ADD CONSTRAINT chk_products_purchase_price CHECK (purchase_price >= 0),
    ADD CONSTRAINT chk_products_selling_price CHECK (selling_price >= 0),
    ADD CONSTRAINT chk_products_stock_quantity CHECK (stock_quantity >= 0);

ALTER TABLE sale_items
    ADD CONSTRAINT chk_sale_items_quantity CHECK (quantity > 0),
    ADD CONSTRAINT chk_sale_items_unit_price CHECK (unit_price >= 0);

ALTER TABLE sales
    ADD CONSTRAINT chk_sales_total_amount CHECK (total_amount >= 0);

ALTER TABLE inventory
    ADD CONSTRAINT chk_inventory_minimum_stock CHECK (minimum_stock >= 0),
    ADD CONSTRAINT chk_inventory_maximum_stock CHECK (maximum_stock >= 0);

-- Composite indexes matching the query patterns dashboards/reports
-- actually run (date-range + status filtering on sales; active
-- products within a category).
ALTER TABLE sales
    ADD INDEX IF NOT EXISTS idx_sales_date_status (sale_date, status);

ALTER TABLE products
    ADD INDEX IF NOT EXISTS idx_products_category_active (category_id, is_active);

ALTER TABLE employees
    ADD INDEX IF NOT EXISTS idx_employees_user (user_id);

-- -------------------------------------------------------------
-- Post-migration manual check
-- -------------------------------------------------------------
-- Run this and review any rows returned -- these are employees whose
-- email did not match any users row, so user_id could not be
-- backfilled automatically. This is expected for employees who never
-- had login access; verify none of them SHOULD have been linked.
--
--   SELECT employee_id, employee_name, email
--   FROM employees
--   WHERE user_id IS NULL;


-- =============================================================
-- Source migration: 003_phase3_inventory_management.sql
-- =============================================================
-- =============================================================
-- Migration 003: Phase 3 -- Inventory Management
-- Safe to run against an EXISTING Phase 1 + Phase 2 database.
-- Run once, AFTER migrations 001 and 002:
--   mysql -u <user> -p <database_name> < 003_phase3_inventory_management.sql
-- =============================================================
--
-- This migration is purely ADDITIVE -- it does not drop, rename, or
-- change the type of any existing column, and does not touch
-- products.stock_quantity (still the single source of truth for a
-- product's total stock, per the Phase 2 redesign). It adds:
--   1. warehouses            -- proper dimension table (replaces the
--                                free-text inventory.warehouse_location,
--                                which is left in place, untouched,
--                                for backward compatibility)
--   2. stock_movements       -- full audit trail of every stock in/out/
--                                adjustment/sale/return event
--   3. product_batches       -- batch/lot + expiry tracking, layered on
--                                top of (not replacing) the product's
--                                total stock_quantity
--   4. v_reorder_suggestions -- read-only view: products at/under their
--                                reorder threshold, with a suggested
--                                reorder quantity
--   5. v_expiring_batches    -- read-only view: batches with an expiry
--                                date, nearest-expiring first
--   6. v_inventory_full      -- extended (CREATE OR REPLACE) with a
--                                warehouse_id/warehouse_name column;
--                                every existing column is unchanged in
--                                name, type, and position, so Phase 2
--                                code that reads it positionally is
--                                unaffected
--
-- Scope note (see the database design documentation section "Design decisions" for the
-- full reasoning): this migration does NOT split products.stock_quantity
-- into per-warehouse quantities. Doing that correctly would require
-- rewriting sales_model.create_sale()'s stock-locking logic and every
-- low-stock/dashboard query built on top of it in Phase 1/2 -- exactly
-- the kind of rewrite this phase was told not to do. What's delivered
-- here is real warehouse/store management (assign inventory records to
-- a warehouse, manage warehouses, see stock movements per warehouse)
-- without touching the proven single-total stock model underneath it.
-- =============================================================

-- The mysql client selects the target database; this migration does not override it.

-- -------------------------------------------------------------
-- 1. warehouses
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS warehouses (
    warehouse_id INT AUTO_INCREMENT PRIMARY KEY,
    warehouse_name VARCHAR(100) NOT NULL UNIQUE,
    location VARCHAR(150),
    contact_person VARCHAR(100),
    contact_phone VARCHAR(20),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Link inventory records to a warehouse. Nullable + a plain FK
-- (not UNIQUE) -- inventory.product_id is already UNIQUE from Phase 2
-- (one inventory row per product), so this just tags which warehouse
-- that row's stock is primarily held in.
ALTER TABLE inventory
    ADD COLUMN IF NOT EXISTS warehouse_id INT NULL;

SET @fk_exists = (
    SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND TABLE_NAME = 'inventory'
      AND CONSTRAINT_NAME = 'fk_inventory_warehouse'
);
SET @sql = IF(@fk_exists = 0,
    'ALTER TABLE inventory ADD CONSTRAINT fk_inventory_warehouse FOREIGN KEY (warehouse_id) REFERENCES warehouses(warehouse_id) ON DELETE SET NULL',
    'SELECT 1'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

ALTER TABLE inventory
    ADD INDEX IF NOT EXISTS idx_inventory_warehouse (warehouse_id);

-- -------------------------------------------------------------
-- 2. stock_movements -- full audit trail of stock changes
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS stock_movements (
    movement_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    product_id INT NOT NULL,
    warehouse_id INT NULL,
    movement_type ENUM('in', 'out', 'adjustment', 'sale', 'return') NOT NULL,
    quantity INT NOT NULL,
    reason VARCHAR(255),
    reference_type VARCHAR(50),   -- e.g. 'sale', 'purchase', 'manual', 'batch'
    reference_id INT,             -- e.g. the sale_id or batch_id, when applicable
    performed_by INT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (product_id) REFERENCES products(product_id),
    FOREIGN KEY (warehouse_id) REFERENCES warehouses(warehouse_id) ON DELETE SET NULL,
    FOREIGN KEY (performed_by) REFERENCES users(user_id) ON DELETE SET NULL,

    CONSTRAINT chk_stock_movements_quantity CHECK (quantity > 0),

    INDEX idx_stock_movements_product (product_id, created_at),
    INDEX idx_stock_movements_type (movement_type),
    INDEX idx_stock_movements_warehouse (warehouse_id)
);

-- -------------------------------------------------------------
-- 3. product_batches -- batch/lot + expiry tracking
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS product_batches (
    batch_id INT AUTO_INCREMENT PRIMARY KEY,
    product_id INT NOT NULL,
    warehouse_id INT NULL,
    batch_number VARCHAR(64) NOT NULL,
    quantity INT NOT NULL DEFAULT 0,
    manufacture_date DATE NULL,
    expiry_date DATE NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE,
    FOREIGN KEY (warehouse_id) REFERENCES warehouses(warehouse_id) ON DELETE SET NULL,

    CONSTRAINT chk_product_batches_quantity CHECK (quantity >= 0),
    CONSTRAINT uq_product_batch_number UNIQUE (product_id, batch_number),

    INDEX idx_batches_product (product_id),
    INDEX idx_batches_expiry (expiry_date)
);

-- -------------------------------------------------------------
-- v_inventory_full -- extended with warehouse info. Every column
-- that existed before (inventory_id .. updated_at) keeps the exact
-- same name/position; warehouse_id/warehouse_name are new columns
-- appended at the end, so Phase 2 code reading specific named
-- columns is completely unaffected.
-- -------------------------------------------------------------
CREATE OR REPLACE VIEW v_inventory_full AS
SELECT
    i.inventory_id,
    i.product_id,
    p.product_name,
    p.stock_quantity                              AS current_stock,
    i.minimum_stock,
    i.maximum_stock,
    p.purchase_price,
    p.selling_price,
    p.stock_quantity * p.purchase_price            AS stock_value,
    i.supplier_name,
    i.supplier_contact,
    i.warehouse_location,
    i.last_restock_date,
    CASE
        WHEN p.stock_quantity = 0 THEN 'Out Of Stock'
        WHEN p.stock_quantity <= i.minimum_stock THEN 'Low Stock'
        ELSE 'In Stock'
    END                                              AS status,
    i.created_at,
    i.updated_at,
    i.warehouse_id,
    w.warehouse_name
FROM inventory i
JOIN products p ON i.product_id = p.product_id
LEFT JOIN warehouses w ON i.warehouse_id = w.warehouse_id;

-- -------------------------------------------------------------
-- v_reorder_suggestions -- products at/under their reorder point.
-- Suggested quantity brings stock back up to maximum_stock (falling
-- back to 2x minimum_stock if no maximum was set).
-- -------------------------------------------------------------
CREATE OR REPLACE VIEW v_reorder_suggestions AS
SELECT
    p.product_id,
    p.product_name,
    p.stock_quantity                                AS current_stock,
    i.minimum_stock,
    i.maximum_stock,
    GREATEST(
        COALESCE(i.maximum_stock, i.minimum_stock * 2) - p.stock_quantity,
        0
    )                                                AS suggested_reorder_qty,
    i.supplier_name,
    i.supplier_contact
FROM products p
JOIN inventory i ON i.product_id = p.product_id
WHERE p.stock_quantity <= i.minimum_stock
  AND p.is_active = TRUE
ORDER BY (p.stock_quantity - i.minimum_stock) ASC;

-- -------------------------------------------------------------
-- v_expiring_batches -- batches with a known expiry date, soonest
-- first, with days remaining computed live (never goes stale).
-- -------------------------------------------------------------
CREATE OR REPLACE VIEW v_expiring_batches AS
SELECT
    b.batch_id,
    b.product_id,
    p.product_name,
    b.batch_number,
    b.quantity,
    b.expiry_date,
    DATEDIFF(b.expiry_date, CURDATE())              AS days_until_expiry,
    w.warehouse_name
FROM product_batches b
JOIN products p ON b.product_id = p.product_id
LEFT JOIN warehouses w ON b.warehouse_id = w.warehouse_id
WHERE b.expiry_date IS NOT NULL
  AND b.quantity > 0
ORDER BY b.expiry_date ASC;


-- =============================================================
-- Source migration: 004_phase4_billing_sales.sql
-- =============================================================
-- =============================================================
-- Migration 004: Phase 4 -- Billing & Sales System
-- Run once, AFTER migrations 001, 002, 003:
--   mysql -u <user> -p <database_name> < 004_phase4_billing_sales.sql
-- Purely additive: no existing column is dropped or retyped except
-- sales.status, which is widened (old values 'completed'/'voided'
-- keep working unchanged) to add 'held'/'refunded'/'partially_refunded'.
-- =============================================================

-- The mysql client selects the target database; this migration does not override it.

-- Per-product GST rate (defaults to the standard 18% slab so every
-- existing product keeps working with zero manual setup).
ALTER TABLE products
    ADD COLUMN IF NOT EXISTS gst_rate DECIMAL(5,2) NOT NULL DEFAULT 18.00;

-- Widen sales.status (additive: existing values unaffected).
ALTER TABLE sales
    MODIFY COLUMN status ENUM('completed','voided','held','refunded','partially_refunded')
        NOT NULL DEFAULT 'completed';

ALTER TABLE sales
    ADD COLUMN IF NOT EXISTS invoice_number VARCHAR(30) NULL,
    ADD COLUMN IF NOT EXISTS taxable_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS cgst_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS sgst_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS igst_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS discount_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS coupon_code VARCHAR(30) NULL,
    ADD COLUMN IF NOT EXISTS customer_state VARCHAR(60) NULL;

ALTER TABLE sales
    ADD UNIQUE INDEX IF NOT EXISTS uq_sales_invoice_number (invoice_number);

CREATE TABLE IF NOT EXISTS company_settings (
    setting_id INT PRIMARY KEY DEFAULT 1,
    company_name VARCHAR(150) NOT NULL DEFAULT 'My Retail Company',
    gst_number VARCHAR(20),
    address VARCHAR(255),
    state VARCHAR(60) NOT NULL DEFAULT 'Same State',
    phone VARCHAR(20),
    email VARCHAR(100),
    CONSTRAINT chk_company_settings_single_row CHECK (setting_id = 1)
);
INSERT IGNORE INTO company_settings (setting_id) VALUES (1);

CREATE TABLE IF NOT EXISTS coupons (
    coupon_id INT AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(30) NOT NULL UNIQUE,
    discount_type ENUM('flat','percent') NOT NULL,
    discount_value DECIMAL(10,2) NOT NULL,
    min_purchase_amount DECIMAL(10,2) NOT NULL DEFAULT 0,
    valid_from DATE NULL,
    valid_until DATE NULL,
    usage_limit INT NULL,
    times_used INT NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_coupons_discount_value CHECK (discount_value >= 0)
);

CREATE TABLE IF NOT EXISTS sale_payments (
    payment_id INT AUTO_INCREMENT PRIMARY KEY,
    sale_id INT NOT NULL,
    payment_method ENUM('cash','upi','card','wallet') NOT NULL,
    amount DECIMAL(12,2) NOT NULL,
    reference_no VARCHAR(64),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (sale_id) REFERENCES sales(sale_id),
    CONSTRAINT chk_sale_payments_amount CHECK (amount > 0),

    INDEX idx_sale_payments_sale (sale_id)
);

CREATE TABLE IF NOT EXISTS sales_returns (
    return_id INT AUTO_INCREMENT PRIMARY KEY,
    sale_id INT NOT NULL,
    product_id INT NOT NULL,
    quantity INT NOT NULL,
    refund_amount DECIMAL(12,2) NOT NULL,
    reason VARCHAR(255),
    refunded_by INT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (sale_id) REFERENCES sales(sale_id),
    FOREIGN KEY (product_id) REFERENCES products(product_id),
    FOREIGN KEY (refunded_by) REFERENCES users(user_id) ON DELETE SET NULL,

    CONSTRAINT chk_sales_returns_quantity CHECK (quantity > 0),

    INDEX idx_sales_returns_sale (sale_id)
);

CREATE TABLE IF NOT EXISTS held_bills (
    hold_id INT AUTO_INCREMENT PRIMARY KEY,
    customer_id INT NULL,
    cart_data MEDIUMTEXT NOT NULL,
    note VARCHAR(255),
    created_by INT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (customer_id) REFERENCES customers(customer_id) ON DELETE SET NULL,
    FOREIGN KEY (created_by) REFERENCES users(user_id) ON DELETE SET NULL
);

-- Reporting views -----------------------------------------------

CREATE OR REPLACE VIEW v_daily_sales AS
SELECT DATE(sale_date) AS sale_day,
       COUNT(*) AS total_bills,
       COALESCE(SUM(total_amount),0) AS total_revenue,
       COALESCE(SUM(profit_amount),0) AS total_profit,
       COALESCE(SUM(cgst_amount+sgst_amount+igst_amount),0) AS total_tax
FROM sales
WHERE status = 'completed'
GROUP BY DATE(sale_date)
ORDER BY sale_day DESC;

CREATE OR REPLACE VIEW v_weekly_sales AS
SELECT YEARWEEK(sale_date,3) AS year_week,
       MIN(DATE(sale_date)) AS week_start,
       COUNT(*) AS total_bills,
       COALESCE(SUM(total_amount),0) AS total_revenue,
       COALESCE(SUM(profit_amount),0) AS total_profit,
       COALESCE(SUM(cgst_amount+sgst_amount+igst_amount),0) AS total_tax
FROM sales
WHERE status = 'completed'
GROUP BY YEARWEEK(sale_date,3)
ORDER BY year_week DESC;

CREATE OR REPLACE VIEW v_monthly_sales AS
SELECT DATE_FORMAT(sale_date,'%Y-%m') AS `year_month`,
       COUNT(*) AS total_bills,
       COALESCE(SUM(total_amount),0) AS total_revenue,
       COALESCE(SUM(profit_amount),0) AS total_profit,
       COALESCE(SUM(cgst_amount+sgst_amount+igst_amount),0) AS total_tax
FROM sales
WHERE status = 'completed'
GROUP BY DATE_FORMAT(sale_date,'%Y-%m')
ORDER BY `year_month` DESC;

CREATE OR REPLACE VIEW v_tax_report AS
SELECT DATE(sale_date) AS sale_day,
       COALESCE(SUM(cgst_amount),0) AS total_cgst,
       COALESCE(SUM(sgst_amount),0) AS total_sgst,
       COALESCE(SUM(igst_amount),0) AS total_igst,
       COALESCE(SUM(cgst_amount+sgst_amount+igst_amount),0) AS total_tax,
       COALESCE(SUM(taxable_amount),0) AS total_taxable_amount
FROM sales
WHERE status = 'completed'
GROUP BY DATE(sale_date)
ORDER BY sale_day DESC;


-- =============================================================
-- Source migration: 005_phase5_customer_supplier.sql
-- =============================================================
-- =============================================================
-- Migration 005: Phase 5 -- Customer & Supplier Management
-- Run once, AFTER migrations 001-004.
-- Purely additive: no existing column dropped/retyped.
-- =============================================================

-- The mysql client selects the target database; this migration does not override it.

ALTER TABLE customers
    ADD COLUMN IF NOT EXISTS loyalty_points INT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS membership_level ENUM('Silver','Gold','Platinum') NOT NULL DEFAULT 'Silver',
    ADD COLUMN IF NOT EXISTS wallet_balance DECIMAL(10,2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS credit_limit DECIMAL(10,2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS credit_balance DECIMAL(10,2) NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS customer_ledger (
    ledger_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    customer_id INT NOT NULL,
    transaction_type ENUM('purchase','payment','refund','credit_sale','credit_payment',
                           'wallet_topup','wallet_debit','loyalty_earned','loyalty_redeemed') NOT NULL,
    amount DECIMAL(12,2) NOT NULL,
    balance_after DECIMAL(12,2) NOT NULL,
    reference_type VARCHAR(50),
    reference_id INT,
    notes VARCHAR(255),
    created_by INT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    FOREIGN KEY (created_by) REFERENCES users(user_id) ON DELETE SET NULL,

    INDEX idx_customer_ledger_customer (customer_id, created_at)
);

CREATE TABLE IF NOT EXISTS suppliers (
    supplier_id INT AUTO_INCREMENT PRIMARY KEY,
    supplier_name VARCHAR(150) NOT NULL,
    contact_person VARCHAR(100),
    phone VARCHAR(20),
    email VARCHAR(100),
    address VARCHAR(255),
    gst_number VARCHAR(20),
    outstanding_balance DECIMAL(12,2) NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_suppliers_name (supplier_name)
);

CREATE TABLE IF NOT EXISTS supplier_ledger (
    ledger_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    supplier_id INT NOT NULL,
    transaction_type ENUM('purchase','payment','adjustment') NOT NULL,
    amount DECIMAL(12,2) NOT NULL,
    balance_after DECIMAL(12,2) NOT NULL,
    reference_type VARCHAR(50),
    reference_id INT,
    notes VARCHAR(255),
    created_by INT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id),
    FOREIGN KEY (created_by) REFERENCES users(user_id) ON DELETE SET NULL,

    INDEX idx_supplier_ledger_supplier (supplier_id, created_at)
);

CREATE TABLE IF NOT EXISTS supplier_payments (
    payment_id INT AUTO_INCREMENT PRIMARY KEY,
    supplier_id INT NOT NULL,
    amount DECIMAL(12,2) NOT NULL,
    payment_method VARCHAR(30) NOT NULL DEFAULT 'bank_transfer',
    reference_no VARCHAR(64),
    notes VARCHAR(255),
    created_by INT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id),
    FOREIGN KEY (created_by) REFERENCES users(user_id) ON DELETE SET NULL,

    CONSTRAINT chk_supplier_payments_amount CHECK (amount > 0)
);

CREATE TABLE IF NOT EXISTS purchase_orders (
    po_id INT AUTO_INCREMENT PRIMARY KEY,
    po_number VARCHAR(30) NULL UNIQUE,
    supplier_id INT NOT NULL,
    status ENUM('draft','ordered','partially_received','received','cancelled') NOT NULL DEFAULT 'draft',
    expected_date DATE NULL,
    total_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
    notes VARCHAR(255),
    created_by INT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id),
    FOREIGN KEY (created_by) REFERENCES users(user_id) ON DELETE SET NULL,

    INDEX idx_po_supplier (supplier_id),
    INDEX idx_po_status (status)
);

CREATE TABLE IF NOT EXISTS purchase_order_items (
    po_item_id INT AUTO_INCREMENT PRIMARY KEY,
    po_id INT NOT NULL,
    product_id INT NOT NULL,
    quantity_ordered INT NOT NULL,
    quantity_received INT NOT NULL DEFAULT 0,
    unit_cost DECIMAL(10,2) NOT NULL,
    subtotal DECIMAL(12,2) NOT NULL,

    FOREIGN KEY (po_id) REFERENCES purchase_orders(po_id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(product_id),

    CONSTRAINT chk_po_items_qty CHECK (quantity_ordered > 0),

    INDEX idx_po_items_po (po_id)
);

CREATE TABLE IF NOT EXISTS grn (
    grn_id INT AUTO_INCREMENT PRIMARY KEY,
    grn_number VARCHAR(30) NULL UNIQUE,
    po_id INT NULL,
    supplier_id INT NOT NULL,
    received_date DATE NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
    notes VARCHAR(255),
    received_by INT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (po_id) REFERENCES purchase_orders(po_id) ON DELETE SET NULL,
    FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id),
    FOREIGN KEY (received_by) REFERENCES users(user_id) ON DELETE SET NULL,

    INDEX idx_grn_supplier (supplier_id)
);

CREATE TABLE IF NOT EXISTS grn_items (
    grn_item_id INT AUTO_INCREMENT PRIMARY KEY,
    grn_id INT NOT NULL,
    po_item_id INT NULL,
    product_id INT NOT NULL,
    quantity_received INT NOT NULL,
    unit_cost DECIMAL(10,2) NOT NULL,

    FOREIGN KEY (grn_id) REFERENCES grn(grn_id) ON DELETE CASCADE,
    FOREIGN KEY (po_item_id) REFERENCES purchase_order_items(po_item_id) ON DELETE SET NULL,
    FOREIGN KEY (product_id) REFERENCES products(product_id),

    CONSTRAINT chk_grn_items_qty CHECK (quantity_received > 0),

    INDEX idx_grn_items_grn (grn_id)
);

-- Reporting / analytics views --------------------------------

CREATE OR REPLACE VIEW v_customer_analytics AS
SELECT
    c.customer_id, c.customer_name, c.membership_level, c.loyalty_points, c.wallet_balance,
    c.credit_limit, c.credit_balance,
    COUNT(s.sale_id) AS total_orders,
    COALESCE(SUM(s.total_amount),0) AS total_spent,
    COALESCE(AVG(s.total_amount),0) AS avg_order_value,
    MAX(s.sale_date) AS last_purchase_date
FROM customers c
LEFT JOIN sales s ON s.customer_id = c.customer_id AND s.status = 'completed'
GROUP BY c.customer_id, c.customer_name, c.membership_level, c.loyalty_points,
         c.wallet_balance, c.credit_limit, c.credit_balance;

CREATE OR REPLACE VIEW v_supplier_performance AS
SELECT
    s.supplier_id, s.supplier_name, s.outstanding_balance,
    COUNT(DISTINCT po.po_id) AS total_purchase_orders,
    COUNT(DISTINCT g.grn_id) AS total_grns,
    COALESCE(SUM(g.total_amount),0) AS total_purchase_value
FROM suppliers s
LEFT JOIN purchase_orders po ON po.supplier_id = s.supplier_id
LEFT JOIN grn g ON g.supplier_id = s.supplier_id
GROUP BY s.supplier_id, s.supplier_name, s.outstanding_balance;


-- =============================================================
-- Source migration: 006_phase6_employee_admin.sql
-- =============================================================
-- =============================================================
-- Migration 006: Phase 6 -- Enterprise Employee & Administration
-- Run once, AFTER migrations 001-005. Purely additive.
--
-- RBAC note: users.role is WIDENED from
-- ('admin','manager','employee') to add 'super_admin','cashier',
-- 'inventory_manager','hr','accountant' -- the three original values
-- are untouched, so every existing @role_required("admin","manager",
-- "employee") check across Phases 1-5 keeps working exactly as
-- before for existing users. 'super_admin' is handled as a universal
-- bypass in core/rbac.py (one additive conditional, not a rewrite of
-- the ~50 existing call sites). The other four new roles were added
-- to the specific existing route decorators where they clearly
-- belong (POS for cashier, inventory for inventory_manager, billing
-- reports/ledgers for accountant) -- see the project security documentation for the
-- exact list.
-- =============================================================

-- The mysql client selects the target database; this migration does not override it.

ALTER TABLE users
    MODIFY COLUMN role ENUM('super_admin','admin','manager','cashier',
                             'inventory_manager','hr','accountant','employee')
        NOT NULL;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS employee_code VARCHAR(20) NULL UNIQUE;

CREATE TABLE IF NOT EXISTS departments (
    department_id INT AUTO_INCREMENT PRIMARY KEY,
    department_name VARCHAR(100) NOT NULL UNIQUE,
    description VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS designations (
    designation_id INT AUTO_INCREMENT PRIMARY KEY,
    designation_name VARCHAR(100) NOT NULL,
    department_id INT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (department_id) REFERENCES departments(department_id) ON DELETE SET NULL,
    CONSTRAINT uq_designation_per_dept UNIQUE (designation_name, department_id)
);

-- employees table (Phase 1) already has a free-text `designation`
-- column -- kept as-is for backward compatibility. department_id /
-- designation_id below are the new, proper FK-based fields used by
-- Phase 6 UI going forward.
ALTER TABLE employees
    ADD COLUMN IF NOT EXISTS department_id INT NULL,
    ADD COLUMN IF NOT EXISTS designation_id INT NULL,
    ADD COLUMN IF NOT EXISTS employee_code VARCHAR(20) NULL UNIQUE,
    ADD COLUMN IF NOT EXISTS date_of_joining DATE NULL;

SET @fk1 = (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
            WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME='employees'
              AND CONSTRAINT_NAME='fk_employees_department');
SET @sql1 = IF(@fk1 = 0,
    'ALTER TABLE employees ADD CONSTRAINT fk_employees_department FOREIGN KEY (department_id) REFERENCES departments(department_id) ON DELETE SET NULL',
    'SELECT 1');
PREPARE s1 FROM @sql1; EXECUTE s1; DEALLOCATE PREPARE s1;

SET @fk2 = (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
            WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME='employees'
              AND CONSTRAINT_NAME='fk_employees_designation');
SET @sql2 = IF(@fk2 = 0,
    'ALTER TABLE employees ADD CONSTRAINT fk_employees_designation FOREIGN KEY (designation_id) REFERENCES designations(designation_id) ON DELETE SET NULL',
    'SELECT 1');
PREPARE s2 FROM @sql2; EXECUTE s2; DEALLOCATE PREPARE s2;

CREATE TABLE IF NOT EXISTS attendance (
    attendance_id INT AUTO_INCREMENT PRIMARY KEY,
    employee_id INT NOT NULL,
    attendance_date DATE NOT NULL,
    check_in TIME NULL,
    check_out TIME NULL,
    status ENUM('present','absent','half_day','leave','holiday') NOT NULL DEFAULT 'present',
    notes VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE,
    CONSTRAINT uq_attendance_employee_date UNIQUE (employee_id, attendance_date),

    INDEX idx_attendance_date (attendance_date)
);

CREATE TABLE IF NOT EXISTS leave_requests (
    leave_id INT AUTO_INCREMENT PRIMARY KEY,
    employee_id INT NOT NULL,
    leave_type ENUM('sick','casual','earned','unpaid') NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    reason VARCHAR(255),
    status ENUM('pending','approved','rejected') NOT NULL DEFAULT 'pending',
    approved_by INT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE,
    FOREIGN KEY (approved_by) REFERENCES users(user_id) ON DELETE SET NULL,

    CONSTRAINT chk_leave_dates CHECK (end_date >= start_date),

    INDEX idx_leave_employee (employee_id)
);

CREATE TABLE IF NOT EXISTS salary_records (
    salary_id INT AUTO_INCREMENT PRIMARY KEY,
    employee_id INT NOT NULL,
    salary_month VARCHAR(7) NOT NULL,  -- 'YYYY-MM'
    basic_salary DECIMAL(10,2) NOT NULL DEFAULT 0,
    allowances DECIMAL(10,2) NOT NULL DEFAULT 0,
    deductions DECIMAL(10,2) NOT NULL DEFAULT 0,
    net_salary DECIMAL(10,2) NOT NULL DEFAULT 0,
    payment_status ENUM('pending','paid') NOT NULL DEFAULT 'pending',
    paid_date DATE NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE,
    CONSTRAINT uq_salary_employee_month UNIQUE (employee_id, salary_month),

    INDEX idx_salary_month (salary_month)
);

CREATE TABLE IF NOT EXISTS employee_performance (
    review_id INT AUTO_INCREMENT PRIMARY KEY,
    employee_id INT NOT NULL,
    review_period VARCHAR(20) NOT NULL,
    rating DECIMAL(2,1) NOT NULL,
    remarks VARCHAR(500),
    reviewed_by INT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE,
    FOREIGN KEY (reviewed_by) REFERENCES users(user_id) ON DELETE SET NULL,

    CONSTRAINT chk_performance_rating CHECK (rating >= 1.0 AND rating <= 5.0)
);

CREATE TABLE IF NOT EXISTS employee_documents (
    document_id INT AUTO_INCREMENT PRIMARY KEY,
    employee_id INT NOT NULL,
    document_type VARCHAR(50) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    notes VARCHAR(255),
    uploaded_by INT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE,
    FOREIGN KEY (uploaded_by) REFERENCES users(user_id) ON DELETE SET NULL
);

-- Fine-grained permission toggles for Phase 6's own HR/Admin actions
-- (e.g. "approve_leave", "process_salary", "manage_departments").
-- Existing Phase 1-5 route protection remains role-based
-- (@role_required) and is not retrofitted onto this table -- see
-- the project security documentation "Design decisions".
CREATE TABLE IF NOT EXISTS permissions (
    permission_id INT AUTO_INCREMENT PRIMARY KEY,
    permission_key VARCHAR(60) NOT NULL UNIQUE,
    description VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS role_permissions (
    role VARCHAR(30) NOT NULL,
    permission_key VARCHAR(60) NOT NULL,
    PRIMARY KEY (role, permission_key),
    FOREIGN KEY (permission_key) REFERENCES permissions(permission_key) ON DELETE CASCADE
);

-- Session Management: a record of active logins for visibility and
-- manual "forget this session" bookkeeping. See the project security documentation
-- "Known limitation" for what this does and does not do.
CREATE TABLE IF NOT EXISTS user_sessions (
    session_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    session_token VARCHAR(64) NOT NULL UNIQUE,
    ip_address VARCHAR(45),
    user_agent VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    INDEX idx_sessions_user (user_id)
);

INSERT IGNORE INTO permissions (permission_key, description) VALUES
    ('approve_leave', 'Approve or reject employee leave requests'),
    ('process_salary', 'Create and mark salary records as paid'),
    ('manage_departments', 'Create/edit departments and designations'),
    ('manage_users', 'Create/edit/delete user accounts'),
    ('view_audit_logs', 'View system audit and login history'),
    ('manage_permissions', 'Change which roles have which permissions');

INSERT IGNORE INTO role_permissions (role, permission_key) VALUES
    ('super_admin','approve_leave'), ('super_admin','process_salary'),
    ('super_admin','manage_departments'), ('super_admin','manage_users'),
    ('super_admin','view_audit_logs'), ('super_admin','manage_permissions'),
    ('admin','approve_leave'), ('admin','process_salary'),
    ('admin','manage_departments'), ('admin','manage_users'),
    ('admin','view_audit_logs'), ('admin','manage_permissions'),
    ('hr','approve_leave'), ('hr','manage_departments'),
    ('accountant','process_salary'), ('accountant','view_audit_logs');

-- Reporting views -------------------------------------------------

CREATE OR REPLACE VIEW v_login_history AS
SELECT a.audit_id, a.user_id, u.full_name, u.email, a.action,
       a.details, a.ip_address, a.created_at
FROM audit_logs a
LEFT JOIN users u ON a.user_id = u.user_id
WHERE a.action IN ('LOGIN_SUCCESS','LOGIN_FAILED','LOGIN_BLOCKED','ACCOUNT_LOCKED','LOGOUT')
ORDER BY a.created_at DESC;

CREATE OR REPLACE VIEW v_attendance_summary AS
SELECT e.employee_id, e.employee_name,
       DATE_FORMAT(a.attendance_date, '%Y-%m') AS month,
       SUM(CASE WHEN a.status='present' THEN 1 ELSE 0 END) AS days_present,
       SUM(CASE WHEN a.status='absent' THEN 1 ELSE 0 END) AS days_absent,
       SUM(CASE WHEN a.status='leave' THEN 1 ELSE 0 END) AS days_on_leave,
       SUM(CASE WHEN a.status='half_day' THEN 1 ELSE 0 END) AS half_days
FROM employees e
JOIN attendance a ON a.employee_id = e.employee_id
GROUP BY e.employee_id, e.employee_name, DATE_FORMAT(a.attendance_date, '%Y-%m');

CREATE OR REPLACE VIEW v_department_report AS
SELECT d.department_id, d.department_name,
       COUNT(e.employee_id) AS total_employees,
       COALESCE(SUM(e.salary),0) AS total_monthly_salary
FROM departments d
LEFT JOIN employees e ON e.department_id = d.department_id
GROUP BY d.department_id, d.department_name;


-- =============================================================
-- Source migration: 007_phase7_powerbi_bi.sql
-- =============================================================
-- =============================================================
-- Migration 007: Phase 7 -- Enterprise Power BI & BI Star Schema
-- Run once, AFTER migrations 001-006.
--
-- Everything in this file is either a VIEW (CREATE OR REPLACE --
-- views hold no data, so replacing one is always non-destructive)
-- or one small new physical table for Row-Level Security. Nothing
-- here changes any OLTP table Phases 1-6 built, and nothing in the
-- Flask app depends on these views -- they exist purely for Power BI
-- (or any other BI tool) to connect to.
--
-- This extends the dim_date / dim_product / dim_customer /
-- dim_employee / fact_sales / fact_inventory_snapshot views Phase 2
-- created, and adds dim_supplier, dim_store, fact_purchases,
-- fact_payments, and the RLS support table.
-- =============================================================

-- The mysql client selects the target database; this migration does not override it.

-- -------------------------------------------------------------
-- RLS support: which store(s) a Power BI user is scoped to. Only
-- meaningful for roles you want store-restricted in Power BI (e.g. a
-- warehouse/store manager who should only see their own store's
-- numbers) -- see POWER_BI_SETUP_GUIDE.md for how this plugs into a
-- DAX role. A user with no rows here is unrestricted under the
-- "Global" role.
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bi_user_store_access (
    access_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    warehouse_id INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (warehouse_id) REFERENCES warehouses(warehouse_id) ON DELETE CASCADE,
    CONSTRAINT uq_bi_user_store UNIQUE (user_id, warehouse_id)
);

CREATE OR REPLACE VIEW v_bi_user_store_access AS
SELECT u.email AS user_email, w.warehouse_id AS store_key, w.warehouse_name AS store_name
FROM bi_user_store_access a
JOIN users u ON a.user_id = u.user_id
JOIN warehouses w ON a.warehouse_id = w.warehouse_id;

-- -------------------------------------------------------------
-- DimDate -- extended with fiscal calendar (Apr-Mar, standard Indian
-- fiscal year matching the GST context Phase 4 introduced) and flags
-- useful for DAX time-intelligence and Power Query incremental
-- refresh range filtering.
-- -------------------------------------------------------------
CREATE OR REPLACE VIEW dim_date AS
SELECT
    DATE(d.dt)                              AS date_key,
    YEAR(d.dt)                              AS year,
    QUARTER(d.dt)                           AS quarter,
    CONCAT('Q', QUARTER(d.dt))              AS quarter_name,
    MONTH(d.dt)                             AS month,
    MONTHNAME(d.dt)                         AS month_name,
    DATE_FORMAT(d.dt, '%b')                 AS month_short,
    DATE_FORMAT(d.dt, '%Y-%m')              AS `year_month`,
    WEEK(d.dt, 3)                           AS iso_week,
    DAY(d.dt)                               AS day_of_month,
    DAYOFWEEK(d.dt)                         AS day_of_week,
    DAYNAME(d.dt)                           AS day_name,
    CASE WHEN DAYOFWEEK(d.dt) IN (1, 7) THEN TRUE ELSE FALSE END AS is_weekend,
    -- Fiscal year: Apr-Mar (e.g. Jan 2026 -> FY2025-26, Apr 2026 -> FY2026-27)
    CASE WHEN MONTH(d.dt) >= 4 THEN YEAR(d.dt) ELSE YEAR(d.dt) - 1 END AS fiscal_year,
    CASE
        WHEN MONTH(d.dt) BETWEEN 4 AND 6  THEN 1
        WHEN MONTH(d.dt) BETWEEN 7 AND 9  THEN 2
        WHEN MONTH(d.dt) BETWEEN 10 AND 12 THEN 3
        ELSE 4
    END                                      AS fiscal_quarter,
    (YEAR(d.dt) = YEAR(CURDATE()) AND MONTH(d.dt) = MONTH(CURDATE())) AS is_current_month,
    (YEAR(d.dt) = YEAR(CURDATE()))          AS is_current_year,
    DATEDIFF(CURDATE(), d.dt)               AS days_ago
FROM (
    SELECT DATE_ADD('2020-01-01', INTERVAL (a.n + b.n * 100 + c.n * 10000) DAY) AS dt
    FROM
        (SELECT 0 n UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4
         UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9) a,
        (SELECT 0 n UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4
         UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9) b,
        (SELECT 0 n UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4
         UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9) c
) d
WHERE d.dt <= DATE_ADD(CURDATE(), INTERVAL 5 YEAR);

-- -------------------------------------------------------------
-- DimProduct -- extended with GST rate and live stock level.
-- -------------------------------------------------------------
CREATE OR REPLACE VIEW dim_product AS
SELECT
    p.product_id                            AS product_key,
    p.product_name,
    p.sku,
    p.barcode,
    c.category_id,
    c.category_name,
    p.purchase_price,
    p.selling_price,
    (p.selling_price - p.purchase_price)    AS unit_margin,
    CASE WHEN p.selling_price > 0
         THEN ROUND((p.selling_price - p.purchase_price) / p.selling_price * 100, 2)
         ELSE 0 END                          AS margin_percent,
    p.gst_rate,
    p.stock_quantity,
    p.is_active
FROM products p
LEFT JOIN categories c ON p.category_id = c.category_id;

-- -------------------------------------------------------------
-- DimCustomer -- extended with Phase 5 loyalty/wallet/credit fields.
-- -------------------------------------------------------------
CREATE OR REPLACE VIEW dim_customer AS
SELECT
    customer_id                             AS customer_key,
    customer_name,
    phone,
    email,
    address,
    membership_level,
    loyalty_points,
    wallet_balance,
    credit_limit,
    credit_balance,
    created_at                              AS customer_since,
    YEAR(created_at)                        AS customer_since_year
FROM customers;

-- -------------------------------------------------------------
-- DimSupplier (new)
-- -------------------------------------------------------------
CREATE OR REPLACE VIEW dim_supplier AS
SELECT
    supplier_id                             AS supplier_key,
    supplier_name,
    contact_person,
    phone,
    email,
    gst_number,
    outstanding_balance,
    is_active,
    created_at                              AS supplier_since
FROM suppliers;

-- -------------------------------------------------------------
-- DimEmployee -- extended with Phase 6 department/designation/tenure.
-- Only staff with a login (user_id) appear here -- a purely-HR
-- employee record with no system account never appears as the
-- "sold by" / "received by" party on any fact table anyway.
-- -------------------------------------------------------------
CREATE OR REPLACE VIEW dim_employee AS
SELECT
    u.user_id                               AS employee_key,
    u.full_name,
    u.role,
    u.employee_code,
    e.designation                           AS designation_text,
    des.designation_name,
    dep.department_name,
    e.phone,
    e.date_of_joining,
    DATEDIFF(CURDATE(), e.date_of_joining)  AS tenure_days,
    u.status
FROM users u
LEFT JOIN employees e ON e.user_id = u.user_id
LEFT JOIN departments dep ON e.department_id = dep.department_id
LEFT JOIN designations des ON e.designation_id = des.designation_id
WHERE u.role IN ('admin', 'manager', 'employee', 'cashier', 'inventory_manager', 'hr', 'accountant', 'super_admin');

-- -------------------------------------------------------------
-- DimStore (new, from Phase 3 warehouses). Note: FactSales does not
-- currently carry a store_key -- sales in this system are not
-- recorded against a specific warehouse. DimStore is fully populated
-- and ready to use for FactInventory and FactPurchases today; wiring
-- it to FactSales would require adding warehouse_id to the sales
-- table, noted as a follow-up in the database design documentation rather than
-- fabricated here.
-- -------------------------------------------------------------
CREATE OR REPLACE VIEW dim_store AS
SELECT
    warehouse_id                            AS store_key,
    warehouse_name                          AS store_name,
    location,
    contact_person,
    contact_phone,
    is_active
FROM warehouses;

-- -------------------------------------------------------------
-- FactSales -- grain: one row per sale line item. Header-level
-- tax/discount (Phase 4 stores these once per sale, not per line) are
-- allocated to each line proportionally by its share of the sale's
-- taxable amount -- an approximation, documented here and in
-- the database design documentation, since Phase 4's schema does not persist a
-- per-line tax split.
-- -------------------------------------------------------------
CREATE OR REPLACE VIEW fact_sales AS
SELECT
    si.item_id                              AS fact_sales_key,
    s.sale_id,
    s.invoice_number,
    DATE(s.sale_date)                       AS date_key,
    si.product_id                           AS product_key,
    s.customer_id                           AS customer_key,
    s.user_id                               AS employee_key,
    si.quantity,
    si.unit_price,
    si.subtotal                             AS line_revenue,
    (si.unit_price - p.purchase_price) * si.quantity AS line_profit,
    CASE WHEN s.taxable_amount > 0
         THEN ROUND(si.subtotal / s.taxable_amount * s.discount_amount, 2)
         ELSE 0 END                          AS line_discount_allocated,
    CASE WHEN s.taxable_amount > 0
         THEN ROUND(si.subtotal / s.taxable_amount * (s.cgst_amount + s.sgst_amount + s.igst_amount), 2)
         ELSE 0 END                          AS line_tax_allocated,
    s.coupon_code,
    s.status
FROM sale_items si
JOIN sales s     ON si.sale_id = s.sale_id
JOIN products p  ON si.product_id = p.product_id;

-- -------------------------------------------------------------
-- FactInventory -- current-state snapshot fact (one row per
-- product's current stock position), now including its store.
-- -------------------------------------------------------------
CREATE OR REPLACE VIEW fact_inventory_snapshot AS
SELECT
    v.inventory_id                          AS fact_inventory_key,
    v.product_id                            AS product_key,
    v.warehouse_id                          AS store_key,
    v.current_stock,
    v.minimum_stock,
    v.maximum_stock,
    v.stock_value,
    v.status,
    v.last_restock_date
FROM v_inventory_full v;

-- -------------------------------------------------------------
-- FactPurchases (new) -- grain: one row per GRN line item.
-- -------------------------------------------------------------
CREATE OR REPLACE VIEW fact_purchases AS
SELECT
    gi.grn_item_id                          AS fact_purchase_key,
    g.grn_number,
    po.po_number,
    DATE(g.received_date)                   AS date_key,
    gi.product_id                           AS product_key,
    g.supplier_id                           AS supplier_key,
    g.received_by                           AS employee_key,
    gi.quantity_received,
    gi.unit_cost,
    (gi.quantity_received * gi.unit_cost)   AS line_cost
FROM grn_items gi
JOIN grn g ON gi.grn_id = g.grn_id
LEFT JOIN purchase_orders po ON g.po_id = po.po_id;

-- -------------------------------------------------------------
-- FactPayments (new) -- grain: one row per sale payment record
-- (supports split payments -- Phase 4 -- as multiple rows per sale).
-- -------------------------------------------------------------
CREATE OR REPLACE VIEW fact_payments AS
SELECT
    sp.payment_id                           AS fact_payment_key,
    s.sale_id,
    DATE(s.sale_date)                       AS date_key,
    s.customer_id                           AS customer_key,
    sp.payment_method,
    sp.amount
FROM sale_payments sp
JOIN sales s ON sp.sale_id = s.sale_id;


-- =============================================================
-- Source migration: 008_phase8_ai_bi.sql
-- =============================================================
-- =============================================================
-- Migration 008: Phase 8 -- AI & Business Intelligence
-- Run once, AFTER migrations 001-007.
--
-- Phase 8 needed almost no schema changes -- every forecast,
-- recommendation, segmentation, and BI feature is computed from data
-- Phases 1-7 already store (sales, sale_items, products, customers,
-- inventory). The only addition is one convenience view that several
-- of the new `ai/*.py` modules query repeatedly, so the aggregation
-- logic lives in one place instead of being copy-pasted across them.
-- =============================================================

-- The mysql client selects the target database; this migration does not override it.

-- Daily per-product sales -- the base aggregate nearly every
-- forecasting/demand/BI function in ai/*.py builds on (trend slope,
-- velocity, ABC classification, dead-stock detection, etc.).
CREATE OR REPLACE VIEW v_daily_product_sales AS
SELECT
    DATE(s.sale_date)                       AS sale_day,
    si.product_id,
    p.product_name,
    p.category_id,
    SUM(si.quantity)                        AS units_sold,
    SUM(si.subtotal)                        AS revenue,
    SUM((si.unit_price - p.purchase_price) * si.quantity) AS profit
FROM sale_items si
JOIN sales s     ON si.sale_id = s.sale_id
JOIN products p  ON si.product_id = p.product_id
WHERE s.status = 'completed'
GROUP BY DATE(s.sale_date), si.product_id, p.product_name, p.category_id;


-- =============================================================
-- Source migration: 009_phase9_security_backup_monitoring.sql
-- =============================================================
-- =============================================================
-- Migration 009: Phase 9 -- Security, Backup, Monitoring & Performance
-- Run once, AFTER migrations 001-008. Purely additive.
-- =============================================================

-- The mysql client selects the target database; this migration does not override it.

-- -------------------------------------------------------------
-- Multi-Factor Authentication (optional, per-user opt-in). Nullable/
-- FALSE-defaulted so every existing account keeps logging in exactly
-- as before unless they explicitly enable it from their profile.
-- -------------------------------------------------------------
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS mfa_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS mfa_secret VARCHAR(64) NULL;

-- password_changed_at already exists (Phase 1) -- used for password
-- expiration without any new column.

-- -------------------------------------------------------------
-- Backup logs
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS backup_logs (
    backup_id INT AUTO_INCREMENT PRIMARY KEY,
    file_name VARCHAR(255) NOT NULL,
    file_size_bytes BIGINT NOT NULL DEFAULT 0,
    backup_type ENUM('manual', 'scheduled') NOT NULL DEFAULT 'manual',
    status ENUM('success', 'failed') NOT NULL,
    error_message VARCHAR(500),
    triggered_by INT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (triggered_by) REFERENCES users(user_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS restore_logs (
    restore_id INT AUTO_INCREMENT PRIMARY KEY,
    source_file VARCHAR(255) NOT NULL,
    safety_backup_file VARCHAR(255),
    status ENUM('success', 'failed') NOT NULL,
    error_message VARCHAR(500),
    triggered_by INT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (triggered_by) REFERENCES users(user_id) ON DELETE SET NULL
);

-- -------------------------------------------------------------
-- Performance: a handful of indexes covering Phase 8's AI query
-- patterns and Phase 9's own log tables, which weren't needed until
-- these query shapes existed.
-- -------------------------------------------------------------
ALTER TABLE sale_payments
    ADD INDEX IF NOT EXISTS idx_sale_payments_method (payment_method);

ALTER TABLE stock_movements
    ADD INDEX IF NOT EXISTS idx_stock_movements_created (created_at);

ALTER TABLE audit_logs
    ADD INDEX IF NOT EXISTS idx_audit_logs_action_created (action, created_at);
