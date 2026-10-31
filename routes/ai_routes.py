from flask import Blueprint, render_template, request

from core.rbac import role_required
from core.export_utils import export_csv, export_excel, export_pdf

from ai import sales_prediction, demand_forecasting, recommendation_engine
from ai import customer_segmentation, business_intelligence, alerts_engine
from models.product_model import Product
from models.customer_model import Customer

ai_bp = Blueprint("ai", __name__)


# ---------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------
@ai_bp.route("/admin/ai-dashboard")
@role_required("admin", "manager")
def ai_dashboard():
    daily = sales_prediction.forecast_daily(days_ahead=7)
    top_products = business_intelligence.profitability_analysis(limit=5)
    alerts = alerts_engine.get_all_alerts()
    churn = customer_segmentation.churn_risk_customers()

    next_week_forecast = round(sum(daily["forecast"]), 2) if daily["forecast"] else 0

    return render_template(
        "admin/ai/ai_dashboard.html",
        daily=daily,
        next_week_forecast=next_week_forecast,
        top_products=top_products,
        alerts=alerts[:8],
        alert_count=len(alerts),
        churn_count=len(churn)
    )


# ---------------------------------------------------------------
# Forecasting / predictions
# ---------------------------------------------------------------
@ai_bp.route("/admin/predictions")
@role_required("admin", "manager")
def predictions():
    daily = sales_prediction.forecast_daily(days_ahead=7)
    weekly = sales_prediction.forecast_weekly(weeks_ahead=4)
    monthly = sales_prediction.forecast_monthly(months_ahead=3)
    seasonal = sales_prediction.seasonal_trend()
    stockout_risk = demand_forecasting.out_of_stock_prediction()
    reorder = demand_forecasting.auto_reorder_suggestions()

    return render_template(
        "admin/ai/predictions.html",
        daily=daily, weekly=weekly, monthly=monthly, seasonal=seasonal,
        stockout_risk=stockout_risk, reorder=reorder
    )


@ai_bp.route("/admin/predictions/product/<int:product_id>")
@role_required("admin", "manager")
def product_forecast(product_id):
    forecast = demand_forecasting.product_demand_forecast(product_id)
    products = Product.get_all_products()
    product_name = next((p[2] for p in products if p[0] == product_id), "Unknown")
    return render_template("admin/ai/product_forecast.html",
                           forecast=forecast, product_id=product_id, product_name=product_name)


# ---------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------
@ai_bp.route("/admin/recommendations")
@role_required("admin", "manager", "employee", "cashier")
def recommendations():
    product_id = request.args.get("product_id", type=int)
    customer_id = request.args.get("customer_id", type=int)

    products = Product.get_all_products()
    customers = Customer.get_all_customers()

    fbt = cross_sell = upsell = []
    customer_recs = []

    if product_id:
        fbt = recommendation_engine.frequently_bought_together(product_id)
        cross_sell = recommendation_engine.cross_sell_suggestions(product_id)
        upsell = recommendation_engine.upsell_suggestions(product_id)

    if customer_id:
        customer_recs = recommendation_engine.recommend_for_customer(customer_id)

    top_sellers = recommendation_engine.top_selling_products()

    return render_template(
        "admin/ai/recommendations.html",
        products=products, customers=customers,
        selected_product=product_id, selected_customer=customer_id,
        fbt=fbt, cross_sell=cross_sell, upsell=upsell,
        customer_recs=customer_recs, top_sellers=top_sellers
    )


# ---------------------------------------------------------------
# Customer analytics
# ---------------------------------------------------------------
@ai_bp.route("/admin/ai/customer-segmentation")
@role_required("admin", "manager")
def segmentation():
    segments = customer_segmentation.compute_rfm_segments()
    counts = {}
    for s in segments:
        counts[s["segment"]] = counts.get(s["segment"], 0) + 1
    return render_template("admin/ai/segmentation.html", segments=segments, counts=counts)


@ai_bp.route("/admin/ai/churn-risk")
@role_required("admin", "manager")
def churn_risk():
    return render_template("admin/ai/churn_risk.html", customers=customer_segmentation.churn_risk_customers())


@ai_bp.route("/admin/ai/clv")
@role_required("admin", "manager")
def clv():
    return render_template("admin/ai/clv.html", customers=customer_segmentation.predicted_clv_all())


@ai_bp.route("/admin/ai/buying-pattern/<int:customer_id>")
@role_required("admin", "manager", "employee")
def buying_pattern(customer_id):
    pattern = customer_segmentation.buying_pattern(customer_id)
    customer = Customer.get_customer(customer_id)
    return render_template("admin/ai/buying_pattern.html", pattern=pattern, customer=customer)


# ---------------------------------------------------------------
# Business intelligence
# ---------------------------------------------------------------
@ai_bp.route("/admin/ai/profitability")
@role_required("admin", "manager", "accountant")
def profitability():
    return render_template("admin/ai/profitability.html",
                           products=business_intelligence.profitability_analysis())


@ai_bp.route("/admin/ai/abc-analysis")
@role_required("admin", "manager", "inventory_manager")
def abc_analysis():
    return render_template("admin/ai/abc_analysis.html", products=business_intelligence.abc_analysis())


@ai_bp.route("/admin/ai/movers")
@role_required("admin", "manager", "inventory_manager")
def movers():
    return render_template("admin/ai/movers.html", data=business_intelligence.fast_slow_movers())


@ai_bp.route("/admin/ai/dead-stock")
@role_required("admin", "manager", "inventory_manager")
def dead_stock_page():
    return render_template("admin/ai/dead_stock.html", products=business_intelligence.dead_stock())


@ai_bp.route("/admin/ai/sales-trend")
@role_required("admin", "manager")
def sales_trend():
    return render_template("admin/ai/sales_trend.html",
                           categories=business_intelligence.sales_trend_by_category())


# ---------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------
@ai_bp.route("/admin/ai/alerts")
@role_required("admin", "manager", "inventory_manager")
def alerts_page():
    return render_template("admin/ai/alerts.html", alerts=alerts_engine.get_all_alerts())


# ---------------------------------------------------------------
# Reports (exportable)
# ---------------------------------------------------------------
@ai_bp.route("/admin/ai/reports/executive-summary")
@role_required("admin", "manager", "super_admin")
def executive_summary():
    daily = sales_prediction.forecast_daily(days_ahead=7)
    top_products = business_intelligence.profitability_analysis(limit=5)
    abc = business_intelligence.abc_analysis()
    alerts = alerts_engine.get_all_alerts()
    churn = customer_segmentation.churn_risk_customers()
    dead = business_intelligence.dead_stock()

    a_count = len([p for p in abc if p["grade"] == "A"])

    return render_template(
        "admin/ai/executive_summary.html",
        daily=daily, top_products=top_products, alerts=alerts,
        churn=churn, dead_stock=dead, a_count=a_count, abc_total=len(abc)
    )


_FORECAST_HEADERS = ["Date", "Forecasted Revenue"]


@ai_bp.route("/admin/ai/reports/forecast/export/<fmt>")
@role_required("admin", "manager")
def export_forecast(fmt):
    daily = sales_prediction.forecast_daily(days_ahead=14)
    from datetime import date, timedelta
    rows = [[str(date.today() + timedelta(days=i + 1)), v] for i, v in enumerate(daily["forecast"])]
    if fmt == "csv":
        return export_csv(_FORECAST_HEADERS, rows, "sales_forecast.csv")
    if fmt == "excel":
        return export_excel(_FORECAST_HEADERS, rows, "sales_forecast.xlsx", "Forecast")
    return export_pdf(_FORECAST_HEADERS, rows, "sales_forecast.pdf", "14-Day Sales Forecast")


_INVENTORY_INTEL_HEADERS = ["Product", "Grade", "Revenue", "Cumulative %"]


@ai_bp.route("/admin/ai/reports/inventory-intelligence/export/<fmt>")
@role_required("admin", "manager", "inventory_manager")
def export_inventory_intelligence(fmt):
    rows = [[p["product_name"], p["grade"], p["revenue"], p["cumulative_pct"]]
            for p in business_intelligence.abc_analysis()]
    if fmt == "csv":
        return export_csv(_INVENTORY_INTEL_HEADERS, rows, "inventory_intelligence.csv")
    if fmt == "excel":
        return export_excel(_INVENTORY_INTEL_HEADERS, rows, "inventory_intelligence.xlsx", "ABC Analysis")
    return export_pdf(_INVENTORY_INTEL_HEADERS, rows, "inventory_intelligence.pdf", "Inventory Intelligence (ABC)")
