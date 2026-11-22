"""
app/services/smtp_service.py — SMTP Email Dispatch Service.
Connects via TLS to send personalized outreach and logs results.
"""

from __future__ import annotations

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, Optional

from config import settings
from app.models.db import db, EmailLog


def send_email(
    to_email: str,
    subject: str,
    body: str,
    lead_id: Optional[int] = None,
    evaluator_score: float = 1.0,
    evaluator_reasoning: str = "Passed grounding evaluation"
) -> Dict[str, Any]:
    """
    Sends an email via SMTP using TLS and logs the result into EmailLog table.

    Args:
        to_email: Recipient email address.
        subject: Subject line.
        body: Plain text email body.
        lead_id: Optional foreign key to Lead table.
        evaluator_score: Evaluator grounding confidence score.
        evaluator_reasoning: Evaluator audit text.

    Returns:
        Dict {"success": bool, "message": str}
    """
    if not to_email or "@" not in to_email:
        return {"success": False, "message": "Invalid recipient email address."}

    smtp_host = settings.SMTP_HOST
    smtp_port = settings.SMTP_PORT
    smtp_user = settings.SMTP_USER
    smtp_pass = settings.SMTP_PASS

    # Check if credentials are placeholders or empty
    is_mock = not (smtp_user and smtp_pass and "your_email" not in smtp_user and "your_app_password" not in smtp_pass)

    success = False
    message = ""

    if is_mock:
        # Simulate dispatch in demo / local mode
        success = True
        message = f"[Simulation] Email successfully dispatched to {to_email} via simulated SMTP."
        print(f"[SMTP Service] {message}")
    else:
        try:
            msg = MIMEMultipart()
            msg["From"] = smtp_user
            msg["To"] = to_email
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain", "utf-8"))

            with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)

            success = True
            message = f"Email successfully sent to {to_email} via {smtp_host}:{smtp_port}."
        except Exception as e:
            success = False
            message = f"SMTP transmission failed: {str(e)}"
            print(f"[SMTP Service] Error: {message}")

    # Log dispatch to database if lead_id is provided
    if lead_id:
        try:
            log_entry = EmailLog(
                lead_id=lead_id,
                subject=subject,
                body=body,
                evaluator_score=evaluator_score,
                evaluator_reasoning=evaluator_reasoning or message,
            )
            db.session.add(log_entry)
            db.session.commit()
        except Exception as db_err:
            print(f"[SMTP Service] Failed to save EmailLog record: {db_err}")
            db.session.rollback()

    return {"success": success, "message": message}
