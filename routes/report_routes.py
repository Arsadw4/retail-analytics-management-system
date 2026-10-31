from flask import Blueprint, render_template, request
from models.report_model import Report
from models.inventory_model import Inventory
from core.rbac import role_required
from core.export_utils import export_excel, export_pdf, export_csv

report_bp = Blueprint('report', __name__)

@report_bp.route('/admin/reports')
@role_required("admin", "manager")
def reports():
    return render_template('admin/reports/reports.html', summary=Report.get_summary(), payment_summary=Report.payment_summary(), top_products=Report.top_products())

@report_bp.route('/admin/sales-report')
@role_required("admin", "manager")
def sales_report():
    date_from=request.args.get('date_from') or None
    date_to=request.args.get('date_to') or None
    rows=Report.sales_rows(date_from,date_to)
    base=Report.sales_summary(date_from,date_to)
    summary=dict(Report.get_summary())
    summary.update(base)
    return render_template('admin/reports/sales_report.html', summary=summary, rows=rows, date_from=date_from or '', date_to=date_to or '', payment_summary=Report.payment_summary(date_from,date_to), top_products=Report.top_products(date_from,date_to), daily_sales=Report.daily_sales(date_from,date_to))

@report_bp.route('/admin/profit-report')
@role_required("admin", "manager")
def profit_report():
    date_from=request.args.get('date_from') or None
    date_to=request.args.get('date_to') or None
    rows=Report.sales_rows(date_from,date_to)
    base=Report.sales_summary(date_from,date_to)
    summary=dict(Report.get_summary())
    summary.update(base)
    return render_template('admin/reports/profit_report.html', summary=summary, rows=rows, date_from=date_from or '', date_to=date_to or '', payment_summary=Report.payment_summary(date_from,date_to), top_products=Report.top_products(date_from,date_to), daily_sales=Report.daily_sales(date_from,date_to))

@report_bp.route('/admin/stock-report')
@role_required("admin", "manager")
def stock_report():
    inventory=Inventory.get_all_inventory()
    summary=Inventory.inventory_summary()
    return render_template('admin/reports/stock_report.html', inventory=inventory, summary=summary, low_stock=Inventory.low_stock_count(), out_of_stock=Inventory.out_of_stock_count())

def _export_report(fmt,headers,rows,filename,title,sheet,date_range=None):
    if fmt=='csv': return export_csv(headers,rows,filename+'.csv',report_title=title,date_range=date_range)
    if fmt=='excel': return export_excel(headers,rows,filename+'.xlsx',sheet,report_title=title,date_range=date_range)
    if fmt=='pdf': return export_pdf(headers,rows,filename+'.pdf',title,date_range=date_range)
    return ("Unsupported export format",400)

@report_bp.route('/admin/sales-report/export/<fmt>')
@role_required("admin", "manager")
def export_sales_report(fmt):
    rows=Report.sales_rows(request.args.get('date_from') or None,request.args.get('date_to') or None)
    return _export_report(fmt,["Sale ID","Invoice","Date","Customer","Total Amount","Profit","Status"],rows,'sales_report','Sales Report','Sales',f"{request.args.get('date_from') or 'All time'} → {request.args.get('date_to') or 'Today'}")

@report_bp.route('/admin/profit-report/export/<fmt>')
@role_required("admin", "manager")
def export_profit_report(fmt):
    rows=Report.sales_rows(request.args.get('date_from') or None,request.args.get('date_to') or None)
    return _export_report(fmt,["Sale ID","Invoice","Date","Customer","Total Amount","Profit","Status"],rows,'profit_report','Profit Report','Profit',f"{request.args.get('date_from') or 'All time'} → {request.args.get('date_to') or 'Today'}")

@report_bp.route('/admin/stock-report/export/<fmt>')
@role_required("admin", "manager")
def export_stock_report(fmt):
    rows=Report.stock_rows()
    return _export_report(fmt,["Product","Current Stock","Purchase Price","Selling Price","Stock Value","Status"],rows,'inventory_report','Inventory Report','Inventory')
