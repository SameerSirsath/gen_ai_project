"""
app/models/db.py — SQLAlchemy database models for AI Sales Outreach Dashboard.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict
from flask_sqlalchemy import SQLAlchemy

from app.models.encrypted_type import EncryptedText

db = SQLAlchemy()


class Company(db.Model):
    """
    Represents the user's company profile and value proposition.
    """
    __tablename__ = "companies"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False)
    industry = db.Column(db.String(150))
    value_proposition = db.Column(db.Text)
    services_offered = db.Column(db.Text)
    case_studies = db.Column(db.Text)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "industry": self.industry,
            "value_proposition": self.value_proposition,
            "services_offered": self.services_offered,
            "case_studies": self.case_studies,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# Alias for backward compatibility
CompanyProfile = Company


class Lead(db.Model):
    """
    Represents a target prospect company / contact lead.
    """
    __tablename__ = "leads"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    company_name = db.Column(db.String(255), nullable=False)
    contact_name = db.Column(db.String(150), default="")
    email = db.Column(db.String(255), unique=True)
    website_url = db.Column(db.String(500), default="")
    status = db.Column(db.String(50), default="Pending")  # 'Pending', 'Processing', 'Drafted', 'Sent', 'Failed'
    mode = db.Column(db.String(50), default="Manual")      # 'Auto', 'Manual'
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    contexts = db.relationship("LeadContext", backref="lead", lazy=True, cascade="all, delete-orphan")
    emails = db.relationship("EmailLog", backref="lead", lazy=True, cascade="all, delete-orphan")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "company_name": self.company_name,
            "contact_name": self.contact_name,
            "email": self.email,
            "website_url": self.website_url,
            "status": self.status,
            "mode": self.mode,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M") if self.created_at else None,
            "context_count": len(self.contexts) if self.contexts else 0,
            "email_count": len(self.emails) if self.emails else 0,
        }


class LeadContext(db.Model):
    """
    Raw intelligence / scraped text gathered for a specific lead.
    """
    __tablename__ = "lead_context"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    raw_text = db.Column(db.Text(length=4294967295), nullable=False)  # LONGTEXT in MySQL
    nlp_processed = db.Column(db.Boolean, default=False)
    vector_synced = db.Column(db.Boolean, default=False)
    source_type = db.Column(db.String(50), default="Manual")
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "lead_id": self.lead_id,
            "raw_text": self.raw_text,
            "nlp_processed": self.nlp_processed,
            "vector_synced": self.vector_synced,
            "source_type": self.source_type,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M") if self.created_at else None,
        }


class EmailLog(db.Model):
    """
    Record of generated and dispatched emails.
    """
    __tablename__ = "email_logs"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    subject = db.Column(db.String(500), default="")
    body = db.Column(db.Text(length=4294967295), default="")  # LONGTEXT in MySQL
    evaluator_score = db.Column(db.String(50), default="1.0")
    evaluator_reasoning = db.Column(db.Text, default="")
    sent_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "lead_id": self.lead_id,
            "subject": self.subject,
            "body": self.body,
            "evaluator_score": self.evaluator_score,
            "evaluator_reasoning": self.evaluator_reasoning,
            "sent_at": self.sent_at.strftime("%Y-%m-%d %H:%M:%S") if self.sent_at else None,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
        }


class ApiKey(db.Model):
    """
    Stores encrypted API keys for multiple providers (Groq, Gemini, etc.).
    Column key_value is encrypted at rest using Fernet via EncryptedText.
    """
    __tablename__ = "api_keys"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    provider = db.Column(db.String(100), nullable=False)
    key_alias = db.Column(db.String(150), nullable=False)
    key_value = db.Column(EncryptedText, nullable=False)  # Encrypted automatically
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    def to_dict(self, mask: bool = True) -> Dict[str, Any]:
        val = self.key_value or ""
        masked_val = (val[:4] + "****" + val[-4:]) if (mask and len(val) >= 8) else ("****" if mask else val)
        return {
            "id": self.id,
            "provider": self.provider,
            "key_alias": self.key_alias,
            "key_value": masked_val,
            "is_active": self.is_active,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
            "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M:%S") if self.updated_at else None,
        }
