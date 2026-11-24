"""
app/routes/company_api.py — REST API for Managing User's Company Profile & Service Catalog.
"""

from __future__ import annotations

import json
from flask import Blueprint, request, jsonify
from app.models.db import db, CompanyProfile
from app.services.vector_service import sync_company_profile_to_chroma

company_bp = Blueprint("company_api", __name__, url_prefix="/api/company")


def _get_services_list(profile: CompanyProfile) -> list:
    """Helper to deserialize services_offered into a list of dicts."""
    raw = profile.services_offered or ""
    if raw.strip().startswith("["):
        try:
            return json.loads(raw)
        except Exception:
            return []
    items = []
    if raw:
        for s in raw.split("\n"):
            if s.strip():
                items.append({"name": s.strip(), "category": "General Solution", "description": "Enterprise service."})
    return items


@company_bp.route("", methods=["GET"])
def get_company():
    """Fetches user company profile."""
    profile = CompanyProfile.query.first()
    if not profile:
        profile = CompanyProfile()
        db.session.add(profile)
        db.session.commit()
    data = profile.to_dict()
    data["services"] = _get_services_list(profile)
    return jsonify({"success": True, "company": data}), 200


@company_bp.route("", methods=["PUT", "POST"])
def update_company():
    """Updates user company profile and syncs to ChromaDB."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        profile = CompanyProfile.query.first()
        if not profile:
            profile = CompanyProfile()
            db.session.add(profile)

        profile.name = data.get("name", profile.name)
        profile.industry = data.get("industry", profile.industry)
        profile.value_proposition = data.get("value_proposition", profile.value_proposition)
        if "services_offered" in data:
            profile.services_offered = data.get("services_offered", profile.services_offered)
        profile.case_studies = data.get("case_studies", profile.case_studies)

        db.session.commit()

        # Combine text fields to embed into ChromaDB under 'our_company' namespace
        combined_text = (
            f"Company Name: {profile.name}\n"
            f"Industry: {profile.industry}\n"
            f"Value Proposition: {profile.value_proposition}\n"
            f"Services & Solutions: {profile.services_offered}\n"
            f"Case Studies & Metrics: {profile.case_studies}"
        )

        try:
            sync_result = sync_company_profile_to_chroma(combined_text)
        except Exception as e:
            sync_result = {"status": "skipped", "note": str(e)}

        res_data = profile.to_dict()
        res_data["services"] = _get_services_list(profile)

        return jsonify({
            "success": True,
            "message": "Company profile saved and synced to ChromaDB successfully.",
            "company": res_data,
            "vector_sync": sync_result,
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@company_bp.route("/services", methods=["POST"])
def add_service():
    """Adds a new service item to the service catalog."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        name = data.get("name", "").strip()
        category = data.get("category", "Core Service").strip()
        description = data.get("description", "").strip()

        if not name:
            return jsonify({"success": False, "error": "Service Name is required."}), 400

        profile = CompanyProfile.query.first()
        if not profile:
            profile = CompanyProfile(name="CognitiveReach AI")
            db.session.add(profile)

        services = _get_services_list(profile)
        services.append({
            "name": name,
            "category": category,
            "description": description or f"{name} enterprise solution."
        })

        profile.services_offered = json.dumps(services)
        db.session.commit()

        return jsonify({
            "success": True,
            "message": f"Service '{name}' added to catalog.",
            "services": services
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@company_bp.route("/services/<int:service_idx>", methods=["DELETE"])
def delete_service(service_idx: int):
    """Deletes a service item by index."""
    try:
        profile = CompanyProfile.query.first()
        if not profile:
            return jsonify({"success": False, "error": "Company profile not found."}), 404

        services = _get_services_list(profile)
        if 0 <= service_idx < len(services):
            deleted = services.pop(service_idx)
            profile.services_offered = json.dumps(services)
            db.session.commit()
            return jsonify({
                "success": True,
                "message": f"Service '{deleted.get('name')}' removed.",
                "services": services
            }), 200
        else:
            return jsonify({"success": False, "error": "Invalid service index."}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
