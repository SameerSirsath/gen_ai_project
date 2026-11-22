"""
app/routes/dashboard.py — HTML Page Rendering Routes for Dashboard UI.
"""

from __future__ import annotations

from flask import Blueprint, render_template, abort
from app.models.db import db, CompanyProfile, Lead, LeadContext, EmailLog

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/", methods=["GET"])
def index():
    """Renders main dashboard overview with stats."""
    total_leads = Lead.query.count()
    sent_emails = EmailLog.query.count()
    pending_leads = Lead.query.filter_by(status="Pending").count()
    drafted_leads = Lead.query.filter_by(status="Drafted").count()
    
    # Mock reply rate calculation
    reply_rate = "8.4%" if sent_emails > 0 else "0.0%"

    recent_leads = Lead.query.order_by(Lead.created_at.desc()).limit(5).all()

    return render_template(
        "index.html",
        total_leads=total_leads,
        sent_emails=sent_emails,
        pending_leads=pending_leads,
        drafted_leads=drafted_leads,
        reply_rate=reply_rate,
        recent_leads=recent_leads,
    )


@dashboard_bp.route("/company", methods=["GET"])
def company_settings():
    """Renders the Company Profile & Value Proposition editor."""
    profile = CompanyProfile.query.first()
    if not profile:
        profile = CompanyProfile(
            name="CognitiveReach AI",
            industry="Enterprise B2B Software & AI Automation",
            value_proposition="We help enterprise sales teams automate personalized outreach and eliminate hallucinations with multi-agent RAG.",
            services_offered="AI SDR Agent Deployment, Real-Time Market Intelligence Ingestion, Multi-Agent Email Generation.",
            case_studies="Boosted sales meeting booking rates by 240% for SaaS clients; reduced research time per prospect from 20 minutes to under 2 seconds."
        )
        db.session.add(profile)
        db.session.commit()

    return render_template("company.html", company=profile)


@dashboard_bp.route("/leads", methods=["GET"])
def leads_list():
    """Renders the Leads Management table view."""
    leads = Lead.query.order_by(Lead.created_at.desc()).all()
    return render_template("leads.html", leads=leads)


@dashboard_bp.route("/leads/<int:lead_id>", methods=["GET"])
def lead_detail(lead_id: int):
    """Renders the Lead Detail and Agent Workspace page."""
    lead = Lead.query.get(lead_id)
    if not lead:
        abort(404)

    contexts = LeadContext.query.filter_by(lead_id=lead_id).order_by(LeadContext.created_at.desc()).all()
    emails = EmailLog.query.filter_by(lead_id=lead_id).order_by(EmailLog.sent_at.desc()).all()

    return render_template(
        "lead_detail.html",
        lead=lead,
        contexts=contexts,
        emails=emails,
    )
