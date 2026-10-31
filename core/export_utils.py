"""Shared CSV, Excel and PDF exporters with consistent business formatting."""
import csv
import io
from datetime import datetime, date
from decimal import Decimal
from flask import send_file
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.table import Table as XLTable, TableStyleInfo
from openpyxl.utils import get_column_letter
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os
from xml.sax.saxutils import escape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm

def _is_money_header(header):
    """Return True only for monetary columns, not counts/quantities/IDs."""
    import re
    h=str(header).strip().lower()
    words=set(re.findall(r"[a-z]+", h))
    money_words={"amount","revenue","profit","price","value","discount","tax","salary","net"}
    count_words={"count","qty","quantity","items","customers","users","transactions","records","product","products","supplier","suppliers","percentage"}
    if words & count_words and not (words & money_words):
        return False
    return bool(words & money_words) or "total" in words and "stock" not in words and not (words & count_words)

def _fmt_money(v):
    try: return f"₹{float(v):,.2f}"
    except (TypeError, ValueError): return str(v)

def export_csv(headers, rows, filename, report_title=None, date_range=None):
    """Export real rows as a readable UTF-8 CSV with optional report metadata."""
    buf=io.StringIO()
    writer=csv.writer(buf)
    if report_title:
        writer.writerow(["Retail Analytics Management System"])
        writer.writerow([str(report_title)])
        writer.writerow(["Generated", datetime.now().strftime("%d %b %Y, %I:%M %p")])
        if date_range:
            writer.writerow(["Date Range", str(date_range)])
        writer.writerow(["Records", len(rows or [])])
        writer.writerow([])
    writer.writerow(headers)
    for row in rows or []:
        writer.writerow([_fmt_money(v) if _is_money_header(h) and isinstance(v,(int,float,Decimal)) else
                         (v.strftime('%d %b %Y, %I:%M %p') if isinstance(v,datetime) else
                          (v.strftime('%d %b %Y') if isinstance(v,date) else v))
                         for h,v in zip(headers,row)])
    mem=io.BytesIO(buf.getvalue().encode("utf-8-sig"))
    return send_file(mem,mimetype="text/csv",as_attachment=True,download_name=filename)


def export_excel(headers, rows, filename, sheet_title="Report", report_title=None, date_range=None):
    wb=Workbook()
    ws=wb.active
    ws.title=sheet_title[:31]
    start_row=1
    if report_title:
        ws.merge_cells(start_row=1,start_column=1,end_row=1,end_column=max(len(headers),1))
        ws.cell(1,1).value="Retail Analytics Management System"
        ws.cell(1,1).font=Font(size=16,bold=True,color="0B315C")
        ws.cell(1,1).alignment=Alignment(horizontal="left")
        ws.merge_cells(start_row=2,start_column=1,end_row=2,end_column=max(len(headers),1))
        ws.cell(2,1).value=str(report_title)
        ws.cell(2,1).font=Font(size=12,bold=True,color="1478F2")
        ws.cell(3,1).value="Generated"
        ws.cell(3,2).value=datetime.now()
        ws.cell(3,2).number_format='dd-mmm-yyyy hh:mm AM/PM'
        if date_range:
            ws.cell(4,1).value="Date Range"
            ws.cell(4,2).value=str(date_range)
        ws.cell(5,1).value="Records"
        ws.cell(5,2).value=len(rows or [])
        start_row=7
    header_row=start_row
    for idx,h in enumerate(headers,1): ws.cell(header_row,idx).value=str(h)
    for ridx,row in enumerate(rows or [],header_row+1):
        for cidx,value in enumerate(row,1): ws.cell(ridx,cidx).value=value
    header_fill=PatternFill("solid", fgColor="0B315C")
    header_font=Font(color="FFFFFF",bold=True)
    thin=Side(style="thin",color="D9E1EE")
    for c in ws[header_row]:
        if c.column<=len(headers):
            c.fill=header_fill
            c.font=header_font
            c.alignment=Alignment(horizontal="center",vertical="center")
    for col_idx,header in enumerate(headers,1):
        money=_is_money_header(header)
        for row in ws.iter_rows(min_row=header_row+1,min_col=col_idx,max_col=col_idx):
            c=row[0]
            if money and isinstance(c.value,(int,float,Decimal)): c.number_format='₹#,##0.00'
            if isinstance(c.value,(datetime,date)): c.number_format='dd-mmm-yyyy hh:mm AM/PM' if isinstance(c.value,datetime) else 'dd-mmm-yyyy'
            c.border=Border(bottom=thin)
            c.alignment=Alignment(vertical="top",wrap_text=True)
        values=[str(ws.cell(r,col_idx).value or '') for r in range(header_row,ws.max_row+1)]
        ws.column_dimensions[get_column_letter(col_idx)].width=min(max(max(map(len,values))+2,12),45)
    data_end=ws.max_row
    if data_end>=header_row+1:
        ref=f"A{header_row}:{ws.cell(data_end,ws.max_column).coordinate}"
        name="ReportData" if not hasattr(wb,'_report_table_count') else "ReportData2"
        tab=XLTable(displayName=name,ref=ref)
        tab.tableStyleInfo=TableStyleInfo(name="TableStyleMedium2",showRowStripes=True,showFirstColumn=False,showLastColumn=False)
        ws.add_table(tab)
        ws.freeze_panes=f"A{header_row+1}"
        # A real totals row for numeric money columns, kept outside the table so
        # the exported dataset remains unchanged.
        total_row=data_end+2
        money_cols=[]
        for idx,h in enumerate(headers,1):
            if _is_money_header(h):
                money_cols.append(idx)
                ws.cell(total_row,idx).value=f"=SUM({ws.cell(header_row+1,idx).coordinate}:{ws.cell(data_end,idx).coordinate})"
                ws.cell(total_row,idx).number_format='₹#,##0.00'
                ws.cell(total_row,idx).font=Font(bold=True,color="0B315C")
        if money_cols:
            ws.cell(total_row,1).value="Report Total" if 1 not in money_cols else ws.cell(total_row,1).value
            ws.cell(total_row,1).font=Font(bold=True,color="0B315C")
    ws.sheet_view.showGridLines=False
    ws.auto_filter.ref=f"A{header_row}:{ws.cell(data_end,ws.max_column).coordinate}" if data_end>=header_row+1 else f"A{header_row}:{ws.cell(header_row,len(headers)).coordinate}"
    buf=io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf,mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",as_attachment=True,download_name=filename)


def export_pdf(headers, rows, filename, title="Report", date_range=None):
    """Generate a clean, print-ready business report PDF from database rows."""
    buf = io.BytesIO()
    page_width, page_height = landscape(A4)
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4),
        topMargin=20 * mm, bottomMargin=18 * mm,
        leftMargin=12 * mm, rightMargin=12 * mm,
        title=str(title), author="Retail Analytics Management System"
    )

    font = "Helvetica"
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        r"C:\\Windows\\Fonts\\arial.ttf",
        r"C:\\Windows\\Fonts\\segoeui.ttf",
    ):
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("RAExportUnicode", path))
                font = "RAExportUnicode"
                break
            except Exception:
                pass

    styles = getSampleStyleSheet()
    brand = ParagraphStyle("ExportBrand", parent=styles["Normal"], fontName=font,fontSize=9, leading=11, textColor=colors.HexColor("#1478F2"))
    title_style = ParagraphStyle("ExportTitle", parent=styles["Title"], fontName=font,fontSize=19, leading=22, textColor=colors.HexColor("#0B315C"),spaceAfter=2 * mm)
    meta = ParagraphStyle("ExportMeta", parent=styles["Normal"], fontName=font,fontSize=8, leading=10, textColor=colors.HexColor("#64748B"))
    section = ParagraphStyle("ExportSection", parent=styles["Heading3"], fontName=font,fontSize=10, leading=12, textColor=colors.HexColor("#0B315C"),spaceBefore=2 * mm, spaceAfter=2 * mm)
    clean_rows=list(rows or [])
    safe_headers=[str(h) for h in headers]
    range_text = f" &nbsp;•&nbsp; Date Range: {escape(str(date_range))}" if date_range else ""
    elements=[Paragraph("Retail <font color='#1478F2'>Analytics</font> Management System",brand),Paragraph(escape(str(title)),title_style),Paragraph(f"Business Report &nbsp;•&nbsp; Generated {datetime.now().strftime('%d %b %Y, %I:%M %p')} &nbsp;•&nbsp; {len(clean_rows)} record(s){range_text}",meta),Spacer(1,4*mm),Paragraph("Report Details",section)]
    data=[[Paragraph(h,ParagraphStyle("Hdr",parent=meta,fontName=font,fontSize=7.5,textColor=colors.white,leading=9)) for h in safe_headers]]
    body_style=ParagraphStyle("Cell",parent=meta,fontName=font,fontSize=7.2,leading=9,textColor=colors.HexColor("#1E293B"))
    for row in clean_rows:
        out=[]
        for h,v in zip(safe_headers,row):
            if v is None:text="—"
            elif _is_money_header(h) and isinstance(v,(int,float,Decimal)):text=_fmt_money(v)
            elif isinstance(v,datetime):text=v.strftime("%d %b %Y, %I:%M %p")
            elif isinstance(v,date):text=v.strftime("%d %b %Y")
            else:text=str(v)
            out.append(Paragraph(escape(text),body_style))
        data.append(out)
    if not data[0]: data=[[Paragraph("No report columns available",body_style)]]
    ncols=max(len(safe_headers),1)
    weights=[]
    for h in safe_headers:
        hl=h.lower()
        if any(k in hl for k in ("customer","product","description","address")):weights.append(2.2)
        elif any(k in hl for k in ("date","invoice","status")):weights.append(1.25)
        elif _is_money_header(h):weights.append(1.35)
        else:weights.append(1.0)
    total_weight=sum(weights) or ncols
    usable=page_width-24*mm
    col_widths=[usable*w/total_weight for w in weights]
    table=Table(data,colWidths=col_widths,repeatRows=1,hAlign="LEFT")
    table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#0B315C")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),0.35,colors.HexColor("#D5DEE9")),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("LEFTPADDING",(0,0),(-1,-1),5),("RIGHTPADDING",(0,0),(-1,-1),5),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]))
    for r in range(1,len(data)):
        if r%2==0: table.setStyle(TableStyle([("BACKGROUND",(0,r),(-1,r),colors.HexColor("#F6F9FC"))]))
        for c,h in enumerate(safe_headers):
            if _is_money_header(h) or h.lower() in {"qty","quantity","count","stock","current stock"}:table.setStyle(TableStyle([("ALIGN",(c,r),(c,r),"RIGHT")]))
    elements.append(table)
    money_totals=[]
    for idx,h in enumerate(safe_headers):
        if _is_money_header(h):
            total=sum(float(row[idx] or 0) for row in clean_rows if idx < len(row) and isinstance(row[idx],(int,float,Decimal)))
            if clean_rows:
                money_totals.append((h,total))
    if money_totals:
        total_cells=[[Paragraph(escape(h),body_style), Paragraph(_fmt_money(v),body_style)] for h,v in money_totals]
        elements.extend([Spacer(1,3*mm),Paragraph("Totals",section)])
        totals_table=Table(total_cells,colWidths=[55*mm,35*mm],hAlign="RIGHT")
        totals_table.setStyle(TableStyle([("GRID",(0,0),(-1,-1),.35,colors.HexColor("#CBD5E1")),("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#EAF3FF")),("FONTNAME",(0,0),(-1,-1),font),("ALIGN",(1,0),(1,-1),"RIGHT"),("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]))
        elements.append(totals_table)
    if not clean_rows:elements.extend([Spacer(1,4*mm),Paragraph("No records matched the selected filters.",meta)])
    def footer(canvas,doc_obj):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#D9E1EA"))
        canvas.line(12*mm,13*mm,page_width-12*mm,13*mm)
        canvas.setFont(font,7.5)
        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.drawString(12*mm,8*mm,"Retail Analytics Management System")
        canvas.drawCentredString(page_width/2,8*mm,"Confidential Business Report")
        canvas.drawRightString(page_width-12*mm,8*mm,f"Page {doc_obj.page}")
        canvas.restoreState()
    doc.build(elements,onFirstPage=footer,onLaterPages=footer)
    buf.seek(0)
    return send_file(buf,mimetype="application/pdf",as_attachment=True,download_name=filename)
