"""
app/__init__.py — Flask Application Factory.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from flask import Flask, jsonify

from config import settings
from app.models.db import db, CompanyProfile, Lead, LeadContext, EmailLog


def create_app(test_config: dict | None = None) -> Flask:
    """Creates and configures the Flask application."""
    app_root = Path(__file__).resolve().parent

    app = Flask(
        __name__,
        template_folder=str(app_root / "templates"),
        static_folder=str(app_root / "static"),
    )

    # Database Configuration
    db_uri = settings.DATABASE_URL
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

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(company_bp)
    app.register_blueprint(leads_bp)

    # CLI Command: flask init-db
    @app.cli.command("init-db")
    def init_db_command():
        """Creates tables and seeds default CompanyProfile."""
        db.create_all()
        _seed_company_profile()
        print("Database initialized successfully with default CompanyProfile seeded!")

    # Auto-create tables and seed on start if they don't exist
    with app.app_context():
        try:
            db.create_all()
            _seed_company_profile()
        except Exception as e:
            # Fallback to local SQLite if MySQL isn't reachable
            if "mysql" in str(app.config["SQLALCHEMY_DATABASE_URI"]).lower():
                print(f"[Database] MySQL connection failed ({e}). Falling back to local SQLite.")
                sqlite_path = Path(__file__).resolve().parent.parent / "ai_sdr.db"
                app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{sqlite_path}"
                db.init_app(app)
                db.create_all()
                _seed_company_profile()

    return app


def _seed_company_profile():
    """Seeds the initial CompanyProfile if none exists."""
    profile = CompanyProfile.query.first()
    if not profile:
        default_profile = CompanyProfile(
            name="CognitiveReach AI",
            industry="Enterprise B2B Software & AI Automation",
            value_proposition="We help enterprise sales teams automate personalized outreach and eliminate hallucinations with multi-agent RAG.",
            services_offered="AI SDR Agent Deployment, Real-Time Market Intelligence Ingestion, Multi-Agent Email Generation.",
            case_studies="Boosted sales meeting booking rates by 240% for SaaS clients; reduced research time per prospect from 20 minutes to under 2 seconds."
        )
        db.session.add(default_profile)
        db.session.commit()
