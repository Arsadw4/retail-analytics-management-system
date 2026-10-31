"""
ai/business_intelligence.py
Profitability ranking, ABC (Pareto) inventory analysis, fast/slow
moving products, dead stock detection, and category sales trend.
Standard retail-analytics techniques computed directly from Phases
1-7's existing tables/views.
"""

from database.db import mysql
from ai._stats import linear_regression
from core.cache import cached

DEAD_STOCK_DAYS = 90
FAST_SLOW_WINDOW_DAYS = 30


def profitability_analysis(limit=None):
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT product_id, product_name, SUM(revenue) AS revenue, SUM(profit) AS profit,
               CASE WHEN SUM(revenue) > 0 THEN ROUND(SUM(profit)/SUM(revenue)*100, 2) ELSE 0 END AS margin_pct
        FROM v_daily_product_sales
        GROUP BY product_id, product_name
        ORDER BY profit DESC
    """)
    data = cur.fetchall()
    cur.close()
    return data[:limit] if limit else data


@cached(ttl_seconds=180)
def abc_analysis():
    """
    Classic 80/15/5 Pareto classification: products contributing the
    top 80% of cumulative revenue are 'A' (highest priority for stock
    availability and vendor negotiation), the next 15% are 'B', and
    the remaining 5% are 'C'.
    """
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT product_id, product_name, SUM(revenue) AS revenue
        FROM v_daily_product_sales
        GROUP BY product_id, product_name
        ORDER BY revenue DESC
    """)
    rows = cur.fetchall()
    cur.close()

    total_revenue = sum(float(r[2]) for r in rows)
    if total_revenue <= 0:
        return []

    results = []
    running = 0.0
    for product_id, name, revenue in rows:
        running += float(revenue)
        cumulative_pct = running / total_revenue * 100
        if cumulative_pct <= 80:
            grade = "A"
        elif cumulative_pct <= 95:
            grade = "B"
        else:
            grade = "C"
        results.append({
            "product_id": product_id, "product_name": name,
            "revenue": float(revenue), "cumulative_pct": round(cumulative_pct, 1),
            "grade": grade
        })
    return results


def fast_slow_movers(window_days=FAST_SLOW_WINDOW_DAYS, limit=10):
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT product_id, product_name, SUM(units_sold) AS units
        FROM v_daily_product_sales
        WHERE sale_day >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
        GROUP BY product_id, product_name
        ORDER BY units DESC
    """, (window_days,))
    rows = cur.fetchall()
    cur.close()

    fast = rows[:limit]
    slow = list(reversed(rows[-limit:])) if len(rows) > limit else list(reversed(rows))
    return {
        "fast_moving": [{"product_id": r[0], "product_name": r[1], "units_sold": r[2]} for r in fast],
        "slow_moving": [{"product_id": r[0], "product_name": r[1], "units_sold": r[2]} for r in slow]
    }


def dead_stock(days=DEAD_STOCK_DAYS):
    """Active products with stock on hand but zero sales in the window."""
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT p.product_id, p.product_name, p.stock_quantity,
               p.stock_quantity * p.purchase_price AS tied_up_value
        FROM products p
        WHERE p.is_active = TRUE AND p.stock_quantity > 0
          AND p.product_id NOT IN (
              SELECT DISTINCT product_id FROM v_daily_product_sales
              WHERE sale_day >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
          )
        ORDER BY tied_up_value DESC
    """, (days,))
    data = cur.fetchall()
    cur.close()
    return data


def sales_trend_by_category(history_days=90):
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT category_id, sale_day, SUM(revenue)
        FROM v_daily_product_sales
        WHERE sale_day >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
        GROUP BY category_id, sale_day
        ORDER BY category_id, sale_day
    """, (history_days,))
    rows = cur.fetchall()

    cur.execute("SELECT category_id, category_name FROM categories")
    names = dict(cur.fetchall())
    cur.close()

    by_category = {}
    for category_id, day, revenue in rows:
        by_category.setdefault(category_id, []).append(float(revenue))

    results = []
    for category_id, values in by_category.items():
        x = list(range(len(values)))
        slope, _ = linear_regression(x, values)
        results.append({
            "category_id": category_id,
            "category_name": names.get(category_id, "Uncategorized"),
            "total_revenue": round(sum(values), 2),
            "trend": "growing" if slope > 0.5 else "declining" if slope < -0.5 else "stable"
        })
    return sorted(results, key=lambda r: r["total_revenue"], reverse=True)
