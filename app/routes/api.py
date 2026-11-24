"""
app/routes/api.py — API Key Management and Lead Context Processing Endpoints.
"""

from __future__ import annotations

import logging
from flask import Blueprint, request, jsonify

from app.models.db import db, ApiKey, Lead, LeadContext, CompanyProfile, Company, Mailbox
from app.services.nlp_pipeline import process_and_sync_to_chroma
from app.services.smtp_service import test_smtp_connection
from pipeline.orchestrator import run_agent_pipeline

logger = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__, url_prefix="/api")


# ─────────────────────────────────────────────────────────────────────────────
# 1. API KEY MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route("/keys", methods=["POST"])
def add_api_key():
    """
    Accepts provider, key_alias, key_value and saves to MySQL.
    The key_value is automatically encrypted at rest via the EncryptedText TypeDecorator.
    """
    data = request.get_json(silent=True) or {}
    provider = data.get("provider", "").strip().lower()
    key_alias = data.get("key_alias", "").strip()
    key_value = data.get("key_value", "").strip()

    if not provider or not key_alias or not key_value:
        return jsonify({"error": "Missing required fields: provider, key_alias, and key_value."}), 400

    new_key = ApiKey(
        provider=provider,
        key_alias=key_alias,
        key_value=key_value,
        is_active=True,
    )
    db.session.add(new_key)
    db.session.commit()

    return jsonify({
        "status": "success",
        "message": "API key stored securely.",
        "key": new_key.to_dict(mask=True),
    }), 201


@api_bp.route("/keys", methods=["GET"])
def get_api_keys():
    """
    Returns list of keys. key.key_value is automatically decrypted when accessed,
    and masked in the response for security (e.g., key[:4] + '****' + key[-4:]).
    """
    keys = ApiKey.query.order_by(ApiKey.id.desc()).all()
    results = []
    for k in keys:
        val = k.key_value or ""
        masked = (val[:4] + "****" + val[-4:]) if len(val) >= 8 else "****"
        results.append({
            "id": k.id,
            "provider": k.provider,
            "key_alias": k.key_alias,
            "key_value": masked,
            "is_active": k.is_active,
            "created_at": k.created_at.strftime("%Y-%m-%d %H:%M:%S") if k.created_at else None,
            "updated_at": k.updated_at.strftime("%Y-%m-%d %H:%M:%S") if k.updated_at else None,
        })
    return jsonify(results), 200


@api_bp.route("/keys/<int:key_id>", methods=["DELETE"])
def delete_api_key(key_id: int):
    """
    Deletes an API key by its database ID.
    """
    key_obj = db.session.get(ApiKey, key_id) if hasattr(db.session, "get") else ApiKey.query.get(key_id)
    if not key_obj:
        return jsonify({"error": f"API key with ID {key_id} not found."}), 404

    db.session.delete(key_obj)
    db.session.commit()
    return jsonify({
        "status": "success",
        "message": f"API key {key_id} deleted successfully.",
    }), 200


@api_bp.route("/keys/<int:key_id>/toggle", methods=["PATCH", "POST"])
def toggle_api_key(key_id: int):
    """
    Toggles the is_active status of an API key.
    """
    key_obj = db.session.get(ApiKey, key_id) if hasattr(db.session, "get") else ApiKey.query.get(key_id)
    if not key_obj:
        return jsonify({"error": f"API key with ID {key_id} not found."}), 404

    data = request.get_json(silent=True) or {}
    if "is_active" in data:
        key_obj.is_active = bool(data["is_active"])
    else:
        key_obj.is_active = not key_obj.is_active

    db.session.commit()
    return jsonify({
        "status": "success",
        "message": f"API key {key_id} status updated.",
        "is_active": key_obj.is_active,
    }), 200


# ─────────────────────────────────────────────────────────────────────────────
# 2. LEAD CONTEXT PROCESSING & VECTOR SYNC
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route("/leads/<int:lead_id>/process", methods=["POST"])
def process_lead_context(lead_id: int):
    """
    Extract raw_text from JSON payload.
    Create a new LeadContext record in MySQL.
    Call process_and_sync_to_chroma(lead_id, raw_text).
    If successful, update LeadContext flags: nlp_processed=True, vector_synced=True.
    Commit to DB and return the pipeline result as JSON.
    """
    data = request.get_json(silent=True) or {}
    raw_text = data.get("raw_text", "")

    if not raw_text or not raw_text.strip():
        return jsonify({"error": "Field 'raw_text' is required and cannot be empty."}), 400

    lead = Lead.query.get(lead_id)
    if not lead:
        # Create lead if it doesn't already exist so processing can succeed
        lead = Lead(id=lead_id, company_name=f"Lead #{lead_id}")
        db.session.add(lead)
        db.session.commit()

    # Create a new LeadContext record in MySQL
    context = LeadContext(
        lead_id=lead_id,
        raw_text=raw_text,
        nlp_processed=False,
        vector_synced=False,
        source_type=data.get("source_type", "Manual"),
    )
    db.session.add(context)
    db.session.commit()

    try:
        # Call process_and_sync_to_chroma
        result = process_and_sync_to_chroma(lead_id=lead_id, raw_text=raw_text)

        # If successful, update flags
        context.nlp_processed = True
        context.vector_synced = True
        db.session.commit()

        # Add success and context_id to result
        result["success"] = True
        result["context_id"] = context.id
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error processing lead {lead_id}: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({
            "status": "error",
            "error": str(e),
            "context_id": context.id,
        }), 500


# ─────────────────────────────────────────────────────────────────────────────
# 3. DIRECT OUTREACH GENERATION (FOR FRONTEND CLIENT SCRIPT)
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route("/generate", methods=["POST"])
def generate_outreach():
    """
    Direct generation endpoint called by frontend scripts.
    Accepts prospect_name and context, executes run_agent_pipeline,
    and returns a structured JSON payload compatible with script.js.
    """
    data = request.get_json(silent=True) or {}
    prospect_name = data.get("prospect_name", "").strip()
    context = data.get("context", "").strip()

    if not prospect_name or not context:
        return jsonify({"error": "Both 'prospect_name' and 'context' are required."}), 400

    try:
        # Retrieve company profile context
        profile = CompanyProfile.query.first() or Company.query.first()
        if profile:
            company_context = (
                f"{profile.name}: {getattr(profile, 'value_proposition', '')}\n"
                f"Services: {getattr(profile, 'services_offered', '')}"
            )
        else:
            company_context = "AI SDR Solutions: Autonomous personalized outreach and multi-agent RAG."

        result = run_agent_pipeline(
            prospect_name=prospect_name,
            context=context,
            company_context=company_context,
        )

        draft = result.get("draft") or {}
        evaluation = result.get("evaluation") or {}
        is_grounded = bool(result.get("approved"))
        status_label = "PASSED" if is_grounded else "BLOCKED"

        claims_used = evaluation.get("supported_claims") or draft.get("claims_used") or []
        flagged_claims = evaluation.get("unsupported_claims") or result.get("flagged_claims") or []
        reasoning = evaluation.get("reasoning") or result.get("reasoning") or "Evaluator verified claims against knowledge base."

        return jsonify({
            "status": status_label,
            "subject": draft.get("subject", ""),
            "body": draft.get("body", ""),
            "reasoning": reasoning,
            "claims_used": claims_used,
            "is_grounded": is_grounded,
            "flagged_claims": flagged_claims,
        }), 200

    except Exception as e:
        logger.error(f"Error during outreach generation: {e}", exc_info=True)
        return jsonify({
            "status": "BLOCKED",
            "error": str(e),
            "reasoning": f"Generation failed: {str(e)}",
            "is_grounded": False,
            "flagged_claims": [str(e)],
        }), 500


# ─────────────────────────────────────────────────────────────────────────────
# 4. MAILBOX SETTINGS & SMTP CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route("/mailbox", methods=["GET"])
def get_mailbox():
    """Returns the primary active outbound sender mailbox configuration."""
    mailbox = Mailbox.query.filter_by(is_active=True).first()
    if not mailbox:
        mailbox = Mailbox.query.first()
    if not mailbox:
        return jsonify({"success": False, "error": "No mailbox configured."}), 404
    return jsonify({"success": True, "mailbox": mailbox.to_dict(mask_pass=True)}), 200


@api_bp.route("/mailbox", methods=["POST", "PUT"])
def update_mailbox():
    """Creates or updates the primary active sender mailbox."""
    data = request.get_json(silent=True) or {}
    sender_name = data.get("sender_name", "").strip() or "Sales Outreach"
    sender_email = data.get("sender_email", "").strip()
    smtp_host = data.get("smtp_host", "").strip() or "smtp.gmail.com"
    smtp_port = int(data.get("smtp_port") or 587)
    smtp_user = data.get("smtp_user", "").strip() or sender_email
    smtp_pass = data.get("smtp_pass", "").strip()
    use_tls = bool(data.get("use_tls", True))

    if not sender_email or "@" not in sender_email:
        return jsonify({"success": False, "error": "Valid sender email address is required."}), 400

    mailbox = Mailbox.query.filter_by(is_active=True).first() or Mailbox.query.first()
    if not mailbox:
        if not smtp_pass:
            return jsonify({"success": False, "error": "SMTP password/app password is required for new mailbox."}), 400
        mailbox = Mailbox(
            sender_name=sender_name,
            sender_email=sender_email,
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            smtp_user=smtp_user,
            smtp_pass=smtp_pass,
            use_tls=use_tls,
            is_active=True
        )
        db.session.add(mailbox)
    else:
        mailbox.sender_name = sender_name
        mailbox.sender_email = sender_email
        mailbox.smtp_host = smtp_host
        mailbox.smtp_port = smtp_port
        mailbox.smtp_user = smtp_user
        if smtp_pass and not smtp_pass.startswith("•"):
            mailbox.smtp_pass = smtp_pass
        mailbox.use_tls = use_tls
        mailbox.is_active = True

    db.session.commit()
    return jsonify({
        "success": True,
        "message": "Mailbox settings updated successfully!",
        "mailbox": mailbox.to_dict(mask_pass=True)
    }), 200


@api_bp.route("/mailbox/test", methods=["POST"])
def test_mailbox():
    """Tests SMTP connection for the mailbox."""
    data = request.get_json(silent=True) or {}

    host = data.get("smtp_host", "").strip()
    port = int(data.get("smtp_port") or 587)
    user = data.get("smtp_user", "").strip()
    password = data.get("smtp_pass", "").strip()
    use_tls = bool(data.get("use_tls", True))

    # If password is empty or masked, read from saved DB mailbox
    if not password or password.startswith("•"):
        mb = Mailbox.query.filter_by(is_active=True).first() or Mailbox.query.first()
        if mb:
            host = host or mb.smtp_host
            port = port or mb.smtp_port
            user = user or mb.smtp_user
            password = mb.smtp_pass

    test_res = test_smtp_connection(
        host=host,
        port=port,
        user=user,
        password=password,
        use_tls=use_tls
    )
    status_code = 200 if test_res.get("success") else 400
    return jsonify(test_res), status_code

