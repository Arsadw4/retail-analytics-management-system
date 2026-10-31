from flask import Blueprint, render_template
from models.analytics_model import Analytics
from core.rbac import role_required

analytics_bp = Blueprint(
    "analytics",
    __name__
)


# Main Analytics Dashboard
@analytics_bp.route("/admin/analytics")
@role_required("admin", "manager")
def analytics():

    return render_template(
        "admin/analytics/analytics.html",

        best_product=Analytics.best_product(),
        worst_product=Analytics.worst_product(),
        top_customer=Analytics.top_customer(),
        low_stock=Analytics.low_stock_alert(),
        revenue=Analytics.revenue_prediction(),

        total_products=Analytics.total_products(),
        total_customers=Analytics.total_customers(),
        total_inventory=Analytics.total_inventory(),
        total_stock=Analytics.total_stock(),
        inventory_value=Analytics.inventory_value(),
        completed_sales=Analytics.completed_sales_count(),
        completed_revenue=Analytics.completed_revenue(),
        completed_profit=Analytics.completed_profit()
    )


# Bar Chart Page
@analytics_bp.route("/admin/bar-chart")
@role_required("admin", "manager")
def bar_chart():

    return render_template(
        "admin/analytics/bar_chart.html",

        total_products=Analytics.total_products(),
        total_customers=Analytics.total_customers(),
        total_inventory=Analytics.total_inventory()
    )


# Line Chart Page
@analytics_bp.route("/admin/line-chart")
@role_required("admin", "manager")
def line_chart():

    return render_template(
        "admin/analytics/line_chart.html",

        revenue=Analytics.revenue_prediction(),
        stock=Analytics.total_stock(),
        inventory_value=Analytics.inventory_value()
    )


# Pie Chart Page
@analytics_bp.route("/admin/pie-chart")
@role_required("admin", "manager")
def pie_chart():

    return render_template(
        "admin/analytics/pie_chart.html",

        total_products=Analytics.total_products(),
        total_customers=Analytics.total_customers(),
        total_inventory=Analytics.total_inventory()
    )


# Profit Loss Page
@analytics_bp.route("/admin/profit-loss")
@role_required("admin", "manager")
def profit_loss():

    return render_template(
        "admin/analytics/profit_loss.html",

        revenue=Analytics.revenue_prediction(),
        inventory_value=Analytics.inventory_value()
    )
