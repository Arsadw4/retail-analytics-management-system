-- =============================================================
-- schema.sql -- Enterprise Retail Management System
-- =============================================================
-- Select the target database before loading this file. The schema script
-- deliberately does not create or switch databases, so test and staging
-- installs cannot be redirected by a hardcoded USE statement.

-- -------------------------------------------------------------
-- users
-- -------------------------------------------------------------
CREATE TABLE users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    role ENUM('super_admin','admin','manager','cashier','inventory_manager','hr','accountant','employee') NOT NULL,
    employee_code VARCHAR(20) NULL UNIQUE,
    mfa_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    mfa_secret VARCHAR(64) NULL,
    status ENUM('active', 'inactive') DEFAULT 'active',
    failed_login_attempts INT NOT NULL DEFAULT 0,
    locked_until DATETIME NULL,
    last_login_at DATETIME NULL,
    password_changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_users_role (role),
    INDEX idx_users_status (status)
);

CREATE TABLE categories (
    category_id INT AUTO_INCREMENT PRIMARY KEY,
    category_name VARCHAR(100) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- -------------------------------------------------------------
-- products -- the single source of truth for price and stock
-- quantity (see inventory table below for why this matters).
-- -------------------------------------------------------------
CREATE TABLE products (
    product_id INT AUTO_INCREMENT PRIMARY KEY,
    category_id INT,
    product_name VARCHAR(150) NOT NULL,
    sku VARCHAR(64) UNIQUE,
    barcode VARCHAR(64) UNIQUE,
    purchase_price DECIMAL(10, 2) NOT NULL,
    selling_price DECIMAL(10, 2) NOT NULL,
    stock_quantity INT DEFAULT 0,
    product_image VARCHAR(255),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    gst_rate DECIMAL(5,2) NOT NULL DEFAULT 18.00,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (category_id) REFERENCES categories(category_id),

    CONSTRAINT chk_products_purchase_price CHECK (purchase_price >= 0),
    CONSTRAINT chk_products_selling_price CHECK (selling_price >= 0),
    CONSTRAINT chk_products_stock_quantity CHECK (stock_quantity >= 0),

    INDEX idx_products_name (product_name),
    INDEX idx_products_category_active (category_id, is_active)
);

CREATE TABLE customers (
    customer_id INT AUTO_INCREMENT PRIMARY KEY,
    customer_name VARCHAR(100) NOT NULL,
    phone VARCHAR(20),
    email VARCHAR(100),
    address TEXT,
    loyalty_points INT NOT NULL DEFAULT 0,
    membership_level ENUM('Silver','Gold','Platinum') NOT NULL DEFAULT 'Silver',
    wallet_balance DECIMAL(10,2) NOT NULL DEFAULT 0,
    credit_limit DECIMAL(10,2) NOT NULL DEFAULT 0,
    credit_balance DECIMAL(10,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_customers_phone (phone),
    INDEX idx_customers_email (email)
);

-- -------------------------------------------------------------
-- departments / designations
-- -------------------------------------------------------------
CREATE TABLE departments (
    department_id INT AUTO_INCREMENT PRIMARY KEY,
    department_name VARCHAR(100) NOT NULL UNIQUE,
    description VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE designations (
    designation_id INT AUTO_INCREMENT PRIMARY KEY,
    designation_name VARCHAR(100) NOT NULL,
    department_id INT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (department_id) REFERENCES departments(department_id) ON DELETE SET NULL,
    CONSTRAINT uq_designation_per_dept UNIQUE (designation_name, department_id)
);

-- -------------------------------------------------------------
-- employees: HR record, linked to `users` (the login/RBAC identity)
-- by a real foreign key. Nullable because an employee record can
-- exist for staff without system login access (e.g. warehouse
-- floor staff who aren't given an account). `designation` (free
-- text) is kept for backward compatibility; department_id /
-- designation_id are the proper FK-based fields Phase 6 UI uses.
-- -------------------------------------------------------------
CREATE TABLE employees (
    employee_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NULL UNIQUE,
    employee_name VARCHAR(100) NOT NULL,
    email VARCHAR(100),
    phone VARCHAR(20),
    designation VARCHAR(100),
    salary DECIMAL(10, 2),
    department_id INT NULL,
    designation_id INT NULL,
    employee_code VARCHAR(20) NULL UNIQUE,
    date_of_joining DATE NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    date_of_birth DATE NULL,
    gender VARCHAR(30) NULL,
    blood_group VARCHAR(10) NULL,
    father_name VARCHAR(100) NULL,
    marital_status VARCHAR(30) NULL,
    nationality VARCHAR(60) NULL,
    language VARCHAR(100) NULL,
    alternate_phone VARCHAR(20) NULL,
    address VARCHAR(255) NULL,
    city VARCHAR(80) NULL,
    state VARCHAR(60) NULL,
    pin_code VARCHAR(10) NULL,

    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL,
    FOREIGN KEY (department_id) REFERENCES departments(department_id) ON DELETE SET NULL,
    FOREIGN KEY (designation_id) REFERENCES designations(designation_id) ON DELETE SET NULL,

    INDEX idx_employees_user (user_id)
);

CREATE TABLE IF NOT EXISTS user_profiles (
    user_id INT PRIMARY KEY,
    date_of_birth DATE NULL,
    gender VARCHAR(30) NULL,
    blood_group VARCHAR(10) NULL,
    father_name VARCHAR(100) NULL,
    marital_status VARCHAR(30) NULL,
    nationality VARCHAR(60) NULL,
    language VARCHAR(100) NULL,
    phone VARCHAR(20) NULL,
    designation VARCHAR(100) NULL,
    alternate_phone VARCHAR(20) NULL,
    address VARCHAR(255) NULL,
    city VARCHAR(80) NULL,
    state VARCHAR(60) NULL,
    pin_code VARCHAR(10) NULL,
    department_id INT NULL,
    designation_id INT NULL,
    date_of_joining DATE NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (department_id) REFERENCES departments(department_id) ON DELETE SET NULL,
    FOREIGN KEY (designation_id) REFERENCES designations(designation_id) ON DELETE SET NULL,
    INDEX idx_user_profiles_department (department_id),
    INDEX idx_user_profiles_designation (designation_id)
);

CREATE TABLE inventory_logs (
    log_id INT AUTO_INCREMENT PRIMARY KEY,
    product_id INT,
    previous_stock INT,
    new_stock INT,
    updated_by INT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (product_id) REFERENCES products(product_id),
    FOREIGN KEY (updated_by) REFERENCES users(user_id),

    INDEX idx_inventory_logs_product (product_id, updated_at)
);

CREATE TABLE activity_logs (
    activity_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    activity TEXT,
    activity_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE audit_logs (
    audit_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NULL,
    action VARCHAR(64) NOT NULL,
    details TEXT,
    ip_address VARCHAR(45),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL,

    INDEX idx_audit_user (user_id),
    INDEX idx_audit_action (action),
    INDEX idx_audit_created (created_at),
    INDEX idx_audit_logs_action_created (action, created_at)
);

CREATE TABLE sales (
    sale_id INT AUTO_INCREMENT PRIMARY KEY,
    customer_id INT,
    user_id INT,
    total_amount DECIMAL(12, 2) NOT NULL,
    profit_amount DECIMAL(12, 2) DEFAULT 0,
    status ENUM('completed', 'voided', 'held', 'refunded', 'partially_refunded') NOT NULL DEFAULT 'completed',
    invoice_number VARCHAR(30) NULL UNIQUE,
    taxable_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
    cgst_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
    sgst_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
    igst_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
    discount_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
    coupon_code VARCHAR(30) NULL,
    customer_state VARCHAR(60) NULL,
    sale_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id),

    CONSTRAINT chk_sales_total_amount CHECK (total_amount >= 0),

    INDEX idx_sales_date (sale_date),
    INDEX idx_sales_customer (customer_id),
    INDEX idx_sales_status (status),
    INDEX idx_sales_date_status (sale_date, status)
);

CREATE TABLE sale_items (
    item_id INT AUTO_INCREMENT PRIMARY KEY,
    sale_id INT,
    product_id INT,
    quantity INT NOT NULL,
    unit_price DECIMAL(10, 2) NOT NULL,
    subtotal DECIMAL(12, 2) NOT NULL,

    FOREIGN KEY (sale_id) REFERENCES sales(sale_id),
    FOREIGN KEY (product_id) REFERENCES products(product_id),

    CONSTRAINT chk_sale_items_quantity CHECK (quantity > 0),
    CONSTRAINT chk_sale_items_unit_price CHECK (unit_price >= 0),

    INDEX idx_sale_items_sale (sale_id),
    INDEX idx_sale_items_product (product_id)
);

-- -------------------------------------------------------------
-- inventory: inventory-SPECIFIC attributes only (reorder
-- thresholds, supplier, warehouse). Deliberately does NOT store
-- current_stock, purchase_price, selling_price, or stock_value --
-- those live on `products` and are joined in live via the
-- `v_inventory_full` view below. See the database design documentation section 2 for
-- why storing them here too was a real bug (silently went stale
-- after every sale).
-- -------------------------------------------------------------
-- -------------------------------------------------------------
-- warehouses (Phase 3): proper dimension table for stock location.
-- inventory.warehouse_location (free text) is kept for backward
-- compatibility but superseded by inventory.warehouse_id below.
-- -------------------------------------------------------------
CREATE TABLE warehouses (
    warehouse_id INT AUTO_INCREMENT PRIMARY KEY,
    warehouse_name VARCHAR(100) NOT NULL UNIQUE,
    location VARCHAR(150),
    contact_person VARCHAR(100),
    contact_phone VARCHAR(20),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE inventory (
    inventory_id INT PRIMARY KEY AUTO_INCREMENT,
    product_id INT NOT NULL UNIQUE,
    minimum_stock INT NOT NULL DEFAULT 10,
    maximum_stock INT DEFAULT 1000,
    supplier_name VARCHAR(100),
    supplier_contact VARCHAR(20),
    warehouse_location VARCHAR(100),
    warehouse_id INT NULL,
    last_restock_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE,
    FOREIGN KEY (warehouse_id) REFERENCES warehouses(warehouse_id) ON DELETE SET NULL,

    CONSTRAINT chk_inventory_minimum_stock CHECK (minimum_stock >= 0),
    CONSTRAINT chk_inventory_maximum_stock CHECK (maximum_stock >= 0),

    INDEX idx_inventory_warehouse (warehouse_id)
);

-- -------------------------------------------------------------
-- stock_movements (Phase 3): full audit trail of every stock in/
-- out/adjustment/sale/return event.
-- -------------------------------------------------------------
CREATE TABLE stock_movements (
    movement_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    product_id INT NOT NULL,
    warehouse_id INT NULL,
    movement_type ENUM('in', 'out', 'adjustment', 'sale', 'return') NOT NULL,
    quantity INT NOT NULL,
    reason VARCHAR(255),
    reference_type VARCHAR(50),
    reference_id INT,
    performed_by INT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (product_id) REFERENCES products(product_id),
    FOREIGN KEY (warehouse_id) REFERENCES warehouses(warehouse_id) ON DELETE SET NULL,
    FOREIGN KEY (performed_by) REFERENCES users(user_id) ON DELETE SET NULL,

    CONSTRAINT chk_stock_movements_quantity CHECK (quantity > 0),

    INDEX idx_stock_movements_product (product_id, created_at),
    INDEX idx_stock_movements_type (movement_type),
    INDEX idx_stock_movements_warehouse (warehouse_id),
    INDEX idx_stock_movements_created (created_at)
);

-- -------------------------------------------------------------
-- product_batches (Phase 3): batch/lot + expiry tracking, layered
-- on top of (not replacing) products.stock_quantity.
-- -------------------------------------------------------------
CREATE TABLE product_batches (
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

-- Read model: reconstructs the full inventory view (including
-- current_stock/prices/status) computed live from products, so it
-- can never drift out of sync the way the old duplicated columns did.
-- Phase 3 appends warehouse_id/warehouse_name at the end only --
-- every column Phase 2 code relies on keeps its name and position.
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

-- v_reorder_suggestions: products at/under their reorder point, with
-- a suggested reorder quantity (tops back up to maximum_stock).
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

-- v_expiring_batches: batches with a known expiry date, soonest first.
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

-- -------------------------------------------------------------
-- Billing & Sales System
-- -------------------------------------------------------------
CREATE TABLE company_settings (
    setting_id INT PRIMARY KEY DEFAULT 1,
    company_name VARCHAR(150) NOT NULL DEFAULT 'My Retail Company',
    gst_number VARCHAR(20),
    address VARCHAR(255),
    state VARCHAR(60) NOT NULL DEFAULT 'Same State',
    phone VARCHAR(20),
    email VARCHAR(100),
    CONSTRAINT chk_company_settings_single_row CHECK (setting_id = 1)
);

CREATE TABLE coupons (
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

CREATE TABLE sale_payments (
    payment_id INT AUTO_INCREMENT PRIMARY KEY,
    sale_id INT NOT NULL,
    payment_method ENUM('cash','upi','card','wallet') NOT NULL,
    amount DECIMAL(12,2) NOT NULL,
    reference_no VARCHAR(64),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (sale_id) REFERENCES sales(sale_id),
    CONSTRAINT chk_sale_payments_amount CHECK (amount > 0),

    INDEX idx_sale_payments_sale (sale_id),
    INDEX idx_sale_payments_method (payment_method)
);

CREATE TABLE sales_returns (
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

CREATE TABLE held_bills (
    hold_id INT AUTO_INCREMENT PRIMARY KEY,
    customer_id INT NULL,
    cart_data MEDIUMTEXT NOT NULL,
    note VARCHAR(255),
    created_by INT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (customer_id) REFERENCES customers(customer_id) ON DELETE SET NULL,
    FOREIGN KEY (created_by) REFERENCES users(user_id) ON DELETE SET NULL
);

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

-- -------------------------------------------------------------
-- Customer & Supplier Management
-- -------------------------------------------------------------
CREATE TABLE customer_ledger (
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

CREATE TABLE suppliers (
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

CREATE TABLE supplier_ledger (
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

CREATE TABLE supplier_payments (
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

CREATE TABLE purchase_orders (
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

CREATE TABLE purchase_order_items (
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

CREATE TABLE grn (
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

CREATE TABLE grn_items (
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

-- -------------------------------------------------------------
-- Employee & Administration
-- -------------------------------------------------------------
CREATE TABLE attendance (
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

CREATE TABLE leave_requests (
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

CREATE TABLE salary_records (
    salary_id INT AUTO_INCREMENT PRIMARY KEY,
    employee_id INT NOT NULL,
    salary_month VARCHAR(7) NOT NULL,
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

CREATE TABLE employee_performance (
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

CREATE TABLE employee_documents (
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

CREATE TABLE permissions (
    permission_id INT AUTO_INCREMENT PRIMARY KEY,
    permission_key VARCHAR(60) NOT NULL UNIQUE,
    description VARCHAR(255)
);

CREATE TABLE role_permissions (
    role VARCHAR(30) NOT NULL,
    permission_key VARCHAR(60) NOT NULL,
    PRIMARY KEY (role, permission_key),
    FOREIGN KEY (permission_key) REFERENCES permissions(permission_key) ON DELETE CASCADE
);

CREATE TABLE user_sessions (
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

INSERT INTO permissions (permission_key, description) VALUES
    ('approve_leave', 'Approve or reject employee leave requests'),
    ('process_salary', 'Create and mark salary records as paid'),
    ('manage_departments', 'Create/edit departments and designations'),
    ('manage_users', 'Create/edit/delete user accounts'),
    ('view_audit_logs', 'View system audit and login history'),
    ('manage_permissions', 'Change which roles have which permissions');

INSERT INTO role_permissions (role, permission_key) VALUES
    ('super_admin','approve_leave'), ('super_admin','process_salary'),
    ('super_admin','manage_departments'), ('super_admin','manage_users'),
    ('super_admin','view_audit_logs'), ('super_admin','manage_permissions'),
    ('admin','approve_leave'), ('admin','process_salary'),
    ('admin','manage_departments'), ('admin','manage_users'),
    ('admin','view_audit_logs'), ('admin','manage_permissions'),
    ('hr','approve_leave'), ('hr','manage_departments'),
    ('accountant','process_salary'), ('accountant','view_audit_logs');

-- -------------------------------------------------------------
-- Phase 7: Power BI Row-Level Security support (see star_schema.sql
-- for the full Power BI star schema views, and
-- database/powerbi/POWER_BI_SETUP_GUIDE.md for how this table is used)
-- -------------------------------------------------------------
CREATE TABLE bi_user_store_access (
    access_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    warehouse_id INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (warehouse_id) REFERENCES warehouses(warehouse_id) ON DELETE CASCADE,
    CONSTRAINT uq_bi_user_store UNIQUE (user_id, warehouse_id)
);

-- -------------------------------------------------------------
-- AI & BI helper view
-- -------------------------------------------------------------
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

-- -------------------------------------------------------------
-- Backup & Recovery logs
-- -------------------------------------------------------------
CREATE TABLE backup_logs (
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

CREATE TABLE restore_logs (
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
-- Seed data
-- -------------------------------------------------------------
INSERT INTO categories (category_name) VALUES
('Electronics'), ('Clothing'), ('Grocery'), ('Furniture'), ('Books');

-- Default admin account. No password credential is included; the empty
-- value cannot pass password verification. Provision a local hash before
-- first login:
--   python -c "from getpass import getpass; from core.security import hash_password; print(hash_password(getpass('New admin password: ')))"
--   UPDATE users SET password='<hash above>' WHERE email='admin@example.com';
INSERT INTO users (full_name, email, password, role) VALUES
('System Administrator', 'admin@example.com',
 '', 'admin');

INSERT INTO company_settings (setting_id, company_name, state) VALUES (1, 'My Retail Company', 'Same State');
