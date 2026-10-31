import logging

from flask import Blueprint, request, jsonify, session
from database.db import mysql
from core.rbac import role_required

global_search_bp = Blueprint('global_search', __name__)
logger = logging.getLogger(__name__)

PAGES = [
    ('Dashboard','Overview','/admin/dashboard','⌂'),('Sales','Operations','/admin/sales','₹'),('POS / Billing','Operations','/admin/billing/pos','▣'),('Customers','Operations','/admin/customers','♙'),
    ('Products','Inventory','/admin/products','□'),('Categories','Inventory','/admin/categories','◇'),('Inventory Dashboard','Inventory','/admin/inventory/dashboard','▤'),('Stock Movements','Inventory','/admin/inventory/movements','↕'),('Batches','Inventory','/admin/inventory/batches','▦'),('Low Stock','Inventory','/admin/low-stock','!'),('Expiry Report','Inventory','/admin/inventory/expiry-report','◷'),('Reorder Suggestions','Inventory','/admin/inventory/reorder-suggestions','↗'),
    ('Suppliers','Procurement','/admin/suppliers','♧'),('Purchase Orders','Procurement','/admin/purchase-orders','▭'),('GRN','Procurement','/admin/grn','✓'),('Employees','People','/admin/hr/employees','♙'),('Departments','People','/admin/departments','⌘'),('Attendance','People','/admin/hr/attendance','◉'),('Leaves','People','/admin/hr/leaves','▱'),('Payroll','People','/admin/hr/salary','₹'),
    ('Analytics','Analytics & AI','/admin/analytics','▥'),('AI Insights','Analytics & AI','/admin/ai-dashboard','✦'),('Forecasting','Analytics & AI','/admin/predictions','⌁'),('Recommendations','Analytics & AI','/admin/recommendations','★'),('Power BI','Analytics & AI','/admin/bi/store-access','▥'),('Reports','Reports','/admin/reports','▤'),('Inventory Report','Reports','/admin/inventory/stock-report','▥'),('Tax Report','Reports','/admin/billing/reports/tax','◈'),
    ('Users','Administration','/admin/users','♙'),('Roles & Permissions','Administration','/admin/permissions','⌑'),('Activity Logs','Administration','/admin/activity-logs','≡'),('Login History','Administration','/admin/login-history','◴'),('Sessions','Administration','/admin/sessions','◉'),('System Health','System','/admin/system/health','♥'),('System Logs','System','/admin/system/logs','≡'),('Backups','System','/admin/system/backups','▣'),('Restore','System','/admin/system/restore','↶'),('Settings','System','/admin/settings','⚙'),('My Security','System','/account/security','⌑')
]

_PAGE_ROLES = {
    '/admin/dashboard': {'admin','manager','super_admin'},
    '/admin/sales': {'admin','manager','employee'},
    '/admin/billing/pos': {'admin','manager','employee','cashier'},
    '/admin/customers': {'admin','manager','employee'},
    '/admin/products': {'admin','manager','employee'},
    '/admin/categories': {'admin','manager'},
    '/admin/inventory/dashboard': {'admin','manager','inventory_manager'},
    '/admin/inventory/movements': {'admin','manager','inventory_manager'},
    '/admin/inventory/batches': {'admin','manager','inventory_manager'},
    '/admin/low-stock': {'admin','manager','inventory_manager'},
    '/admin/inventory/expiry-report': {'admin','manager','inventory_manager'},
    '/admin/inventory/reorder-suggestions': {'admin','manager','inventory_manager'},
    '/admin/suppliers': {'admin','manager','accountant'},
    '/admin/purchase-orders': {'admin','manager','accountant'},
    '/admin/grn': {'admin','manager','accountant'},
    '/admin/hr/employees': {'admin','manager','hr'},
    '/admin/departments': {'admin','manager','hr'},
    '/admin/hr/attendance': {'admin','manager','hr'},
    '/admin/hr/leaves': {'admin','manager','hr'},
    '/admin/hr/salary': {'admin','manager','hr','accountant'},
    '/admin/analytics': {'admin','manager'},
    '/admin/ai-dashboard': {'admin','manager'},
    '/admin/predictions': {'admin','manager'},
    '/admin/recommendations': {'admin','manager','employee','cashier'},
    '/admin/bi/store-access': {'admin','super_admin'},
    '/admin/reports': {'admin','manager'},
    '/admin/inventory/stock-report': {'admin','manager','inventory_manager'},
    '/admin/billing/reports/tax': {'admin','manager','accountant'},
    '/admin/users': {'admin','super_admin'},
    '/admin/permissions': {'admin','super_admin'},
    '/admin/activity-logs': {'admin','super_admin','hr','accountant'},
    '/admin/login-history': {'admin','super_admin','hr'},
    '/admin/sessions': {'admin','super_admin'},
    '/admin/system/health': {'admin','super_admin'},
    '/admin/system/logs': {'admin','super_admin'},
    '/admin/system/backups': {'admin','super_admin'},
    '/admin/system/restore': {'admin','super_admin'},
    '/admin/settings': {'admin','super_admin'},
    '/account/security': {'admin','manager','cashier','inventory_manager','hr','accountant','employee','super_admin'},
}
_ACTION_ROLES = {
    '/admin/add-product': {'admin','manager'}, '/admin/add-customer': {'admin','manager','employee'},
    '/admin/billing/pos': {'admin','manager','employee','cashier'}, '/admin/inventory/stock-in': {'admin','manager','employee','inventory_manager'},
    '/admin/inventory/stock-out': {'admin','manager','employee','inventory_manager'}, '/admin/purchase-orders/add': {'admin','manager','accountant'},
    '/admin/grn/add': {'admin','manager','accountant'}, '/admin/reports': {'admin','manager'},
    '/admin/add-employee': {'admin','manager'}, '/admin/add-supplier': {'admin','manager','accountant'},
}

def _visible_url(url, role, mapping):
    allowed = mapping.get(url)
    return role == 'super_admin' or (allowed is not None and role in allowed)

ACTIONS=[('Add Product','Create a new product','/admin/add-product','＋'),('Add Customer','Create a customer','/admin/add-customer','♙'),('New Sale','Open POS','/admin/billing/pos','₹'),('Stock In','Record incoming stock','/admin/inventory/stock-in','▣'),('Stock Out','Record outgoing stock','/admin/inventory/stock-out','▣'),('Purchase Order','Create purchase order','/admin/purchase-orders/add','🚚'),('New GRN','Receive goods','/admin/grn/add','✓'),('Generate Report','Open reporting centre','/admin/reports','▤'),('Add Employee','Create an employee','/admin/add-employee','♙'),('Add Supplier','Create a supplier','/admin/add-supplier','♧')]

def _like(q):
    return f'%{q}%'

def _run(cur, sql, params, builder, records):
    try:
        cur.execute(sql, params)
        records.extend(builder(r) for r in cur.fetchall())
    except Exception:
        # Search must remain available even when an optional/legacy table
        # differs between installations. Business pages still work normally.
        logger.exception("A global-search source query failed; remaining sources will continue.")

@global_search_bp.route('/admin/global-search')
@role_required('admin','manager','employee','cashier','inventory_manager','hr','accountant','super_admin')
def global_search():
    q=request.args.get('q','').strip()
    if not q:
        return jsonify(records=[],pages=[],actions=[])
    like=_like(q)
    records=[]
    cur=mysql.connection.cursor()
    try:
        role = session.get("role")
        if role in ("admin", "manager", "super_admin"):
            _run(cur, "SELECT product_id, product_name, sku, barcode FROM products WHERE product_name LIKE %s OR sku LIKE %s OR barcode LIKE %s ORDER BY product_id DESC LIMIT 6", (like,like,like), lambda r:{'title':r[1], 'meta':f'Product • SKU: {r[2] or "—"}', 'url':f'/admin/edit-product/{r[0]}', 'icon':'□'}, records)
        elif role == "employee":
            _run(cur, "SELECT product_id, product_name, sku, barcode FROM products WHERE product_name LIKE %s OR sku LIKE %s OR barcode LIKE %s ORDER BY product_id DESC LIMIT 6", (like,like,like), lambda r:{'title':r[1], 'meta':f'Product • SKU: {r[2] or "—"}', 'url':'/admin/products', 'icon':'□'}, records)
        if role in ("admin", "manager", "employee", "super_admin"):
            _run(cur, "SELECT customer_id, customer_name, phone, email FROM customers WHERE customer_name LIKE %s OR phone LIKE %s OR email LIKE %s ORDER BY customer_id DESC LIMIT 6", (like,like,like), lambda r:{'title':r[1], 'meta':f'Customer • {r[2] or r[3] or "—"}', 'url':(f'/employee/edit-customer/{r[0]}' if role == 'employee' else f'/admin/edit-customer/{r[0]}'), 'icon':'♙'}, records)
        if role in ("admin", "manager", "accountant", "super_admin"):
            _run(cur, "SELECT supplier_id, supplier_name, phone, email FROM suppliers WHERE supplier_name LIKE %s OR phone LIKE %s OR email LIKE %s ORDER BY supplier_id DESC LIMIT 6", (like,like,like), lambda r:{'title':r[1], 'meta':f'Supplier • {r[2] or r[3] or "—"}', 'url':f'/admin/suppliers/{r[0]}/profile', 'icon':'♧'}, records)
        # User-account discovery is administrative data. Do not expose it to
        # operational roles through the global search endpoint.
        if role in ("admin", "super_admin"):
            _run(cur, "SELECT user_id, full_name, email, role FROM users WHERE full_name LIKE %s OR email LIKE %s OR role LIKE %s ORDER BY user_id DESC LIMIT 6", (like,like,like), lambda r:{'title':r[1], 'meta':f'User • {r[2]} • {r[3]}', 'url':f'/admin/edit-user/{r[0]}', 'icon':'♙'}, records)
        if role in ("admin", "manager", "hr", "super_admin"):
            _run(cur, "SELECT employee_id, employee_name, email, designation FROM employees WHERE employee_name LIKE %s OR email LIKE %s OR designation LIKE %s ORDER BY employee_id DESC LIMIT 6", (like,like,like), lambda r:{'title':r[1], 'meta':f'Employee • {r[3] or "Staff"} • {r[2] or "—"}', 'url':f'/admin/hr/employees/{r[0]}', 'icon':'♙'}, records)
        if role in ("admin", "manager", "super_admin"):
            _run(cur, "SELECT category_id, category_name FROM categories WHERE category_name LIKE %s ORDER BY category_id DESC LIMIT 6", (like,), lambda r:{'title':r[1], 'meta':'Category', 'url':f'/admin/categories', 'icon':'◇'}, records)
        if role in ("admin", "manager", "employee", "cashier", "super_admin"):
            _run(cur, "SELECT sale_id, invoice_number, total_amount, status FROM sales WHERE invoice_number LIKE %s OR CAST(sale_id AS CHAR) LIKE %s OR status LIKE %s ORDER BY sale_id DESC LIMIT 6", (like,like,like), lambda r:{'title':r[1] or f'Sale #{r[0]}', 'meta':f'Sale • ₹{r[2]} • {r[3]}', 'url':f'/admin/billing/invoice/{r[0]}', 'icon':'₹'}, records)
        if role in ("admin", "manager", "accountant", "super_admin"):
            _run(cur, "SELECT po_id, po_number, status, total_amount FROM purchase_orders WHERE po_number LIKE %s OR status LIKE %s ORDER BY po_id DESC LIMIT 6", (like,like), lambda r:{'title':r[1] or f'PO #{r[0]}', 'meta':f'Purchase Order • ₹{r[3]} • {r[2]}', 'url':f'/admin/purchase-orders/{r[0]}', 'icon':'▭'}, records)
            _run(cur, "SELECT grn_id, grn_number, total_amount FROM grn WHERE grn_number LIKE %s OR CAST(grn_id AS CHAR) LIKE %s ORDER BY grn_id DESC LIMIT 6", (like,like), lambda r:{'title':r[1] or f'GRN #{r[0]}', 'meta':f'GRN • ₹{r[2]}', 'url':f'/admin/grn/{r[0]}', 'icon':'✓'}, records)
    finally:
        cur.close()
    ql=q.lower()
    tokens=[t for t in ql.split() if t]
    def matches(item):
        hay=(item[0]+' '+item[1]).lower()
        return all(t in hay for t in tokens)
    visible_pages=[]
    for t,g,u,i in PAGES:
        if not matches((t,g)) or not _visible_url(u, role, _PAGE_ROLES):
            continue
        if role == 'employee' and u == '/admin/dashboard':
            u = '/employee/dashboard'
        visible_pages.append({'title':t,'meta':f'Page • {g}','url':u,'icon':i})
    if role == 'employee' and matches(('Dashboard','Overview')):
        visible_pages.insert(0, {'title':'Dashboard','meta':'Page • Overview','url':'/employee/dashboard','icon':'⌂'})
    pages=visible_pages[:8]
    actions=[{'title':t,'meta':f'Action • {m}','url':u,'icon':i} for t,m,u,i in ACTIONS if matches((t,m)) and _visible_url(u, role, _ACTION_ROLES)][:6]
    return jsonify(records=records[:20],pages=pages,actions=actions)


@global_search_bp.route('/admin/notifications')
@role_required('admin','manager','employee','cashier','inventory_manager','hr','accountant','super_admin')
def notifications():
    """Return only live, database-derived alerts; never fabricate notification records."""
    role = session.get('role')
    notifications = []
    cur = mysql.connection.cursor()
    try:
        if role in ('admin','manager','inventory_manager','employee','cashier'):
            try:
                cur.execute("""SELECT COUNT(*) FROM v_inventory_full WHERE current_stock <= minimum_stock""")
                low = int(cur.fetchone()[0] or 0)
                if low:
                    notifications.append({'title': f'{low} low-stock item(s) need attention', 'meta': 'Inventory', 'url': '/admin/low-stock'})
            except Exception:
                logger.exception("Could not load low-stock notifications.")
        if role in ('admin','manager','hr','super_admin'):
            try:
                cur.execute("SELECT COUNT(*) FROM leave_requests WHERE status='pending'")
                pending = int(cur.fetchone()[0] or 0)
                if pending:
                    notifications.append({'title': f'{pending} leave request(s) pending', 'meta': 'People & HR', 'url': '/admin/hr/leaves?status=pending'})
            except Exception:
                logger.exception("Could not load pending-leave notifications.")
    finally:
        cur.close()
    return jsonify(notifications=notifications, count=len(notifications))
