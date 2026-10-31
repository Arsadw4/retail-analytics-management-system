"""
core/email_service.py
Minimal SMTP-based email sending for invoice delivery. Uses smtplib
directly rather than adding a dependency -- one focused function,
easy to audit. Never raises to the caller: email delivery failure
should never take down a checkout/reprint flow, so callers get a
(success: bool, message: str) tuple back instead.
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

from flask import current_app

logger = logging.getLogger("app")


def send_invoice_email(to_email, subject, body_text, pdf_bytes, pdf_filename):
    host = current_app.config.get("SMTP_HOST")
    if not host:
        return False, "Email is not configured on this server (SMTP_HOST is empty)."

    try:
        msg = MIMEMultipart()
        msg["From"] = current_app.config["SMTP_FROM_EMAIL"]
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body_text, "plain"))

        attachment = MIMEApplication(pdf_bytes, _subtype="pdf")
        attachment.add_header("Content-Disposition", "attachment", filename=pdf_filename)
        msg.attach(attachment)

        with smtplib.SMTP(host, current_app.config["SMTP_PORT"], timeout=15) as server:
            if current_app.config.get("SMTP_USE_TLS"):
                server.starttls()
            if current_app.config.get("SMTP_USERNAME"):
                server.login(current_app.config["SMTP_USERNAME"], current_app.config["SMTP_PASSWORD"])
            server.sendmail(current_app.config["SMTP_FROM_EMAIL"], [to_email], msg.as_string())

        return True, "Invoice emailed successfully."
    except Exception:
        logger.exception("Failed to send invoice email to %s", to_email)
        return False, "Failed to send email -- check SMTP configuration."
