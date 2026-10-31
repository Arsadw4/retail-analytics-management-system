from database.db import mysql

class Report:
    @staticmethod
    def get_summary():
        cur=mysql.connection.cursor()
        cur.execute("SELECT COUNT(*) FROM users")
        users=cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM products")
        products=cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM customers")
        customers=cur.fetchone()[0]
        cur.execute("SELECT COALESCE(SUM(total_amount),0) FROM sales WHERE status='completed'")
        sales=cur.fetchone()[0]
        cur.execute("SELECT COALESCE(SUM(profit_amount),0) FROM sales WHERE status='completed'")
        profit=cur.fetchone()[0]
        cur.close()
        return {"users":users,"products":products,"customers":customers,"sales":sales,"profit":profit}

    @staticmethod
    def sales_rows(date_from=None,date_to=None):
        cur=mysql.connection.cursor()
        where=["s.status='completed'"]
        params=[]
        if date_from: where.append("DATE(s.sale_date)>=%s"); params.append(date_from)
        if date_to: where.append("DATE(s.sale_date)<=%s"); params.append(date_to)
        cur.execute(f"""SELECT s.sale_id,s.invoice_number,s.sale_date,COALESCE(c.customer_name,'Walk-in Customer'),s.total_amount,s.profit_amount,s.status
                       FROM sales s LEFT JOIN customers c ON c.customer_id=s.customer_id WHERE {' AND '.join(where)} ORDER BY s.sale_date DESC,s.sale_id DESC""",tuple(params)); rows=cur.fetchall(); cur.close(); return rows

    @staticmethod
    def stock_rows():
        """Return a stable report projection matching the Inventory Report/export contract."""
        cur=mysql.connection.cursor()
        cur.execute("""
            SELECT product_name, current_stock, minimum_stock, purchase_price,
                   selling_price, stock_value, status
            FROM v_inventory_full
            ORDER BY product_name
        """)
        rows=cur.fetchall()
        cur.close()
        return rows

    @staticmethod
    def sales_summary(date_from=None, date_to=None):
        cur=mysql.connection.cursor()
        where=["status='completed'"]
        params=[]
        if date_from: where.append("DATE(sale_date)>=%s"); params.append(date_from)
        if date_to: where.append("DATE(sale_date)<=%s"); params.append(date_to)
        cur.execute(f"SELECT COALESCE(SUM(total_amount),0),COALESCE(SUM(profit_amount),0),COUNT(*),COUNT(DISTINCT customer_id) FROM sales WHERE {' AND '.join(where)}",tuple(params))
        row=cur.fetchone()
        cur.close()
        return {"sales":row[0],"profit":row[1],"transactions":row[2],"customers":row[3]}


    @staticmethod
    def payment_summary(date_from=None, date_to=None):
        cur=mysql.connection.cursor()
        where=["s.status='completed'"]
        params=[]
        if date_from: where.append("DATE(s.sale_date)>=%s"); params.append(date_from)
        if date_to: where.append("DATE(s.sale_date)<=%s"); params.append(date_to)
        cur.execute(f"""
            SELECT COALESCE(sp.payment_method,'unknown'), COUNT(*), COALESCE(SUM(sp.amount),0)
            FROM sale_payments sp JOIN sales s ON s.sale_id=sp.sale_id
            WHERE {' AND '.join(where)} GROUP BY sp.payment_method ORDER BY SUM(sp.amount) DESC
        """, tuple(params)); rows=cur.fetchall(); cur.close(); return rows

    @staticmethod
    def top_products(date_from=None, date_to=None, limit=5):
        cur=mysql.connection.cursor()
        where=["s.status='completed'"]
        params=[]
        if date_from: where.append("DATE(s.sale_date)>=%s"); params.append(date_from)
        if date_to: where.append("DATE(s.sale_date)<=%s"); params.append(date_to)
        params.append(int(limit))
        cur.execute(f"""
            SELECT p.product_name, COALESCE(SUM(si.quantity),0), COALESCE(SUM(si.subtotal),0)
            FROM sale_items si JOIN sales s ON s.sale_id=si.sale_id
            JOIN products p ON p.product_id=si.product_id
            WHERE {' AND '.join(where)}
            GROUP BY p.product_id,p.product_name ORDER BY SUM(si.subtotal) DESC LIMIT %s
        """, tuple(params)); rows=cur.fetchall(); cur.close(); return rows

    @staticmethod
    def daily_sales(date_from=None, date_to=None):
        cur=mysql.connection.cursor()
        where=["s.status='completed'"]
        params=[]
        if date_from: where.append("DATE(s.sale_date)>=%s"); params.append(date_from)
        if date_to: where.append("DATE(s.sale_date)<=%s"); params.append(date_to)
        cur.execute(f"""
            SELECT DATE(s.sale_date), COALESCE(SUM(s.total_amount),0)
            FROM sales s WHERE {' AND '.join(where)}
            GROUP BY DATE(s.sale_date) ORDER BY DATE(s.sale_date)
        """, tuple(params)); rows=cur.fetchall(); cur.close(); return rows
