"""
app/services/smtp_service.py — SMTP Email Dispatch Service.
Connects via TLS/SSL to send personalized outreach and logs results.
Supports dynamic mailbox configurations stored in database with environment fallback.
"""

from __future__ import annotations

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, Optional

from config import settings
from app.models.db import db, EmailLog, Mailbox


def get_active_mailbox(mailbox_id: Optional[int] = None) -> Optional[Mailbox]:
    """Retrieves specified or primary active mailbox from the database."""
    try:
        if mailbox_id:
            mb = db.session.get(Mailbox, mailbox_id) if hasattr(db.session, "get") else Mailbox.query.get(mailbox_id)
            if mb:
                return mb
        return Mailbox.query.filter_by(is_active=True).first()
    except Exception as e:
        print(f"[SMTP Service] Failed to query Mailbox: {e}")
        return None


def test_smtp_connection(
    host: str,
    port: int,
    user: str,
    password: str,
    use_tls: bool = True
) -> Dict[str, Any]:
    """
    Tests SMTP connection and authentication credentials without dispatching an email.
    """
    if not host or not user or not password:
        return {"success": False, "message": "Host, username, and password are required."}

    try:
        if int(port) == 465:
            server = smtplib.SMTP_SSL(host, int(port), timeout=12)
            server.ehlo()
        else:
            server = smtplib.SMTP(host, int(port), timeout=12)
            server.ehlo()
            if use_tls:
                server.starttls()
                server.ehlo()

        server.login(user, password)
        server.quit()
        return {
            "success": True,
            "message": f"Successfully authenticated with SMTP server {host}:{port} as {user}!"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"SMTP Connection Failed: {str(e)}"
        }


def send_email(
    to_email: str,
    subject: str,
    body: str,
    lead_id: Optional[int] = None,
    evaluator_score: float = 1.0,
    evaluator_reasoning: str = "Passed grounding evaluation",
    sender_email: Optional[str] = None,
    mailbox_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Sends an email via SMTP using dynamic Mailbox configuration and logs the result into EmailLog table.

    Args:
        to_email: Recipient email address.
        subject: Subject line.
        body: Plain text email body.
        lead_id: Optional foreign key to Lead table.
        evaluator_score: Evaluator grounding confidence score.
        evaluator_reasoning: Evaluator audit text.
        sender_email: Optional manual override for From address.
        mailbox_id: Optional specific Mailbox ID to send from.

    Returns:
        Dict {"success": bool, "message": str}
    """
    if not to_email or "@" not in to_email:
        return {"success": False, "message": "Invalid recipient email address."}

    # 1. Resolve sender mailbox settings (DB Mailbox takes precedence, then environment/settings)
    mb = get_active_mailbox(mailbox_id)

    if mb and mb.smtp_user:
        smtp_user = mb.smtp_user
        smtp_pass = mb.smtp_pass or ""
        smtp_host = mb.smtp_host or "smtp.gmail.com"
        smtp_port = int(mb.smtp_port or 587)
        from_email = sender_email or mb.sender_email or smtp_user
        from_name = mb.sender_name or "BizCorp Sales Outreach"
        use_tls = mb.use_tls if mb.use_tls is not None else True
    else:
        smtp_user = os.getenv("SMTP_USER", "") or settings.SMTP_USER or ""
        smtp_pass = os.getenv("SMTP_PASS", "") or settings.SMTP_PASS or ""
        smtp_host = os.getenv("SMTP_HOST", "") or settings.SMTP_HOST or "smtp.gmail.com"
        smtp_port = int(os.getenv("SMTP_PORT", 587))
        from_email = sender_email or smtp_user or "sales@example.com"
        from_name = "BizCorp Sales Outreach"
        use_tls = True

    if not smtp_user or "your_email" in smtp_user:
        print("[SMTP Service] Email simulated (SMTP credentials missing or default placeholder)")
        if lead_id:
            try:
                log_entry = EmailLog(
                    lead_id=lead_id,
                    subject=subject,
                    body=body,
                    evaluator_score=str(evaluator_score),
                    evaluator_reasoning=evaluator_reasoning or "Email simulated (SMTP keys missing)",
                )
                db.session.add(log_entry)
                db.session.commit()
            except Exception as db_err:
                print(f"[SMTP Service] Failed to save EmailLog record: {db_err}")
                db.session.rollback()
        return {
            "success": True,
            "message": "Email simulated (SMTP credentials missing or placeholder).",
            "simulated": True,
        }

    success = False
    message = ""

    try:
        msg = MIMEMultipart()
        msg["From"] = f"{from_name} <{from_email}>" if from_name else from_email
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15) as server:
                server.ehlo()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
                server.ehlo()
                if use_tls:
                    server.starttls()
                    server.ehlo()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)

        success = True
        message = f"Email successfully sent to {to_email} from {from_email} via {smtp_host}:{smtp_port}."
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
                evaluator_score=str(evaluator_score),
                evaluator_reasoning=evaluator_reasoning or message,
            )
            db.session.add(log_entry)
            db.session.commit()
        except Exception as db_err:
            print(f"[SMTP Service] Failed to save EmailLog record: {db_err}")
            db.session.rollback()

    return {"success": success, "message": message}
