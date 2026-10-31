"""
ai/sales_prediction.py
Daily/weekly/monthly sales forecasting and seasonal trend detection.
Method: ordinary least-squares linear trend over trailing history
(see ai/_stats.py) -- a standard, explainable baseline forecasting
approach. Not a neural net / deep learning model
see
AI_SETUP_GUIDE.md for why and how to upgrade if your data volume
later justifies it.
"""

from database.db import mysql
from ai._stats import forecast_next, linear_regression


def _completed_sales_by_day(days_back=90):
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT DATE(sale_date) AS d, COALESCE(SUM(total_amount),0)
        FROM sales
        WHERE status='completed' AND sale_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
        GROUP BY DATE(sale_date)
        ORDER BY d ASC
    """, (days_back,))
    data = cur.fetchall()
    cur.close()
    return data


def forecast_daily(days_ahead=7, history_days=90):
    rows = _completed_sales_by_day(history_days)
    if not rows:
        return {"history": [], "forecast": [], "trend": "insufficient_data"}

    y = [float(r[1]) for r in rows]
    x = list(range(len(y)))
    slope, _ = linear_regression(x, y)
    forecast = forecast_next(x, y, days_ahead)

    return {
        "history": [{"date": str(r[0]), "revenue": float(r[1])} for r in rows],
        "forecast": [round(max(v, 0), 2) for v in forecast],
        "trend": "growing" if slope > 0.5 else "declining" if slope < -0.5 else "stable"
    }


def forecast_weekly(weeks_ahead=4, history_weeks=26):
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT YEARWEEK(sale_date,3) AS yw, MIN(DATE(sale_date)) AS week_start,
               COALESCE(SUM(total_amount),0)
        FROM sales
        WHERE status='completed' AND sale_date >= DATE_SUB(CURDATE(), INTERVAL %s WEEK)
        GROUP BY YEARWEEK(sale_date,3)
        ORDER BY yw ASC
    """, (history_weeks,))
    rows = cur.fetchall()
    cur.close()

    if not rows:
        return {"history": [], "forecast": [], "trend": "insufficient_data"}

    y = [float(r[2]) for r in rows]
    x = list(range(len(y)))
    slope, _ = linear_regression(x, y)
    forecast = forecast_next(x, y, weeks_ahead)

    return {
        "history": [{"week_start": str(r[1]), "revenue": float(r[2])} for r in rows],
        "forecast": [round(max(v, 0), 2) for v in forecast],
        "trend": "growing" if slope > 0.5 else "declining" if slope < -0.5 else "stable"
    }


def forecast_monthly(months_ahead=3, history_months=12):
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT DATE_FORMAT(sale_date,'%%Y-%%m') AS ym, COALESCE(SUM(total_amount),0)
        FROM sales
        WHERE status='completed' AND sale_date >= DATE_SUB(CURDATE(), INTERVAL %s MONTH)
        GROUP BY DATE_FORMAT(sale_date,'%%Y-%%m')
        ORDER BY ym ASC
    """, (history_months,))
    rows = cur.fetchall()
    cur.close()

    if not rows:
        return {"history": [], "forecast": [], "trend": "insufficient_data"}

    y = [float(r[1]) for r in rows]
    x = list(range(len(y)))
    slope, _ = linear_regression(x, y)
    forecast = forecast_next(x, y, months_ahead)

    return {
        "history": [{"month": r[0], "revenue": float(r[1])} for r in rows],
        "forecast": [round(max(v, 0), 2) for v in forecast],
        "trend": "growing" if slope > 0.5 else "declining" if slope < -0.5 else "stable"
    }


def seasonal_trend(history_days=365):
    """
    Average revenue by day-of-week and by calendar month, to surface
    recurring seasonal patterns (e.g. "Saturdays outperform weekdays
    by 40%", "December is the strongest month").
    """
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT DAYNAME(sale_date), AVG(daily_total) FROM (
            SELECT DATE(sale_date) AS sale_date, SUM(total_amount) AS daily_total
            FROM sales
            WHERE status='completed' AND sale_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
            GROUP BY DATE(sale_date)
        ) daily
        GROUP BY DAYNAME(sale_date)
        ORDER BY AVG(daily_total) DESC
    """, (history_days,))
    by_weekday = cur.fetchall()

    cur.execute("""
        SELECT month_name, AVG(monthly_total) FROM (
            SELECT DATE_FORMAT(sale_date,'%%Y-%%m') AS ym,
                   MONTHNAME(MIN(sale_date)) AS month_name,
                   SUM(total_amount) AS monthly_total
            FROM sales
            WHERE status='completed' AND sale_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
            GROUP BY DATE_FORMAT(sale_date,'%%Y-%%m')
        ) monthly
        GROUP BY month_name
        ORDER BY AVG(monthly_total) DESC
    """, (history_days,))
    by_month = cur.fetchall()
    cur.close()

    return {
        "by_weekday": [{"day": r[0], "avg_revenue": round(float(r[1] or 0), 2)} for r in by_weekday],
        "by_month": [{"month": r[0], "avg_revenue": round(float(r[1] or 0), 2)} for r in by_month],
    }
