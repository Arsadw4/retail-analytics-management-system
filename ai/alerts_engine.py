"""
ai/alerts_engine.py
Unified alert feed: low stock, overstock, slow sales, and high
demand -- computed fresh on each request (no persisted alert table,
so there's nothing to go stale or need cleanup).
"""

from database.db import mysql
from ai.demand_forecasting import calculate_velocity
from ai.business_intelligence import fast_slow_movers
from core.cache import cached

OVERSTOCK_DAYS_OF_STOCK = 120
HIGH_DEMAND_SPIKE_RATIO = 1.5   # recent 7-day velocity vs prior 30-day velocity


def low_stock_alerts():
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT product_id, product_name, current_stock, minimum_stock
        FROM v_inventory_full
        WHERE current_stock <= minimum_stock
        ORDER BY current_stock ASC
    """)
    data = cur.fetchall()
    cur.close()
    return [{"type": "low_stock", "severity": "high" if r[2] == 0 else "medium",
             "product_id": r[0], "product_name": r[1],
             "message": f"{r[1]}: {r[2]} left (reorder point {r[3]})"} for r in data]


def overstock_alerts():
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT product_id, product_name, current_stock, maximum_stock
        FROM v_inventory_full
        WHERE maximum_stock IS NOT NULL AND current_stock > maximum_stock
        ORDER BY current_stock DESC
    """)
    data = cur.fetchall()
    cur.close()
    return [{"type": "overstock", "severity": "low",
             "product_id": r[0], "product_name": r[1],
             "message": f"{r[1]}: {r[2]} units on hand, above the {r[3]} maximum"} for r in data]


def slow_sales_alerts(limit=10):
    movers = fast_slow_movers(limit=limit)
    return [{"type": "slow_sales", "severity": "low",
             "product_id": m["product_id"], "product_name": m["product_name"],
             "message": f"{m['product_name']}: only {m['units_sold']} units sold in the last 30 days"}
            for m in movers["slow_moving"] if m["units_sold"] <= 2]


def high_demand_alerts():
    cur = mysql.connection.cursor()
    cur.execute("SELECT product_id, product_name FROM products WHERE is_active=TRUE")
    products = cur.fetchall()
    cur.close()

    alerts = []
    for pid, name in products:
        recent = calculate_velocity(pid, days_back=7)
        baseline = calculate_velocity(pid, days_back=30)
        if baseline > 0 and recent >= baseline * HIGH_DEMAND_SPIKE_RATIO and recent >= 1:
            alerts.append({
                "type": "high_demand", "severity": "medium",
                "product_id": pid, "product_name": name,
                "message": f"{name}: demand up to {recent:.1f}/day "
                           f"(was {baseline:.1f}/day) -- consider restocking ahead of trend"
            })
    return alerts


@cached(ttl_seconds=120)
def get_all_alerts():
    alerts = []
    alerts += low_stock_alerts()
    alerts += overstock_alerts()
    alerts += slow_sales_alerts()
    alerts += high_demand_alerts()
    severity_order = {"high": 0, "medium": 1, "low": 2}
    return sorted(alerts, key=lambda a: severity_order.get(a["severity"], 3))
