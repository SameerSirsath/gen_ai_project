"""
app/models/db.py — SQLAlchemy database models for AI Sales Outreach Dashboard.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class CompanyProfile(db.Model):
    """
    Represents the user's own company profile and value proposition.
    """
    __tablename__ = "company_profiles"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, default="CognitiveReach AI")
    industry = db.Column(db.String(255), default="Enterprise B2B Software & AI Automation")
    value_proposition = db.Column(
        db.Text,
        default="We help enterprise sales teams automate personalized outreach and eliminate hallucinations with multi-agent RAG."
    )
    services_offered = db.Column(
        db.Text,
        default="AI SDR Agent Deployment, Real-Time Market Intelligence Ingestion, Automated CRM Enrichment, Multi-Agent Email Generation."
    )
    case_studies = db.Column(
        db.Text,
        default="Boosted sales meeting booking rates by 240% for SaaS clients; reduced research time per prospect from 20 minutes to under 2 seconds."
    )
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "industry": self.industry,
            "value_proposition": self.value_proposition,
            "services_offered": self.services_offered,
            "case_studies": self.case_studies,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Lead(db.Model):
    """
    Represents a target prospect company / contact lead.
    """
    __tablename__ = "leads"

    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(255), nullable=False)
    contact_name = db.Column(db.String(255), default="")
    email = db.Column(db.String(255), default="")
    website_url = db.Column(db.String(500), default="")
    status = db.Column(db.String(50), default="Pending")  # Pending, Processing, Drafted, Sent, Failed
    mode = db.Column(db.String(50), default="Manual")      # Auto, Manual
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

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
            "context_count": len(self.contexts),
            "email_count": len(self.emails),
        }


class LeadContext(db.Model):
    """
    Raw intelligence / scraped text gathered for a specific lead.
    """
    __tablename__ = "lead_contexts"

    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    raw_text = db.Column(db.Text, nullable=False)
    nlp_processed = db.Column(db.Boolean, default=False)
    vector_synced = db.Column(db.Boolean, default=False)
    source_type = db.Column(db.String(50), default="Manual")  # Website, News, Manual
    keywords = db.Column(db.Text, default="[]")  # JSON serialized list of keywords/entities
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        import json
        try:
            kw = json.loads(self.keywords) if self.keywords else []
        except Exception:
            kw = []
        return {
            "id": self.id,
            "lead_id": self.lead_id,
            "raw_text": self.raw_text,
            "nlp_processed": self.nlp_processed,
            "vector_synced": self.vector_synced,
            "source_type": self.source_type,
            "keywords": kw,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M") if self.created_at else None,
        }


class EmailLog(db.Model):
    """
    Record of generated and dispatched emails.
    """
    __tablename__ = "email_logs"

    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    subject = db.Column(db.String(500), default="")
    body = db.Column(db.Text, default="")
    evaluator_score = db.Column(db.Float, default=1.0)
    evaluator_reasoning = db.Column(db.Text, default="")
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "lead_id": self.lead_id,
            "subject": self.subject,
            "body": self.body,
            "evaluator_score": self.evaluator_score,
            "evaluator_reasoning": self.evaluator_reasoning,
            "sent_at": self.sent_at.strftime("%Y-%m-%d %H:%M:%S") if self.sent_at else None,
        }
