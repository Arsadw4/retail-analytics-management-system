"""Database-backed professional PDF invoice generation."""
import io
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

_FONT_READY = False

def _register_unicode_font():
    global _FONT_READY
    if _FONT_READY:
        return "RAUnicode"
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        r"C:\\Windows\\Fonts\\arial.ttf",
        r"C:\\Windows\\Fonts\\segoeui.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("RAUnicode", path))
                _FONT_READY = True
                return "RAUnicode"
            except Exception:
                continue
    return "Helvetica"

def build_invoice_pdf(company, sale, items, payments):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm,
                            leftMargin=14 * mm, rightMargin=14 * mm)
    font = _register_unicode_font()
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleBig", parent=styles["Title"], fontName=font,
                                 fontSize=20, textColor=colors.HexColor("#0B315C"))
    body_style = ParagraphStyle("Body", parent=styles["Normal"], fontName=font, fontSize=9)
    small_style = ParagraphStyle("Small", parent=styles["Normal"], fontName=font, fontSize=8,
                                 textColor=colors.HexColor("#64748B"))
    elements = []

    def money(value):
        return f"₹{float(value or 0):,.2f}"

    company_name = company[1] if company else "Retail Company"
    gst_number = company[2] if company else ""
    address = company[3] if company else ""
    phone = company[5] if company else ""
    email = company[6] if company else ""

    elements.append(Paragraph("Retail <font color='#1473FF'>Analytics</font>", title_style))
    elements.append(Paragraph("Management System", body_style))
    elements.append(Spacer(1, 2 * mm))
    elements.append(Paragraph(company_name, ParagraphStyle("Company", parent=body_style, fontSize=13,
                                                            fontName=font, leading=16)))
    if address: elements.append(Paragraph(address, body_style))
    contact = " · ".join(str(v) for v in (phone, email) if v)
    if contact: elements.append(Paragraph(contact, small_style))
    if gst_number: elements.append(Paragraph(f"GSTIN: {gst_number}", body_style))
    elements.append(Spacer(1, 6 * mm))

    (sale_id, invoice_number, sale_date, total_amount, profit_amount, status,
     taxable_amount, cgst, sgst, igst, discount_amount, coupon_code, customer_state,
     customer_name, customer_phone, customer_email, customer_address, sold_by) = sale

    customer_block = [
        Paragraph("<b>INVOICE</b>", ParagraphStyle("InvoiceHead", parent=body_style, fontSize=15, textColor=colors.HexColor("#1473FF"))),
        Paragraph(f"Invoice No: <b>{invoice_number}</b>", body_style),
        Paragraph(f"Date: {sale_date}", body_style),
        Paragraph(f"Status: {status}", body_style),
    ]
    billed_block = [
        Paragraph("<b>BILL TO</b>", body_style),
        Paragraph(customer_name or "Walk-in Customer", body_style),
    ]
    if customer_phone: billed_block.append(Paragraph(f"Phone: {customer_phone}", body_style))
    if customer_email: billed_block.append(Paragraph(f"Email: {customer_email}", body_style))
    if customer_address: billed_block.append(Paragraph(customer_address, body_style))
    billed_block.append(Paragraph(f"Served by: {sold_by or '-'}", small_style))
    info = Table([[customer_block, billed_block]], colWidths=[90 * mm, 85 * mm])
    info.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#D9E1EE")),
                              ("INNERGRID", (0, 0), (-1, -1), .3, colors.HexColor("#E8EDF4")), ("LEFTPADDING", (0, 0), (-1, -1), 8),
                              ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    elements.append(info)
    elements.append(Spacer(1, 6 * mm))

    table_data = [["Product", "SKU", "Qty", "Unit Price", "Discount", "GST", "Subtotal"]]
    original_subtotal = sum(float(it[4] or 0) for it in items)
    for it in items:
        product_id, product_name, qty, unit_price, subtotal, gst_rate, product_image, sku = it
        product_cell = [Paragraph(str(product_name), body_style)]
        if product_image and company is not None:
            # Images live under the application's static/uploads directory.
            try:
                from flask import current_app
                image_path = os.path.join(current_app.static_folder, "uploads", product_image)
                if os.path.isfile(image_path):
                    img = Image(image_path, width=9 * mm, height=9 * mm)
                    product_cell.insert(0, img)
            except Exception:
                pass
        line_discount = (float(subtotal or 0) / original_subtotal * float(discount_amount or 0)) if original_subtotal else 0
        table_data.append([product_cell, sku or "—", str(qty), money(unit_price), money(line_discount),
                           f"{float(gst_rate or 0):.1f}%", money(float(subtotal or 0) - line_discount)])
    item_table = Table(table_data, colWidths=[55 * mm, 25 * mm, 12 * mm, 26 * mm, 26 * mm, 18 * mm, 30 * mm], repeatRows=1)
    item_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B315C")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#CBD5E1")), ("FONTNAME", (0, 0), (-1, -1), font),
        ("FONTSIZE", (0, 0), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (2, 1), (-1, -1), "RIGHT"), ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(item_table)
    elements.append(Spacer(1, 5 * mm))

    summary_data = [
        ["Taxable Amount", money(taxable_amount)], ["Discount", f"-{money(discount_amount)}"],
        ["CGST", money(cgst)], ["SGST", money(sgst)], ["IGST", money(igst)],
        ["Grand Total", money(total_amount)],
    ]
    summary_table = Table(summary_data, colWidths=[50 * mm, 38 * mm], hAlign="RIGHT")
    summary_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font), ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"), ("LINEABOVE", (0, -1), (-1, -1), 1, colors.HexColor("#0B315C")),
        ("FONTNAME", (0, -1), (-1, -1), font), ("FONTSIZE", (0, -1), (-1, -1), 11),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#EAF3FF")),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 5 * mm))
    if payments:
        pay_lines = [f"{p[0].upper()}: {money(p[1])}" + (f" (Ref: {p[2]})" if p[2] else "") for p in payments]
        elements.append(Paragraph("<b>Payment:</b> " + " · ".join(pay_lines), body_style))
    elements.append(Spacer(1, 8 * mm))
    elements.append(Paragraph("Thank you for your business.", ParagraphStyle("Thanks", parent=body_style, fontSize=9, italic=True)))

    def footer(canvas, doc_obj):
        canvas.saveState()
        canvas.setFont(font, 8)
        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.drawString(14 * mm, 9 * mm, "Retail Analytics Management System")
        canvas.drawRightString(A4[0] - 14 * mm, 9 * mm, f"Page {doc_obj.page}")
        canvas.restoreState()

    doc.build(elements, onFirstPage=footer, onLaterPages=footer)
    buf.seek(0)
    return buf.read()
