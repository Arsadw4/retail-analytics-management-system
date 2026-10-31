"""
ai/customer_segmentation.py
RFM-style customer segmentation, predicted CLV, churn risk, and
buying-pattern analysis. Method: recency/frequency/monetary scoring
against fixed, documented thresholds (a standard, explainable
technique real retail CRMs use) -- not a clustering model. See
AI_SETUP_GUIDE.md for tuning the thresholds or upgrading to k-means
if your customer count later justifies it.
"""

from database.db import mysql

CHURN_RISK_DAYS = 60      # no purchase in this many days => at risk
CHURN_LOST_DAYS = 120     # no purchase in this many days => considered lost
ASSUMED_CUSTOMER_LIFESPAN_YEARS = 3


def compute_rfm_segments():
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT
            c.customer_id, c.customer_name,
            DATEDIFF(CURDATE(), MAX(s.sale_date))         AS recency_days,
            COUNT(s.sale_id)                                AS frequency,
            COALESCE(SUM(s.total_amount), 0)                AS monetary
        FROM customers c
        LEFT JOIN sales s ON s.customer_id = c.customer_id AND s.status = 'completed'
        GROUP BY c.customer_id, c.customer_name
    """)
    rows = cur.fetchall()
    cur.close()

    results = []
    for customer_id, name, recency, frequency, monetary in rows:
        segment = _classify(recency, frequency, float(monetary))
        results.append({
            "customer_id": customer_id,
            "customer_name": name,
            "recency_days": recency,
            "frequency": frequency,
            "monetary": float(monetary),
            "segment": segment
        })
    return results


def _classify(recency, frequency, monetary):
    if frequency == 0 or recency is None:
        return "New / No Purchases"
    if recency <= 30 and frequency >= 5 and monetary >= 5000:
        return "Champions"
    if recency <= 60 and frequency >= 3:
        return "Loyal Customers"
    if recency > CHURN_LOST_DAYS:
        return "Lost"
    if recency > CHURN_RISK_DAYS:
        return "At Risk"
    if frequency == 1:
        return "New Customer"
    return "Regular"


def predicted_clv_all():
    """
    Predicted CLV = average order value x estimated purchase frequency
    per year x assumed customer lifespan. A standard, explainable CLV
    formula (not a trained model) -- see AI_SETUP_GUIDE.md.
    """
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT
            c.customer_id, c.customer_name,
            COUNT(s.sale_id)                                          AS orders,
            COALESCE(AVG(s.total_amount), 0)                          AS avg_order_value,
            DATEDIFF(CURDATE(), MIN(s.sale_date))                     AS customer_age_days
        FROM customers c
        LEFT JOIN sales s ON s.customer_id = c.customer_id AND s.status = 'completed'
        GROUP BY c.customer_id, c.customer_name
    """)
    rows = cur.fetchall()
    cur.close()

    results = []
    for customer_id, name, orders, avg_order_value, age_days in rows:
        if not orders or not age_days or age_days <= 0:
            predicted = 0.0
            annual_frequency = 0.0
        else:
            annual_frequency = orders / (age_days / 365.0)
            predicted = float(avg_order_value) * annual_frequency * ASSUMED_CUSTOMER_LIFESPAN_YEARS

        results.append({
            "customer_id": customer_id,
            "customer_name": name,
            "avg_order_value": round(float(avg_order_value), 2),
            "annual_purchase_frequency": round(annual_frequency, 2),
            "predicted_clv": round(predicted, 2)
        })
    return sorted(results, key=lambda r: r["predicted_clv"], reverse=True)


def churn_risk_customers():
    segments = compute_rfm_segments()
    return [s for s in segments if s["segment"] in ("At Risk", "Lost") and s["frequency"] > 0]


def buying_pattern(customer_id):
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT c.category_name, COUNT(*) AS purchases
        FROM sale_items si
        JOIN sales s ON si.sale_id = s.sale_id
        JOIN products p ON si.product_id = p.product_id
        LEFT JOIN categories c ON p.category_id = c.category_id
        WHERE s.customer_id=%s AND s.status='completed'
        GROUP BY c.category_name
        ORDER BY purchases DESC
    """, (customer_id,))
    categories = cur.fetchall()

    cur.execute("""
        SELECT DAYNAME(sale_date), COUNT(*) FROM sales
        WHERE customer_id=%s AND status='completed'
        GROUP BY DAYNAME(sale_date)
        ORDER BY COUNT(*) DESC
    """, (customer_id,))
    weekdays = cur.fetchall()

    cur.execute("""
        SELECT AVG(item_count) FROM (
            SELECT s.sale_id, SUM(si.quantity) AS item_count
            FROM sales s JOIN sale_items si ON s.sale_id = si.sale_id
            WHERE s.customer_id=%s AND s.status='completed'
            GROUP BY s.sale_id
        ) basket
    """, (customer_id,))
    avg_basket = cur.fetchone()[0]
    cur.close()

    return {
        "top_categories": [{"category": c[0] or "Uncategorized", "purchases": c[1]} for c in categories],
        "preferred_days": [{"day": d[0], "orders": d[1]} for d in weekdays],
        "avg_basket_size": round(float(avg_basket), 1) if avg_basket else 0.0
    }
