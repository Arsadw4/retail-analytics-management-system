"""
ai/demand_forecasting.py
Per-product demand forecasting, inventory-demand projection, AI-aware
reorder suggestions, and out-of-stock prediction. Velocity-based
(recent average daily sales rate) rather than a trained model -- see
AI_SETUP_GUIDE.md. This is deliberately additive to, not a
replacement for, Phase 3's threshold-based v_reorder_suggestions
(still used by the Inventory Dashboard) -- this module adds a
demand-aware layer alongside it.
"""

from database.db import mysql
from ai._stats import forecast_next

DEFAULT_LEAD_TIME_DAYS = 7
STOCKOUT_WARNING_DAYS = 7


def calculate_velocity(product_id, days_back=30):
    """Average units sold per day over the trailing window."""
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT COALESCE(SUM(units_sold),0)
        FROM v_daily_product_sales
        WHERE product_id=%s AND sale_day >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
    """, (product_id, days_back))
    total = cur.fetchone()[0]
    cur.close()
    return float(total) / days_back if days_back else 0.0


def product_demand_forecast(product_id, days_ahead=30, history_days=60):
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT sale_day, units_sold FROM v_daily_product_sales
        WHERE product_id=%s AND sale_day >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
        ORDER BY sale_day ASC
    """, (product_id, history_days))
    rows = cur.fetchall()
    cur.close()

    if not rows:
        return {"history": [], "forecast_total_units": 0, "daily_velocity": 0.0}

    y = [float(r[1]) for r in rows]
    x = list(range(len(y)))
    forecast = forecast_next(x, y, days_ahead)
    forecast = [max(v, 0) for v in forecast]

    return {
        "history": [{"date": str(r[0]), "units": float(r[1])} for r in rows],
        "forecast_total_units": round(sum(forecast), 1),
        "daily_velocity": round(sum(y) / len(y), 2) if y else 0.0
    }


def inventory_demand_forecast(lead_time_days=DEFAULT_LEAD_TIME_DAYS):
    """
    For every active product: current stock, recent daily velocity,
    projected days of stock remaining, and a predicted stockout date.
    """
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT product_id, product_name, stock_quantity
        FROM products WHERE is_active=TRUE
    """)
    products = cur.fetchall()
    cur.close()

    results = []
    for pid, name, stock in products:
        velocity = calculate_velocity(pid, days_back=30)
        if velocity <= 0:
            days_remaining = None
        else:
            days_remaining = round(stock / velocity, 1)

        results.append({
            "product_id": pid,
            "product_name": name,
            "current_stock": stock,
            "daily_velocity": round(velocity, 2),
            "days_of_stock_remaining": days_remaining,
            "predicted_stockout_soon": days_remaining is not None and days_remaining <= STOCKOUT_WARNING_DAYS
        })

    return results


def auto_reorder_suggestions(lead_time_days=DEFAULT_LEAD_TIME_DAYS):
    """
    Demand-aware reorder suggestion: how much stock will be consumed
    during the supplier lead time, vs. what's on hand right now.
    Complements (does not replace) Phase 3's static min/max threshold
    suggestions -- this one reacts to actual recent sales velocity.
    """
    forecast = inventory_demand_forecast(lead_time_days)
    suggestions = []
    for item in forecast:
        projected_consumption = item["daily_velocity"] * lead_time_days
        shortfall = projected_consumption - item["current_stock"]
        if shortfall > 0:
            suggestions.append({
                **item,
                "projected_consumption_during_lead_time": round(projected_consumption, 1),
                "suggested_reorder_qty": round(shortfall, 0)
            })
    return sorted(suggestions, key=lambda r: r["days_of_stock_remaining"] or 0)


def out_of_stock_prediction(warning_days=STOCKOUT_WARNING_DAYS):
    forecast = inventory_demand_forecast()
    return [f for f in forecast if f["predicted_stockout_soon"]]
