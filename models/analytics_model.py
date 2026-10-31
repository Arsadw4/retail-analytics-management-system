from database.db import mysql


class Analytics:
    """Read-only business analytics backed by completed sales and live inventory."""

    @staticmethod
    def best_product():
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT p.product_name, COALESCE(SUM(si.subtotal), 0) AS revenue
            FROM sale_items si
            JOIN sales s ON s.sale_id = si.sale_id AND s.status = 'completed'
            JOIN products p ON p.product_id = si.product_id
            GROUP BY p.product_id, p.product_name
            ORDER BY revenue DESC
            LIMIT 1
        """)
        row = cur.fetchone()
        cur.close()
        return row[0] if row else "No Sales Yet"

    @staticmethod
    def worst_product():
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT p.product_name, COALESCE(SUM(si.subtotal), 0) AS revenue
            FROM sale_items si
            JOIN sales s ON s.sale_id = si.sale_id AND s.status = 'completed'
            JOIN products p ON p.product_id = si.product_id
            GROUP BY p.product_id, p.product_name
            ORDER BY revenue ASC
            LIMIT 1
        """)
        row = cur.fetchone()
        cur.close()
        return row[0] if row else "No Sales Yet"

    @staticmethod
    def top_customer():
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT c.customer_name, COALESCE(SUM(s.total_amount), 0) AS spend
            FROM sales s
            JOIN customers c ON c.customer_id = s.customer_id
            WHERE s.status = 'completed' AND s.customer_id IS NOT NULL
            GROUP BY c.customer_id, c.customer_name
            ORDER BY spend DESC
            LIMIT 1
        """)
        row = cur.fetchone()
        cur.close()
        return row[0] if row else "No Customer Sales Yet"

    @staticmethod
    def low_stock_alert():
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM v_inventory_full
            WHERE current_stock <= minimum_stock
        """)
        count = cur.fetchone()[0]
        cur.close()
        return f"{count} Product(s) Need Restock"

    @staticmethod
    def revenue_prediction():
        """Return current completed revenue for backward-compatible callers."""
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT COALESCE(SUM(total_amount), 0)
            FROM sales
            WHERE status = 'completed'
        """)
        value = cur.fetchone()[0]
        cur.close()
        return value or 0

    @staticmethod
    def total_products():
        cur = mysql.connection.cursor()
        cur.execute("SELECT COUNT(*) FROM products WHERE is_active = TRUE")
        total = cur.fetchone()[0]
        cur.close()
        return total

    @staticmethod
    def total_customers():
        cur = mysql.connection.cursor()
        cur.execute("SELECT COUNT(*) FROM customers")
        total = cur.fetchone()[0]
        cur.close()
        return total

    @staticmethod
    def total_inventory():
        cur = mysql.connection.cursor()
        cur.execute("SELECT COUNT(*) FROM v_inventory_full")
        total = cur.fetchone()[0]
        cur.close()
        return total

    @staticmethod
    def total_stock():
        cur = mysql.connection.cursor()
        cur.execute("SELECT COALESCE(SUM(current_stock), 0) FROM v_inventory_full")
        total = cur.fetchone()[0]
        cur.close()
        return total or 0

    @staticmethod
    def inventory_value():
        cur = mysql.connection.cursor()
        cur.execute("SELECT COALESCE(SUM(stock_value), 0) FROM v_inventory_full")
        total = cur.fetchone()[0]
        cur.close()
        return total or 0

    @staticmethod
    def completed_sales_count():
        cur = mysql.connection.cursor()
        cur.execute("SELECT COUNT(*) FROM sales WHERE status = 'completed'")
        total = cur.fetchone()[0]
        cur.close()
        return total

    @staticmethod
    def completed_revenue():
        return Analytics.revenue_prediction()

    @staticmethod
    def completed_profit():
        cur = mysql.connection.cursor()
        cur.execute("SELECT COALESCE(SUM(profit_amount), 0) FROM sales WHERE status = 'completed'")
        value = cur.fetchone()[0]
        cur.close()
        return value or 0
