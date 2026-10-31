from database.db import get_db_cursor, mysql


class StockMovement:

    @staticmethod
    def stock_in(product_id, quantity, warehouse_id, reason, performed_by, batch_id=None):
        if quantity is None or quantity <= 0:
            return False
        if warehouse_id is not None:
            with get_db_cursor(commit=False) as check_cur:
                check_cur.execute("SELECT warehouse_id FROM warehouses WHERE warehouse_id=%s AND is_active=TRUE", (warehouse_id,))
                if check_cur.fetchone() is None:
                    return False

        with get_db_cursor() as cur:
            cur.execute(
                "SELECT stock_quantity FROM products WHERE product_id=%s FOR UPDATE",
                (product_id,)
            )
            row = cur.fetchone()
            if row is None:
                return False

            cur.execute(
                "UPDATE products SET stock_quantity = stock_quantity + %s WHERE product_id=%s",
                (quantity, product_id)
            )

            cur.execute("""
                INSERT INTO stock_movements
                    (product_id, warehouse_id, movement_type, quantity,
                     reason, reference_type, reference_id, performed_by)
                VALUES (%s, %s, 'in', %s, %s, 'manual', %s, %s)
            """, (product_id, warehouse_id, quantity, reason, batch_id, performed_by))

            cur.execute("""
                UPDATE inventory SET last_restock_date = CURDATE()
                WHERE product_id=%s
            """, (product_id,))

            return True

    @staticmethod
    def stock_out(product_id, quantity, warehouse_id, reason, performed_by):
        if quantity is None or quantity <= 0:
            return False
        if warehouse_id is not None:
            with get_db_cursor(commit=False) as check_cur:
                check_cur.execute("SELECT warehouse_id FROM warehouses WHERE warehouse_id=%s AND is_active=TRUE", (warehouse_id,))
                if check_cur.fetchone() is None:
                    return False

        with get_db_cursor() as cur:
            cur.execute(
                "SELECT stock_quantity FROM products WHERE product_id=%s FOR UPDATE",
                (product_id,)
            )
            row = cur.fetchone()
            if row is None:
                return False

            current_stock = int(row[0])
            if quantity > current_stock:
                return False

            cur.execute(
                "UPDATE products SET stock_quantity = stock_quantity - %s WHERE product_id=%s",
                (quantity, product_id)
            )

            cur.execute("""
                INSERT INTO stock_movements
                    (product_id, warehouse_id, movement_type, quantity,
                     reason, reference_type, performed_by)
                VALUES (%s, %s, 'out', %s, %s, 'manual', %s)
            """, (product_id, warehouse_id, quantity, reason, performed_by))

            return True

    @staticmethod
    def log_sale_movement(cur, product_id, quantity, sale_id, performed_by):
        """
        Called from sales_model.create_sale() inside its existing
        transaction/cursor -- adds an audit row without altering the
        stock-locking logic already fixed in Phase 2.
        """
        cur.execute("""
            INSERT INTO stock_movements
                (product_id, movement_type, quantity, reference_type, reference_id, performed_by)
            VALUES (%s, 'sale', %s, 'sale', %s, %s)
        """, (product_id, quantity, sale_id, performed_by))

    @staticmethod
    def get_history(product_id=None, movement_type=None, limit=200):
        cur = mysql.connection.cursor()

        query = """
            SELECT
                sm.movement_id, p.product_name, sm.movement_type,
                sm.quantity, sm.reason, sm.reference_type,
                w.warehouse_name, u.full_name, sm.created_at
            FROM stock_movements sm
            JOIN products p ON sm.product_id = p.product_id
            LEFT JOIN warehouses w ON sm.warehouse_id = w.warehouse_id
            LEFT JOIN users u ON sm.performed_by = u.user_id
            WHERE 1=1
        """
        params = []

        if product_id:
            query += " AND sm.product_id=%s"
            params.append(product_id)

        if movement_type:
            query += " AND sm.movement_type=%s"
            params.append(movement_type)

        query += " ORDER BY sm.created_at DESC LIMIT %s"
        params.append(limit)

        cur.execute(query, tuple(params))
        data = cur.fetchall()
        cur.close()
        return data
