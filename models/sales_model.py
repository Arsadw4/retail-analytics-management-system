from database.db import mysql, get_db_cursor
from models.stock_movement_model import StockMovement


class Sale:

    @staticmethod
    def get_customers():

        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT customer_id, customer_name
            FROM customers
            ORDER BY customer_name
        """)

        customers = cur.fetchall()

        cur.close()

        return customers

    @staticmethod
    def get_products():

        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT
                product_id,
                product_name,
                selling_price,
                stock_quantity
            FROM products
            ORDER BY product_name
        """)

        products = cur.fetchall()

        cur.close()

        return products

    @staticmethod
    def create_sale(
        customer_id,
        user_id,
        product_id,
        quantity
    ):
        """
        Before: this read the product's stock, decided in Python
        whether there was enough, then issued a separate UPDATE --
        with no row lock held in between. Two employees selling the
        last unit of the same product at the same moment could BOTH
        pass the stock check (each reads stock=1 before either
        writes), and both sales would go through, leaving
        stock_quantity at -1. That's a classic
        check-then-act race condition.

        Fix: `SELECT ... FOR UPDATE` takes a row lock on the product
        the moment it's read, inside one transaction (one
        get_db_cursor block). A second concurrent create_sale() for
        the same product_id blocks until the first transaction
        commits or rolls back, so the stock check and the stock
        decrement are now atomic with respect to each other --
        overselling is no longer possible.
        """
        if quantity is None or quantity <= 0:
            return False

        with get_db_cursor() as cur:
            cur.execute("""
                SELECT
                    purchase_price,
                    selling_price,
                    stock_quantity
                FROM products
                WHERE product_id=%s
                FOR UPDATE
            """, (product_id,))

            product = cur.fetchone()

            if product is None:
                return False

            purchase_price = float(product[0])
            selling_price = float(product[1])
            stock = int(product[2])

            if quantity > stock:
                return False

            subtotal = selling_price * quantity
            profit = (selling_price - purchase_price) * quantity

            cur.execute("""
                INSERT INTO sales
                (
                    customer_id,
                    user_id,
                    total_amount,
                    profit_amount
                )
                VALUES
                (
                    %s,%s,%s,%s
                )
            """, (
                customer_id,
                user_id,
                subtotal,
                profit
            ))

            sale_id = cur.lastrowid

            cur.execute("""
                INSERT INTO sale_items
                (
                    sale_id,
                    product_id,
                    quantity,
                    unit_price,
                    subtotal
                )
                VALUES
                (
                    %s,%s,%s,%s,%s
                )
            """, (
                sale_id,
                product_id,
                quantity,
                selling_price,
                subtotal
            ))

            cur.execute("""
                UPDATE products
                SET stock_quantity = stock_quantity - %s
                WHERE product_id=%s
            """, (
                quantity,
                product_id
            ))

            StockMovement.log_sale_movement(cur, product_id, quantity, sale_id, user_id)

            return True

    @staticmethod
    def get_all_sales():

        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT
                s.sale_id,
                c.customer_name,
                s.total_amount,
                s.profit_amount,
                s.sale_date
            FROM sales s
            LEFT JOIN customers c
            ON s.customer_id = c.customer_id
            ORDER BY s.sale_id DESC
        """)

        sales = cur.fetchall()

        cur.close()

        return sales

    @staticmethod
    def total_sales_amount():

        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT COALESCE(SUM(total_amount),0)
            FROM sales
            WHERE status='completed' 
        """)

        total = cur.fetchone()[0]

        cur.close()

        return total

    @staticmethod
    def monthly_sales_totals():
        """Return actual completed sales totals for each month of the current year.

        This is a read-only dashboard/reporting query
        it does not alter any
        sales or inventory business rules. Missing months are filled with zero
        by the dashboard template so the chart never invents sales activity.
        """
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT MONTH(sale_date) AS month_no,
                   COALESCE(SUM(total_amount), 0) AS total_amount
            FROM sales
            WHERE status='completed'
              AND YEAR(sale_date)=YEAR(CURDATE())
            GROUP BY MONTH(sale_date)
            ORDER BY MONTH(sale_date)
        """)
        rows = cur.fetchall()
        cur.close()
        totals = {int(row[0]): float(row[1] or 0) for row in rows}
        return [totals.get(month, 0.0) for month in range(1, 13)]

    @staticmethod
    def total_profit():

        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT COALESCE(SUM(profit_amount),0)
            FROM sales
            WHERE status='completed' AND profit_amount > 0
        """)

        total = cur.fetchone()[0]

        cur.close()

        return total

    @staticmethod
    def total_loss():

        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT ABS(COALESCE(SUM(profit_amount),0))
            FROM sales
            WHERE status='completed' AND profit_amount < 0
        """)

        total = cur.fetchone()[0]

        cur.close()

        return total

    @staticmethod
    def get_sale_by_id(sale_id):

        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT
                s.sale_id,
                c.customer_name,
                s.total_amount,
                s.profit_amount,
                s.sale_date
            FROM sales s
            LEFT JOIN customers c
            ON s.customer_id = c.customer_id
            WHERE s.sale_id=%s
        """, (sale_id,))

        sale = cur.fetchone()

        cur.close()

        return sale

    @staticmethod
    def get_sale_items(sale_id):

        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT
                p.product_name,
                si.quantity,
                si.unit_price,
                si.subtotal
            FROM sale_items si
            LEFT JOIN products p
            ON si.product_id = p.product_id
            WHERE si.sale_id=%s
        """, (sale_id,))

        items = cur.fetchall()

        cur.close()

        return items
    

    @staticmethod
    def dashboard_metrics(start_date=None, end_date=None):
        """Return dashboard sales metrics for an optional inclusive date range."""
        cur = mysql.connection.cursor()
        where = ["status='completed'"]
        params = []
        if start_date:
            where.append("sale_date >= %s")
            params.append(start_date)
        if end_date:
            where.append("sale_date < DATE_ADD(%s, INTERVAL 1 DAY)")
            params.append(end_date)
        condition = " AND ".join(where)
        cur.execute(f"""
            SELECT
                COALESCE(SUM(total_amount),0),
                COALESCE(SUM(CASE WHEN profit_amount > 0 THEN profit_amount ELSE 0 END),0),
                COALESCE(SUM(CASE WHEN profit_amount < 0 THEN ABS(profit_amount) ELSE 0 END),0),
                COUNT(*)
            FROM sales
            WHERE {condition}
        """, tuple(params))
        row = cur.fetchone()
        cur.close()
        return {
            'sales': float(row[0] or 0),
            'profit': float(row[1] or 0),
            'loss': float(row[2] or 0),
            'transactions': int(row[3] or 0),
        }

    @staticmethod
    def dashboard_series(start_date, end_date, granularity='month'):
        """Return database-backed chart labels/values for the dashboard."""
        cur = mysql.connection.cursor()
        if granularity == 'day':
            key_expr = "DATE(sale_date)"
        else:
            key_expr = "DATE_FORMAT(sale_date, '%%Y-%%m')"
        cur.execute(f"""
            SELECT {key_expr} AS bucket, COALESCE(SUM(total_amount),0)
            FROM sales
            WHERE status='completed' AND sale_date >= %s
              AND sale_date < DATE_ADD(%s, INTERVAL 1 DAY)
            GROUP BY bucket
            ORDER BY bucket
        """, (start_date, end_date))
        rows = cur.fetchall()
        cur.close()
        return [(str(r[0]), float(r[1] or 0)) for r in rows]

    @staticmethod
    def recent_sales_for_range(start_date=None, end_date=None, limit=5):
        cur = mysql.connection.cursor()
        where = ["s.status='completed'"]
        params = []
        if start_date:
            where.append("s.sale_date >= %s")
            params.append(start_date)
        if end_date:
            where.append("s.sale_date < DATE_ADD(%s, INTERVAL 1 DAY)")
            params.append(end_date)
        params.append(int(limit))
        cur.execute(f"""
            SELECT s.sale_id, s.sale_date, COALESCE(c.customer_name,'Walk-in Customer'),
                   COALESCE(COUNT(si.item_id),0), s.total_amount, s.status
            FROM sales s
            LEFT JOIN customers c ON c.customer_id=s.customer_id
            LEFT JOIN sale_items si ON si.sale_id=s.sale_id
            WHERE {' AND '.join(where)}
            GROUP BY s.sale_id, s.sale_date, c.customer_name, s.total_amount, s.status
            ORDER BY s.sale_date DESC, s.sale_id DESC
            LIMIT %s
        """, tuple(params))
        rows=cur.fetchall()
        cur.close()
        return rows

    @staticmethod
    def top_products_for_range(start_date=None, end_date=None, limit=5):
        cur=mysql.connection.cursor()
        where=["s.status='completed'"]
        params=[]
        if start_date: where.append("s.sale_date >= %s"); params.append(start_date)
        if end_date: where.append("s.sale_date < DATE_ADD(%s, INTERVAL 1 DAY)"); params.append(end_date)
        params.append(int(limit))
        cur.execute(f"""
            SELECT p.product_name, COALESCE(SUM(si.quantity),0) AS units,
                   COALESCE(SUM(si.subtotal),0) AS revenue
            FROM sale_items si
            JOIN sales s ON s.sale_id=si.sale_id
            JOIN products p ON p.product_id=si.product_id
            WHERE {' AND '.join(where)}
            GROUP BY p.product_id, p.product_name
            ORDER BY units DESC, revenue DESC
            LIMIT %s
        """, tuple(params))
        rows=cur.fetchall()
        cur.close()
        return rows

    @staticmethod
    def get_employee_sales(user_id):

        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT
                sale_id,
                total_amount,
                profit_amount,
                sale_date
            FROM sales
            WHERE user_id=%s
            ORDER BY sale_id DESC
        """,(user_id,))

        sales = cur.fetchall()

        cur.close()

        return sales
