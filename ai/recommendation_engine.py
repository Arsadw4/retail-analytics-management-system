"""
ai/recommendation_engine.py
Frequently-bought-together / cross-sell / upsell / per-customer
recommendations. Method: co-purchase frequency counting (a standard,
explainable market-basket technique) and category affinity -- not a
trained collaborative-filtering model. See AI_SETUP_GUIDE.md.
"""

from database.db import mysql


def frequently_bought_together(product_id, limit=5):
    """
    Products most often appearing in the same completed sale as
    `product_id`, ranked by co-occurrence count.
    """
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT si2.product_id, p.product_name, COUNT(*) AS times_bought_together
        FROM sale_items si1
        JOIN sale_items si2 ON si1.sale_id = si2.sale_id AND si2.product_id != si1.product_id
        JOIN sales s ON si1.sale_id = s.sale_id
        JOIN products p ON si2.product_id = p.product_id
        WHERE si1.product_id = %s AND s.status = 'completed'
        GROUP BY si2.product_id, p.product_name
        ORDER BY times_bought_together DESC
        LIMIT %s
    """, (product_id, limit))
    data = cur.fetchall()
    cur.close()
    return data


def cross_sell_suggestions(product_id, limit=5):
    """Alias of frequently_bought_together -- kept as a distinct,
    named entry point matching the requested feature list, since
    "cross-sell" is how this is presented to a cashier at checkout
    even though the underlying computation is identical."""
    return frequently_bought_together(product_id, limit)


def upsell_suggestions(product_id, limit=5):
    """
    Other active products in the same category priced higher than
    this one, ranked by price -- the standard "upsell" pattern
    (suggest a pricier, presumably higher-margin alternative in the
    same category the customer is already browsing).
    """
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT p2.product_id, p2.product_name, p2.selling_price
        FROM products p1
        JOIN products p2 ON p1.category_id = p2.category_id AND p2.product_id != p1.product_id
        WHERE p1.product_id = %s AND p2.is_active = TRUE
          AND p2.selling_price > p1.selling_price
        ORDER BY p2.selling_price ASC
        LIMIT %s
    """, (product_id, limit))
    data = cur.fetchall()
    cur.close()
    return data


def recommend_for_customer(customer_id, limit=8):
    """
    Hybrid recommendation: products frequently bought alongside items
    this customer has already purchased, excluding products they've
    already bought, ranked by combined co-occurrence strength.
    Falls back to top sellers in the customer's most-purchased
    category if they have no purchase history yet.
    """
    cur = mysql.connection.cursor()

    cur.execute("""
        SELECT DISTINCT si.product_id
        FROM sale_items si
        JOIN sales s ON si.sale_id = s.sale_id
        WHERE s.customer_id = %s AND s.status = 'completed'
    """, (customer_id,))
    purchased = [r[0] for r in cur.fetchall()]

    if not purchased:
        cur.close()
        return top_selling_products(limit)

    placeholders = ",".join(["%s"] * len(purchased))
    cur.execute(f"""
        SELECT si2.product_id, p.product_name, COUNT(*) AS score
        FROM sale_items si1
        JOIN sale_items si2 ON si1.sale_id = si2.sale_id AND si2.product_id NOT IN ({placeholders})
        JOIN sales s ON si1.sale_id = s.sale_id
        JOIN products p ON si2.product_id = p.product_id
        WHERE si1.product_id IN ({placeholders}) AND s.status = 'completed' AND p.is_active = TRUE
        GROUP BY si2.product_id, p.product_name
        ORDER BY score DESC
        LIMIT %s
    """, tuple(purchased) + tuple(purchased) + (limit,))
    data = cur.fetchall()
    cur.close()

    if not data:
        return top_selling_products(limit)
    return data


def top_selling_products(limit=8):
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT product_id, product_name, SUM(units_sold) AS total_units
        FROM v_daily_product_sales
        GROUP BY product_id, product_name
        ORDER BY total_units DESC
        LIMIT %s
    """, (limit,))
    data = cur.fetchall()
    cur.close()
    return data
