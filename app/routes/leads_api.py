"""
app/routes/leads_api.py — REST API for Leads Management, NLP Processing, Multi-Agent Generation & Dispatch.
"""

from __future__ import annotations

import json
import threading
from typing import Any
from flask import Blueprint, request, jsonify, current_app

from app.models.db import db, Lead, LeadContext, CompanyProfile
from app.services.vector_service import sync_to_chroma, search_lead_context, search_company_profile
from app.services.smtp_service import send_email
from pipeline.orchestrator import run_agent_pipeline

leads_bp = Blueprint("leads_api", __name__, url_prefix="/api/leads")


def _background_process_context(app, context_id: int, lead_id: int, raw_text: str):
    """Worker function executed in a background thread to process NLP and ChromaDB indexing."""
    with app.app_context():
        try:
            sync_result = sync_to_chroma(lead_id, raw_text)
            ctx = LeadContext.query.get(context_id)
            if ctx:
                ctx.nlp_processed = True
                ctx.vector_synced = True
                ctx.keywords = json.dumps(sync_result.get("keywords", []))
                db.session.commit()
                print(f"[LeadProcessing] Background sync completed for Lead #{lead_id}")
        except Exception as e:
            print(f"[LeadProcessing] Background sync failed for Lead #{lead_id}: {e}")
            db.session.rollback()


@leads_bp.route("", methods=["GET"])
def list_leads():
    """Returns all leads."""
    leads = Lead.query.order_by(Lead.created_at.desc()).all()
    return jsonify({"success": True, "leads": [lead.to_dict() for lead in leads]}), 200


@leads_bp.route("", methods=["POST"])
def create_lead():
    """
    Creates a new lead in Auto or Manual mode.
    Auto mode: Ingests via URL.
    Manual mode: Saves custom research text.
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        company_name = data.get("company_name", "").strip()
        contact_name = data.get("contact_name", "").strip()
        email = data.get("email", "").strip()
        website_url = data.get("website_url", "").strip()
        mode = data.get("mode", "Manual")
        raw_text = data.get("context", "").strip()

        if not company_name and website_url:
            # Infer company name from URL if missing
            domain = website_url.replace("https://", "").replace("http://", "").split("/")[0]
            company_name = domain.split(".")[0].capitalize()

        if not company_name:
            return jsonify({"success": False, "error": "Company Name is required."}), 400

        lead = Lead(
            company_name=company_name,
            contact_name=contact_name,
            email=email,
            website_url=website_url,
            mode=mode,
            status="Pending",
        )
        db.session.add(lead)
        db.session.commit()

        # If Auto mode and no text provided, attempt basic web retrieval
        if mode == "Auto" and website_url and not raw_text:
            try:
                import requests
                from bs4 import BeautifulSoup
                headers = {"User-Agent": "Mozilla/5.0"}
                resp = requests.get(website_url, headers=headers, timeout=5)
                if resp.ok:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    text_parts = [p.get_text() for p in soup.find_all(["p", "h1", "h2", "h3"])]
                    raw_text = f"{company_name} Overview ({website_url}):\n" + "\n".join(text_parts[:10])
            except Exception as e:
                print(f"[Leads API] Auto scraper notice: {e}")
                raw_text = f"{company_name} is an enterprise organization operating at {website_url}."

        # Save initial lead context if text exists
        if raw_text:
            lead_ctx = LeadContext(
                lead_id=lead.id,
                raw_text=raw_text,
                source_type="Website" if mode == "Auto" else "Manual",
            )
            db.session.add(lead_ctx)
            db.session.commit()

            # Trigger background NLP & ChromaDB sync
            app = current_app._get_current_object()
            threading.Thread(
                target=_background_process_context,
                args=(app, lead_ctx.id, lead.id, raw_text),
                daemon=True
            ).start()

        return jsonify({
            "success": True,
            "message": f"Lead '{company_name}' created successfully.",
            "lead": lead.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@leads_bp.route("/<int:lead_id>", methods=["DELETE"])
def delete_lead(lead_id: int):
    """Deletes a lead and its associated contexts and emails."""
    lead = Lead.query.get(lead_id)
    if not lead:
        return jsonify({"success": False, "error": "Lead not found."}), 404

    try:
        db.session.delete(lead)
        db.session.commit()
        return jsonify({"success": True, "message": "Lead deleted successfully."}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@leads_bp.route("/<int:lead_id>", methods=["PUT"])
def update_lead(lead_id: int):
    """Updates lead contact details or status."""
    lead = Lead.query.get(lead_id)
    if not lead:
        return jsonify({"success": False, "error": "Lead not found."}), 404

    data = request.get_json(force=True, silent=True) or {}
    lead.company_name = data.get("company_name", lead.company_name)
    lead.contact_name = data.get("contact_name", lead.contact_name)
    lead.email = data.get("email", lead.email)
    lead.website_url = data.get("website_url", lead.website_url)
    lead.status = data.get("status", lead.status)

    db.session.commit()
    return jsonify({"success": True, "lead": lead.to_dict()}), 200


@leads_bp.route("/<int:lead_id>/generate", methods=["POST"])
def generate_email(lead_id: int):
    """
    Triggers multi-agent pipeline:
    1. Fetches lead context from ChromaDB (or DB fallback).
    2. Fetches our company profile from ChromaDB (or DB fallback).
    3. Runs Researcher -> Writer -> Evaluator.
    4. Updates lead status to 'Drafted'.
    """
    lead = Lead.query.get(lead_id)
    if not lead:
        return jsonify({"success": False, "error": "Lead not found."}), 404

    # 1. Retrieve Lead Context
    retrieved_lead_context = search_lead_context(lead_id, query=f"{lead.company_name} news business overview")
    if not retrieved_lead_context:
        # Fallback to direct raw text stored in LeadContext
        latest_ctx = LeadContext.query.filter_by(lead_id=lead_id).order_by(LeadContext.created_at.desc()).first()
        retrieved_lead_context = latest_ctx.raw_text if latest_ctx else f"{lead.company_name} corporate developments."

    # 2. Retrieve Our Company Profile Context
    retrieved_company_context = search_company_profile(query=f"{lead.company_name} sales solutions")
    if not retrieved_company_context:
        profile = CompanyProfile.query.first()
        if profile:
            retrieved_company_context = f"{profile.name}: {profile.value_proposition}\nServices: {profile.services_offered}"
        else:
            retrieved_company_context = "AI SDR Solutions: Autonomous personalized outreach and multi-agent RAG."

    # 3. Execute Multi-Agent Pipeline
    result = run_agent_pipeline(
        prospect_name=lead.company_name,
        context=retrieved_lead_context,
        company_context=retrieved_company_context
    )

    draft = result.get("draft") or {}
    evaluation = result.get("evaluation") or {}
    is_grounded = bool(result.get("approved"))
    status_label = "PASSED" if is_grounded else "BLOCKED"

    # Update lead status
    lead.status = "Drafted"
    db.session.commit()

    return jsonify({
        "success": True,
        "status": status_label,
        "is_grounded": is_grounded,
        "subject": draft.get("subject", ""),
        "body": draft.get("body", ""),
        "claims_used": draft.get("claims_used", []),
        "flagged_claims": evaluation.get("flagged_claims", []) or result.get("flagged_claims", []),
        "reasoning": evaluation.get("reasoning", "") or result.get("reasoning", ""),
        "signals": result.get("signals", {}),
    }), 200


@leads_bp.route("/<int:lead_id>/send", methods=["POST"])
def dispatch_email(lead_id: int):
    """
    Sends email draft via SMTP and logs to EmailLog table.
    """
    lead = Lead.query.get(lead_id)
    if not lead:
        return jsonify({"success": False, "error": "Lead not found."}), 404

    data = request.get_json(force=True, silent=True) or {}
    subject = data.get("subject", "").strip()
    body = data.get("body", "").strip()
    recipient_email = data.get("email", lead.email).strip()

    if not subject or not body:
        return jsonify({"success": False, "error": "Subject and Body are required."}), 400

    if not recipient_email:
        return jsonify({"success": False, "error": "Lead email address is missing."}), 400

    send_res = send_email(
        to_email=recipient_email,
        subject=subject,
        body=body,
        lead_id=lead.id,
        evaluator_score=1.0,
        evaluator_reasoning="Dispatched via Web UI by user approval."
    )

    if send_res.get("success"):
        lead.status = "Sent"
        db.session.commit()
        return jsonify({
            "success": True,
            "message": send_res.get("message", "Email sent successfully!"),
            "lead": lead.to_dict()
        }), 200
    else:
        return jsonify({
            "success": False,
            "error": send_res.get("message", "SMTP dispatch failed.")
        }), 500
