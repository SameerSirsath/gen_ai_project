"""
app/__init__.py — Flask Application Factory.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask, jsonify

load_dotenv()

from config import settings
from app.models.db import db, Company, CompanyProfile, Lead, LeadContext, EmailLog, ApiKey, Mailbox


def _run_migrations():
    """Ensures newly added columns exist in existing database tables."""
    try:
        engine = db.engine
        with engine.connect() as conn:
            is_sqlite = "sqlite" in engine.url.drivername
            if is_sqlite:
                cols = [row[1] for row in conn.execute(db.text("PRAGMA table_info(leads)")).fetchall()]
                if "is_archived" not in cols:
                    conn.execute(db.text("ALTER TABLE leads ADD COLUMN is_archived BOOLEAN DEFAULT 0"))
                    conn.commit()
            else:
                try:
                    # Ensure status column is VARCHAR(50) to allow 'Archived' status
                    conn.execute(db.text("ALTER TABLE leads MODIFY COLUMN status VARCHAR(50) DEFAULT 'Pending'"))
                    conn.commit()
                except Exception:
                    pass
                try:
                    conn.execute(db.text("ALTER TABLE leads ADD COLUMN is_archived BOOLEAN DEFAULT FALSE"))
                    conn.commit()
                except Exception:
                    pass
    except Exception as e:
        print(f"[Migration Notice]: {e}")


def _seed_mailbox():
    """Seeds the initial Mailbox configuration from environment/settings if none exists."""
    try:
        mailbox = Mailbox.query.first()
        if not mailbox:
            smtp_user = os.getenv("SMTP_USER") or getattr(settings, "SMTP_USER", "") or "aipowerdsales@gmail.com"
            smtp_pass = os.getenv("SMTP_PASS") or getattr(settings, "SMTP_PASS", "") or "pfedmkydqlzlbbqh"
            smtp_host = os.getenv("SMTP_HOST") or getattr(settings, "SMTP_HOST", "smtp.gmail.com")
            smtp_port = int(os.getenv("SMTP_PORT") or getattr(settings, "SMTP_PORT", 587))

            default_mailbox = Mailbox(
                sender_name="BizCorp Sales Outreach",
                sender_email=smtp_user,
                smtp_host=smtp_host,
                smtp_port=smtp_port,
                smtp_user=smtp_user,
                smtp_pass=smtp_pass,
                use_tls=True,
                is_active=True,
            )
            db.session.add(default_mailbox)
            db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"[Mailbox Seed Notice]: {e}")


def create_app(test_config: dict | None = None) -> Flask:
    """Creates and configures the Flask application."""
    app_root = Path(__file__).resolve().parent

    app = Flask(
        __name__,
        template_folder=str(app_root / "templates"),
        static_folder=str(app_root / "static"),
    )

    # Database & Security Configuration
    db_uri = os.getenv("DATABASE_URL") or settings.DATABASE_URL
    app.config["SQLALCHEMY_DATABASE_URI"] = db_uri
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "ai-sdr-secret-key-123")

    if test_config:
        app.config.update(test_config)

    # Initialize extensions
    db.init_app(app)

    # Register blueprints
    from app.routes.dashboard import dashboard_bp
    from app.routes.company_api import company_bp
    from app.routes.leads_api import leads_bp
    from app.routes.api import api_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(company_bp)
    app.register_blueprint(leads_bp)
    app.register_blueprint(api_bp)

    # CLI Command: flask init-db
    @app.cli.command("init-db")
    def init_db_command():
        """Creates tables, applies schema migrations, and seeds defaults."""
        db.create_all()
        _run_migrations()
        _seed_company_profile()
        _seed_mailbox()
        print("Database initialized successfully with default Company profile and Mailbox seeded!")

    # Auto-create tables and seed on start if needed
    with app.app_context():
        try:
            db.create_all()
            _run_migrations()
            _seed_company_profile()
            _seed_mailbox()
        except Exception as e:
            # Fallback to local SQLite if MySQL isn't reachable
            if "mysql" in str(app.config["SQLALCHEMY_DATABASE_URI"]).lower():
                print("WARNING: Falling back to SQLite. MySQL is not connected.")
                sqlite_path = Path(__file__).resolve().parent.parent / "ai_sdr.db"
                app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{sqlite_path}"
                db.init_app(app)
                db.create_all()
                _run_migrations()
                _seed_company_profile()
                _seed_mailbox()

    return app


def _seed_company_profile():
    """Seeds the initial Company if none exists."""
    profile = Company.query.first()
    if not profile:
        default_profile = Company(
            name="CognitiveReach AI",
            industry="Enterprise B2B Software & AI Automation",
            value_proposition="We help enterprise sales teams automate personalized outreach and eliminate hallucinations with multi-agent RAG.",
            services_offered="AI SDR Agent Deployment, Real-Time Market Intelligence Ingestion, Multi-Agent Email Generation.",
            case_studies="Boosted sales meeting booking rates by 240% for SaaS clients; reduced research time per prospect from 20 minutes to under 2 seconds."
        )
        db.session.add(default_profile)
        db.session.commit()
