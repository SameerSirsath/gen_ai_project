"""
app/routes/company_api.py — REST API for Managing User's Company Profile.
"""

from __future__ import annotations

from flask import Blueprint, request, jsonify
from app.models.db import db, CompanyProfile
from app.services.vector_service import sync_company_profile_to_chroma

company_bp = Blueprint("company_api", __name__, url_prefix="/api/company")


@company_bp.route("", methods=["GET"])
def get_company():
    """Fetches user company profile."""
    profile = CompanyProfile.query.first()
    if not profile:
        profile = CompanyProfile()
        db.session.add(profile)
        db.session.commit()
    return jsonify({"success": True, "company": profile.to_dict()}), 200


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

        sync_result = sync_company_profile_to_chroma(combined_text)

        return jsonify({
            "success": True,
            "message": "Company profile saved and synced to ChromaDB successfully.",
            "company": profile.to_dict(),
            "vector_sync": sync_result,
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
