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


class User(db.Model):
    """
    User model for authentication, role-based access, and enterprise profiles.
    """
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(150), default="")
    role = db.Column(db.String(50), default="admin")  # 'admin', 'manager', 'sdr', 'viewer'
    is_active = db.Column(db.Boolean, default=True)
    avatar_url = db.Column(db.String(500), nullable=True)
    last_login_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    # Relationships
    sessions = db.relationship("UserSession", backref="user", lazy=True, cascade="all, delete-orphan")
    resets = db.relationship("PasswordReset", backref="user", lazy=True, cascade="all, delete-orphan")
    settings = db.relationship("UserSetting", backref="user", uselist=False, lazy=True, cascade="all, delete-orphan")
    activities = db.relationship("ActivityLog", backref="user", lazy=True)

    def set_password(self, password: str) -> None:
        from werkzeug.security import generate_password_hash
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        from werkzeug.security import check_password_hash
        return check_password_hash(self.password_hash, password)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "full_name": self.full_name,
            "role": self.role,
            "is_active": self.is_active,
            "avatar_url": self.avatar_url,
            "last_login_at": self.last_login_at.strftime("%Y-%m-%d %H:%M:%S") if self.last_login_at else None,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
            "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M:%S") if self.updated_at else None,
        }


class UserSession(db.Model):
    """
    Tracks active user login sessions, devices, and expiration tokens.
    """
    __tablename__ = "user_sessions"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    session_token = db.Column(db.String(255), unique=True, nullable=False)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(500), nullable=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "expires_at": self.expires_at.strftime("%Y-%m-%d %H:%M:%S") if self.expires_at else None,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
        }


class PasswordReset(db.Model):
    """
    Stores secure tokens for password recovery requests.
    """
    __tablename__ = "password_resets"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = db.Column(db.String(255), unique=True, nullable=False)
    is_used = db.Column(db.Boolean, default=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "is_used": self.is_used,
            "expires_at": self.expires_at.strftime("%Y-%m-%d %H:%M:%S") if self.expires_at else None,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
        }


class UserSetting(db.Model):
    """
    Stores user preferences, UI theme, email signatures, and defaults.
    """
    __tablename__ = "user_settings"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    theme = db.Column(db.String(50), default="light")
    notifications_enabled = db.Column(db.Boolean, default=True)
    email_signature = db.Column(db.Text, nullable=True)
    default_llm_provider = db.Column(db.String(50), default="groq")
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "theme": self.theme,
            "notifications_enabled": self.notifications_enabled,
            "email_signature": self.email_signature,
            "default_llm_provider": self.default_llm_provider,
            "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M:%S") if self.updated_at else None,
        }


class ActivityLog(db.Model):
    """
    Audit log tracking user actions and events for security and transparency.
    """
    __tablename__ = "activity_logs"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = db.Column(db.String(100), nullable=False)  # 'LOGIN', 'CREATE_LEAD', 'GENERATE_EMAIL', 'SEND_EMAIL'
    entity_type = db.Column(db.String(50), nullable=True)  # 'lead', 'email', 'api_key', 'company'
    entity_id = db.Column(db.Integer, nullable=True)
    details = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "action": self.action,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "details": self.details,
            "ip_address": self.ip_address,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
        }


