-- =============================================================
-- Enterprise Power BI star schema (dimension + fact VIEWS)
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
-- Select the target database before loading this file.

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
