"""
app/routes/api.py — API Key Management and Lead Context Processing Endpoints.
"""

from __future__ import annotations

import logging
from flask import Blueprint, request, jsonify

from app.models.db import db, ApiKey, Lead, LeadContext
from app.services.nlp_pipeline import process_and_sync_to_chroma

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
    key_obj = ApiKey.query.get(key_id)
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
    key_obj = ApiKey.query.get(key_id)
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
