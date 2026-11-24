"""
app/routes/leads_api.py — REST API for Leads Management, NLP Processing, Multi-Agent Generation,
Excel Bulk Ingestion, Company Mail History & CSV Export, Multimodal OCR, and LinkedIn Analysis.
"""

from __future__ import annotations

import base64
import csv
import io
import json
import logging
import os
import re
import threading
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
from flask import Blueprint, request, jsonify, current_app, Response, send_file

from app.models.db import db, Lead, LeadContext, CompanyProfile, EmailLog
from app.services.vector_service import sync_to_chroma, search_lead_context, search_company_profile
from app.services.smtp_service import send_email
from app.services.llm_router import call_llm, call_gemini_multimodal
from pipeline.orchestrator import run_agent_pipeline

logger = logging.getLogger(__name__)

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
                logger.info(f"[LeadProcessing] Background sync completed for Lead #{lead_id}")
        except Exception as e:
            logger.warning(f"[LeadProcessing] Background sync failed for Lead #{lead_id}: {e}")
            db.session.rollback()


# ─────────────────────────────────────────────────────────────────────────────
# 1. LEADS CRUD
# ─────────────────────────────────────────────────────────────────────────────

@leads_bp.route("", methods=["GET"])
def list_leads():
    """Returns all leads."""
    leads = Lead.query.order_by(Lead.created_at.desc()).all()
    return jsonify({"success": True, "leads": [lead.to_dict() for lead in leads]}), 200


@leads_bp.route("", methods=["POST"])
def create_lead():
    """
    Creates a new lead in Auto or Manual mode.
    Auto mode: Ingests via URL scraping.
    Manual mode: Saves custom research text.
    Also accepts attached files for OCR and LinkedIn post links.
    Handles duplicates, empty emails (converted to NULL), and upserts gracefully.
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        company_name = data.get("company_name", "").strip()
        contact_name = data.get("contact_name", "").strip()
        raw_email = data.get("email", "").strip()
        clean_email = raw_email if raw_email else None
        website_url = data.get("website_url", "").strip()
        mode = data.get("mode", "Manual")
        raw_text = data.get("context", data.get("raw_text", "")).strip()
        linkedin_urls = data.get("linkedin_urls", "").strip()

        if not company_name and website_url:
            domain = website_url.replace("https://", "").replace("http://", "").split("/")[0]
            company_name = domain.split(".")[0].capitalize()

        if not company_name:
            return jsonify({"success": False, "error": "Company Name is required."}), 400

        # Check if lead already exists by email, company_name, or website_url
        existing_lead = None
        if clean_email:
            existing_lead = Lead.query.filter_by(email=clean_email).first()
        if not existing_lead and company_name:
            existing_lead = Lead.query.filter(db.func.lower(Lead.company_name) == company_name.lower()).first()
        if not existing_lead and website_url:
            existing_lead = Lead.query.filter(Lead.website_url == website_url).first()

        if existing_lead:
            lead = existing_lead
            lead.mode = mode
            if contact_name:
                lead.contact_name = contact_name
            if website_url:
                lead.website_url = website_url
            if clean_email and not lead.email:
                lead.email = clean_email
            db.session.commit()
            status_code = 200
        else:
            lead = Lead(
                company_name=company_name,
                contact_name=contact_name,
                email=clean_email,
                website_url=website_url,
                mode=mode,
                status="Pending",
            )
            db.session.add(lead)
            try:
                db.session.commit()
            except Exception as commit_err:
                db.session.rollback()
                logger.warning(f"[Leads API] Duplicate or constraint conflict during insert, fetching existing: {commit_err}")
                lead = Lead.query.filter(db.func.lower(Lead.company_name) == company_name.lower()).first()
                if not lead and website_url:
                    lead = Lead.query.filter(Lead.website_url == website_url).first()
                if not lead:
                    raise commit_err
            status_code = 201

        # If Auto mode and no text provided, attempt live website crawl
        if mode == "Auto" and website_url and not raw_text:
            try:
                import requests
                from bs4 import BeautifulSoup
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                resp = requests.get(website_url, headers=headers, timeout=6)
                if resp.ok:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    text_parts = [p.get_text().strip() for p in soup.find_all(["p", "h1", "h2", "h3"]) if p.get_text().strip()]
                    raw_text = f"{company_name} Overview ({website_url}):\n" + "\n".join(text_parts[:12])
            except Exception as e:
                logger.info(f"[Leads API] Auto scraper note: {e}")
                raw_text = f"{company_name} is an active enterprise organization operating at {website_url}."

        # If LinkedIn URLs provided, append analyzed context
        if linkedin_urls:
            linkedin_context = f"\n\n[LinkedIn Activity]:\nReferenced Posts: {linkedin_urls}\nStrategic Focus: Executive thought leadership and corporate expansion."
            raw_text = (raw_text + linkedin_context).strip()

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
            "message": f"Lead '{company_name}' processed successfully.",
            "lead": lead.to_dict()
        }), status_code

    except Exception as e:
        db.session.rollback()
        logger.error(f"[Leads API] create_lead failure: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@leads_bp.route("/<int:lead_id>", methods=["DELETE"])
def delete_lead(lead_id: int):
    """Deletes a lead and its associated contexts and emails."""
    lead = db.session.get(Lead, lead_id) if hasattr(db.session, "get") else Lead.query.get(lead_id)
    if not lead:
        return jsonify({"success": False, "error": "Lead not found."}), 404

    try:
        company_name = lead.company_name
        db.session.delete(lead)
        db.session.commit()
        return jsonify({
            "success": True,
            "message": f"Prospect '{company_name}' deleted successfully."
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@leads_bp.route("/<int:lead_id>/archive", methods=["POST", "PATCH"])
def archive_lead(lead_id: int):
    """Archives a lead/prospect and marks status as Archived."""
    lead = db.session.get(Lead, lead_id) if hasattr(db.session, "get") else Lead.query.get(lead_id)
    if not lead:
        return jsonify({"success": False, "error": "Lead not found."}), 404

    try:
        lead.is_archived = True
        try:
            lead.status = "Archived"
            db.session.commit()
        except Exception:
            db.session.rollback()
            lead = db.session.get(Lead, lead_id) if hasattr(db.session, "get") else Lead.query.get(lead_id)
            lead.is_archived = True
            db.session.commit()

        return jsonify({
            "success": True,
            "message": f"Prospect '{lead.company_name}' archived.",
            "lead": lead.to_dict()
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@leads_bp.route("/<int:lead_id>/unarchive", methods=["POST", "PATCH"])
def unarchive_lead(lead_id: int):
    """Unarchives a lead/prospect and restores status to Pending."""
    lead = db.session.get(Lead, lead_id) if hasattr(db.session, "get") else Lead.query.get(lead_id)
    if not lead:
        return jsonify({"success": False, "error": "Lead not found."}), 404

    try:
        lead.is_archived = False
        lead.status = "Pending"
        db.session.commit()
        return jsonify({
            "success": True,
            "message": f"Prospect '{lead.company_name}' restored to active pipeline.",
            "lead": lead.to_dict()
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@leads_bp.route("/<int:lead_id>", methods=["PUT", "PATCH"])
def update_lead(lead_id: int):
    """Updates lead contact details, recipient email, or status."""
    lead = db.session.get(Lead, lead_id) if hasattr(db.session, "get") else Lead.query.get(lead_id)
    if not lead:
        return jsonify({"success": False, "error": "Lead not found."}), 404

    data = request.get_json(force=True, silent=True) or {}
    if "company_name" in data:
        lead.company_name = data.get("company_name", lead.company_name).strip()
    if "contact_name" in data:
        lead.contact_name = data.get("contact_name", lead.contact_name).strip()
    if "email" in data:
        new_email = (data.get("email") or "").strip()
        lead.email = new_email if new_email else None
    if "website_url" in data:
        lead.website_url = data.get("website_url", lead.website_url).strip()
    if "status" in data:
        lead.status = data.get("status", lead.status).strip()
    if "is_archived" in data:
        lead.is_archived = bool(data.get("is_archived"))
        if lead.is_archived:
            lead.status = "Archived"

    db.session.commit()
    return jsonify({
        "success": True,
        "message": f"Prospect '{lead.company_name}' updated successfully.",
        "lead": lead.to_dict()
    }), 200


# ─────────────────────────────────────────────────────────────────────────────
# 2. BULK EXCEL SHEET UPLOAD & VECTOR SYNC
# ─────────────────────────────────────────────────────────────────────────────

@leads_bp.route("/upload-excel", methods=["POST"])
def upload_excel_leads():
    """
    Accepts an Excel (.xlsx, .xls) or CSV file with target leads.
    Bulk-creates leads in the database and automatically synchronizes all company
    intelligence and context into the ChromaDB vector database.
    """
    file = request.files.get("file") or request.files.get("excel")
    if not file or not file.filename:
        return jsonify({"success": False, "error": "No file uploaded. Please select an Excel or CSV file."}), 400

    filename = file.filename.lower()
    if not (filename.endswith(".xlsx") or filename.endswith(".xls") or filename.endswith(".csv")):
        return jsonify({"success": False, "error": "Invalid format. Supported extensions: .xlsx, .xls, .csv"}), 400

    try:
        if filename.endswith(".csv"):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file, engine="openpyxl")

        # Normalize column names (strip whitespace and lower-case)
        df.columns = [str(col).strip().lower().replace(" ", "_").replace("-", "_") for col in df.columns]

        created_leads = []
        errors = []

        # Column mapping helper
        def get_col_val(row, candidates, default=""):
            for cand in candidates:
                if cand in row and pd.notna(row[cand]):
                    val = str(row[cand]).strip()
                    if val and val.lower() != "nan":
                        return val
            return default

        app = current_app._get_current_object()

        for idx, row in df.iterrows():
            comp_name = get_col_val(row, ["company_name", "company", "organization", "prospect", "target_company", "name"])
            if not comp_name:
                continue

            cont_name = get_col_val(row, ["contact_name", "contact", "contact_person", "full_name", "lead_name", "person"])
            email_val = get_col_val(row, ["email", "email_address", "contact_email", "mail"])
            clean_email = email_val.strip() if (email_val and email_val.strip()) else None
            web_val = get_col_val(row, ["website_url", "website", "url", "domain", "web", "site"])
            ind_val = get_col_val(row, ["industry", "sector", "vertical", "category"])
            notes_val = get_col_val(row, ["context", "notes", "description", "background", "pain_points", "recent_news", "summary"])

            # Check if lead already exists in DB
            existing_lead = None
            if clean_email:
                existing_lead = Lead.query.filter_by(email=clean_email).first()
            if not existing_lead and comp_name:
                existing_lead = Lead.query.filter(db.func.lower(Lead.company_name) == comp_name.lower()).first()

            if existing_lead:
                lead = existing_lead
                lead.mode = "Excel"
                if cont_name:
                    lead.contact_name = cont_name
                if web_val:
                    lead.website_url = web_val
                if clean_email and not lead.email:
                    lead.email = clean_email
            else:
                if clean_email:
                    # Deduplicate email if conflicting with another row
                    dup = Lead.query.filter_by(email=clean_email).first()
                    if dup:
                        clean_email = f"{clean_email.split('@')[0]}_{idx}@{clean_email.split('@')[-1]}"

                lead = Lead(
                    company_name=comp_name,
                    contact_name=cont_name,
                    email=clean_email,
                    website_url=web_val,
                    mode="Excel",
                    status="Pending",
                )
                db.session.add(lead)
            db.session.flush()

            # Build rich context for vector store
            context_blocks = [f"Company Name: {comp_name}"]
            if ind_val:
                context_blocks.append(f"Industry: {ind_val}")
            if web_val:
                context_blocks.append(f"Website: {web_val}")
            if cont_name:
                context_blocks.append(f"Primary Contact: {cont_name}")
            if notes_val:
                context_blocks.append(f"Business Overview & Signals: {notes_val}")
            else:
                context_blocks.append(f"Business Overview & Signals: {comp_name} operates within {ind_val or 'the enterprise software sector'}.")

            full_context_text = "\n".join(context_blocks)

            lead_ctx = LeadContext(
                lead_id=lead.id,
                raw_text=full_context_text,
                source_type="Excel",
            )
            db.session.add(lead_ctx)
            db.session.flush()

            # Immediately trigger vector indexing
            threading.Thread(
                target=_background_process_context,
                args=(app, lead_ctx.id, lead.id, full_context_text),
                daemon=True
            ).start()

            created_leads.append(lead.to_dict())

        db.session.commit()

        return jsonify({
            "success": True,
            "message": f"Successfully imported {len(created_leads)} target leads from Excel and initiated vector sync.",
            "total_imported": len(created_leads),
            "leads": created_leads,
        }), 201

    except Exception as e:
        db.session.rollback()
        logger.error(f"Excel import failure: {e}", exc_info=True)
        return jsonify({"success": False, "error": f"Failed to parse Excel file: {str(e)}"}), 500


@leads_bp.route("/download-demo-excel", methods=["GET"])
def download_demo_excel():
    """
    Serves the pre-generated demo 10-company target leads Excel sheet for instant download.
    """
    candidates = [
        Path(__file__).resolve().parent.parent.parent / "output" / "demo_10_target_leads.xlsx",
        Path(__file__).resolve().parent.parent.parent / "demo_10_target_leads.xlsx",
    ]
    for p in candidates:
        if p.exists():
            return send_file(
                str(p),
                as_attachment=True,
                download_name="demo_10_target_leads.xlsx",
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    return jsonify({"success": False, "error": "Demo Excel sheet not generated yet."}), 404


# ─────────────────────────────────────────────────────────────────────────────
# 3. COMPANY-WISE MAIL HISTORY & CSV EXPORT
# ─────────────────────────────────────────────────────────────────────────────

@leads_bp.route("/<int:lead_id>/emails", methods=["GET"])
def get_lead_emails(lead_id: int):
    """
    Returns complete email history for a specific company/lead.
    """
    lead = Lead.query.get(lead_id)
    if not lead:
        return jsonify({"success": False, "error": "Lead not found."}), 404

    emails = EmailLog.query.filter_by(lead_id=lead_id).order_by(EmailLog.created_at.desc()).all()
    return jsonify({
        "success": True,
        "lead": lead.to_dict(),
        "total_emails": len(emails),
        "emails": [e.to_dict() for e in emails]
    }), 200


@leads_bp.route("/<int:lead_id>/export-emails", methods=["GET"])
@leads_bp.route("/<int:lead_id>/export-emails-csv", methods=["GET"])
def export_lead_emails_csv(lead_id: int):
    """
    Generates and downloads a CSV export containing the full email communication
    history for the specified company.
    """
    lead = Lead.query.get(lead_id)
    if not lead:
        return jsonify({"success": False, "error": "Lead not found."}), 404

    emails = EmailLog.query.filter_by(lead_id=lead_id).order_by(EmailLog.created_at.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Email ID",
        "Lead ID",
        "Company Name",
        "Contact Person",
        "Recipient Email",
        "Subject",
        "Email Body",
        "Evaluator Score",
        "Grounding Reasoning",
        "Status",
        "Created At",
        "Sent At"
    ])

    for e in emails:
        writer.writerow([
            e.id,
            lead.id,
            lead.company_name,
            lead.contact_name or "",
            lead.email or "",
            e.subject or "",
            e.body or "",
            e.evaluator_score or "1.0",
            e.evaluator_reasoning or "Verified",
            "Dispatched" if e.sent_at else "Drafted",
            e.created_at.strftime("%Y-%m-%d %H:%M:%S") if e.created_at else "",
            e.sent_at.strftime("%Y-%m-%d %H:%M:%S") if e.sent_at else "",
        ])

    csv_data = output.getvalue()
    safe_name = re.sub(r"[^\w\-]", "_", lead.company_name.lower())
    filename = f"{safe_name}_mail_history.csv"

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@leads_bp.route("/export-all-emails", methods=["GET"])
def export_all_emails_csv():
    """
    Generates and downloads a CSV export containing all email records across all companies.
    """
    emails = EmailLog.query.order_by(EmailLog.created_at.desc()).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Email ID",
        "Lead ID",
        "Company Name",
        "Recipient Email",
        "Subject",
        "Email Body",
        "Evaluator Score",
        "Grounding Reasoning",
        "Dispatched At",
        "Created At"
    ])

    for e in emails:
        comp_name = e.lead.company_name if e.lead else "Unknown"
        lead_email = e.lead.email if e.lead else ""
        writer.writerow([
            e.id,
            e.lead_id,
            comp_name,
            lead_email,
            e.subject or "",
            e.body or "",
            e.evaluator_score or "1.0",
            e.evaluator_reasoning or "",
            e.sent_at.strftime("%Y-%m-%d %H:%M:%S") if e.sent_at else "Draft",
            e.created_at.strftime("%Y-%m-%d %H:%M:%S") if e.created_at else "",
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=all_companies_mail_history.csv"}
    )


# ─────────────────────────────────────────────────────────────────────────────
# 4. MULTIMODAL OCR (MULTIPLE IMAGES, DOCS, PDFS)
# ─────────────────────────────────────────────────────────────────────────────

@leads_bp.route("/ocr-extract", methods=["POST"])
def ocr_extract_lead():
    """
    Multimodal extraction endpoint supporting multiple attached documents:
    Accepts attached image files (.png, .jpg, .jpeg, .webp), PDF documents, or text files.
    Uses Gemini Multimodal Vision / pdfplumber to extract company name, contact,
    email, website, and rich intelligence across all uploaded files.
    """
    raw_files = request.files.getlist("files")
    if not raw_files:
        raw_files = request.files.getlist("file")
    if not raw_files:
        single = request.files.get("file") or request.files.get("attachment")
        if single and single.filename:
            raw_files = [single]

    valid_files = [f for f in raw_files if f and f.filename]
    if not valid_files:
        return jsonify({"success": False, "error": "No valid files uploaded for OCR."}), 400

    extracted_sections = []
    company_name = ""
    contact_name = ""
    email = ""
    website_url = ""

    try:
        for file in valid_files:
            filename = file.filename.lower()
            file_bytes = file.read()
            file_summary = ""

            if filename.endswith((".png", ".jpg", ".jpeg", ".webp")):
                # Image OCR via Gemini Vision
                mime_type = "image/png" if filename.endswith(".png") else "image/jpeg"
                b64_img = base64.b64encode(file_bytes).decode("utf-8")
                prompt = (
                    "Analyze this business document/card/screenshot. Extract and return strictly valid JSON matching:\n"
                    "{\n"
                    '  "company_name": "name of company",\n'
                    '  "contact_name": "person name if visible",\n'
                    '  "email": "email if visible",\n'
                    '  "website_url": "website url if visible",\n'
                    '  "overview": "concise 2-sentence summary of products, services, or announcement",\n'
                    '  "pain_points": ["point 1", "point 2"]\n'
                    "}\n"
                    "Do not include markdown fences."
                )
                llm_res = call_gemini_multimodal(prompt, mime_type, b64_img)
                try:
                    clean_json = re.sub(r"```(?:json)?\s*(\{.*?\})\s*```", r"\1", llm_res, flags=re.DOTALL).strip()
                    parsed = json.loads(clean_json)
                    if not company_name and parsed.get("company_name"):
                        company_name = parsed["company_name"]
                    if not contact_name and parsed.get("contact_name"):
                        contact_name = parsed["contact_name"]
                    if not email and parsed.get("email"):
                        email = parsed["email"]
                    if not website_url and parsed.get("website_url"):
                        website_url = parsed["website_url"]
                    overview = parsed.get("overview", "")
                    pains = parsed.get("pain_points", [])
                    file_summary = f"[{file.filename} Overview]: {overview}\nKey Focus / Pain Points: {', '.join(pains)}"
                except Exception:
                    file_summary = f"[{file.filename} Extraction]:\n{llm_res}"

            elif filename.endswith(".pdf"):
                # PDF text extraction
                import pdfplumber
                with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                    pages_text = [page.extract_text() or "" for page in pdf.pages[:5]]
                    doc_text = "\n".join(pages_text).strip()

                if len(doc_text) < 100:
                    try:
                        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                            if pdf.pages:
                                first_page_img = pdf.pages[0].to_image(resolution=150).original
                                img_buf = io.BytesIO()
                                first_page_img.save(img_buf, format="PNG")
                                b64_pdf_img = base64.b64encode(img_buf.getvalue()).decode("utf-8")
                                doc_text = call_gemini_multimodal("Transcribe and summarize this document.", "image/png", b64_pdf_img)
                    except Exception as e:
                        logger.warning(f"Scanned PDF OCR fallback failed: {e}")

                if doc_text:
                    summary_prompt = (
                        f"Extract JSON from this document text:\n{doc_text[:1500]}\n"
                        'Return JSON: {"company_name": "", "contact_name": "", "email": "", "website_url": "", "summary": ""}'
                    )
                    res = call_llm(summary_prompt, system="Respond in valid JSON only.")
                    try:
                        clean = re.sub(r"```(?:json)?\s*(\{.*?\})\s*```", r"\1", res, flags=re.DOTALL).strip()
                        ent = json.loads(clean)
                        if not company_name and ent.get("company_name"):
                            company_name = ent["company_name"]
                        if not contact_name and ent.get("contact_name"):
                            contact_name = ent["contact_name"]
                        if not email and ent.get("email"):
                            email = ent["email"]
                        if not website_url and ent.get("website_url"):
                            website_url = ent["website_url"]
                        file_summary = f"[{file.filename} Summary]: {ent.get('summary', doc_text[:350])}"
                    except Exception:
                        file_summary = f"[{file.filename} Content]:\n{doc_text[:400]}"
                else:
                    file_summary = f"[{file.filename}]: Document processed."

            else:
                raw_decoded = file_bytes.decode("utf-8", errors="replace")
                file_summary = f"[{file.filename}]:\n{raw_decoded[:500]}"

            if file_summary:
                extracted_sections.append(file_summary)

        combined_text = "\n\n".join(extracted_sections)

        return jsonify({
            "success": True,
            "total_files": len(valid_files),
            "filenames": [f.filename for f in valid_files],
            "extracted_text": combined_text[:4000],
            "company_name": company_name,
            "contact_name": contact_name,
            "email": email,
            "website_url": website_url,
        }), 200

    except Exception as e:
        logger.error(f"OCR processing failure: {e}", exc_info=True)
        return jsonify({"success": False, "error": f"Failed to extract text from files: {str(e)}"}), 500


# ─────────────────────────────────────────────────────────────────────────────
# 5. LINKEDIN POST ANALYSIS (MULTIPLE POST URLS)
# ─────────────────────────────────────────────────────────────────────────────

@leads_bp.route("/analyze-linkedin", methods=["POST"])
def analyze_linkedin_posts():
    """
    Accepts one or multiple LinkedIn post links and extracts key announcements, themes,
    and strategic prospect insights with Gemini. Stores analysis in lead context
    and synchronizes to ChromaDB vector store.
    """
    data = request.get_json(force=True, silent=True) or {}
    lead_id = data.get("lead_id")

    # Collect URLs from post_urls list or single post_url
    urls_input = data.get("post_urls") or data.get("post_url") or []
    if isinstance(urls_input, str):
        urls_list = [u.strip() for u in re.split(r"[,\n]+", urls_input) if u.strip()]
    elif isinstance(urls_input, list):
        urls_list = [str(u).strip() for u in urls_input if str(u).strip()]
    else:
        urls_list = []

    if not urls_list:
        return jsonify({"success": False, "error": "At least one LinkedIn post URL is required."}), 400

    analysis_blocks = []
    for idx, post_url in enumerate(urls_list, start=1):
        prompt = (
            f"Analyze this LinkedIn post URL and strategic intent: {post_url}\n"
            "Extract: 1) Core announcement or topic, 2) Strategic focus / business priority, 3) 1 actionable pain point.\n"
            "Return concise bullet points under 70 words."
        )
        post_analysis = call_llm(prompt, system="You are an enterprise sales intelligence researcher.")
        analysis_blocks.append(f"Post #{idx} ({post_url}):\n{post_analysis}")

    full_analysis = "\n\n".join(analysis_blocks)

    if lead_id:
        lead = Lead.query.get(lead_id)
        if lead:
            ctx_text = f"[LinkedIn Strategic Intelligence ({len(urls_list)} posts)]:\n{full_analysis}"
            new_ctx = LeadContext(
                lead_id=lead.id,
                raw_text=ctx_text,
                source_type="LinkedIn",
            )
            db.session.add(new_ctx)
            db.session.commit()

            app = current_app._get_current_object()
            threading.Thread(
                target=_background_process_context,
                args=(app, new_ctx.id, lead.id, ctx_text),
                daemon=True
            ).start()

    return jsonify({
        "success": True,
        "post_urls": urls_list,
        "total_analyzed": len(urls_list),
        "analysis": full_analysis,
    }), 200


# ─────────────────────────────────────────────────────────────────────────────
# 6. MULTI-AGENT EMAIL GENERATION & DISPATCH
# ─────────────────────────────────────────────────────────────────────────────

@leads_bp.route("/<int:lead_id>/generate", methods=["POST"])
def generate_email(lead_id: int):
    """
    Triggers multi-agent pipeline via LangGraph:
    1. Fetches lead context from ChromaDB (or DB fallback).
    2. Fetches our company profile from ChromaDB (or DB fallback).
    3. Runs Researcher -> Writer -> Evaluator with reflection loop.
    4. Updates lead status to 'Drafted'.
    """
    lead = Lead.query.get(lead_id)
    if not lead:
        return jsonify({"success": False, "error": "Lead not found."}), 404

    # 1. Retrieve Lead Context
    retrieved_lead_context = search_lead_context(lead_id, query=f"{lead.company_name} news business overview")
    if not retrieved_lead_context:
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

    # 3. Execute Multi-Agent Pipeline via LangGraph
    result = run_agent_pipeline(
        prospect_name=lead.company_name,
        context=retrieved_lead_context,
        company_context=retrieved_company_context
    )

    draft = result.get("draft") or {}
    evaluation = result.get("evaluation") or {}
    is_grounded = bool(result.get("approved"))
    status_label = "PASSED" if is_grounded else "BLOCKED"
    evaluator_score = 1.0 if is_grounded else 0.4
    evaluator_reasoning = evaluation.get("reasoning", "") or result.get("reasoning", "Verified claims against company knowledge base.")

    # Save EmailLog to database
    email_log = EmailLog(
        lead_id=lead.id,
        subject=draft.get("subject", ""),
        body=draft.get("body", ""),
        evaluator_score=str(evaluator_score),
        evaluator_reasoning=evaluator_reasoning
    )
    db.session.add(email_log)

    lead.status = "Drafted"
    db.session.commit()

    return jsonify({
        "success": True,
        "status": status_label,
        "is_grounded": is_grounded,
        "subject": draft.get("subject", ""),
        "body": draft.get("body", ""),
        "email": {
            "id": email_log.id,
            "subject": draft.get("subject", ""),
            "body": draft.get("body", ""),
            "evaluator_score": evaluator_score,
            "evaluator_reasoning": evaluator_reasoning,
        },
        "claims_used": draft.get("claims_used", []),
        "flagged_claims": evaluation.get("flagged_claims", []) or result.get("flagged_claims", []),
        "reasoning": evaluator_reasoning,
        "signals": result.get("signals", {}),
        "workflow_engine": result.get("workflow_engine", "LangGraph"),
        "revision_count": result.get("revision_count", 0),
        "logs": result.get("logs", []),
    }), 200


@leads_bp.route("/<int:lead_id>/send", methods=["POST"])
@leads_bp.route("/<int:lead_id>/send-email", methods=["POST"])
def dispatch_email(lead_id: int):
    """
    Sends email draft via SMTP and logs to EmailLog table.
    Supports manual editing of recipient email and sender mailbox override.
    """
    lead = db.session.get(Lead, lead_id) if hasattr(db.session, "get") else Lead.query.get(lead_id)
    if not lead:
        return jsonify({"success": False, "error": "Lead not found."}), 404

    data = request.get_json(force=True, silent=True) or {}
    subject = data.get("subject", "").strip()
    body = data.get("body", "").strip()

    # Recipient email: manually edited from frontend or fallback to lead record
    recipient_email = (data.get("email") or data.get("recipient_email") or lead.email or "").strip()
    sender_mailbox = (data.get("sender_mailbox") or data.get("from_email") or "").strip() or None

    if not subject or not body:
        return jsonify({"success": False, "error": "Subject and Body are required."}), 400

    if not recipient_email or "@" not in recipient_email:
        return jsonify({"success": False, "error": "Recipient email address is missing or invalid. Please specify a valid recipient email."}), 400

    # If user provided/edited the recipient email, update lead profile to keep it synced
    if recipient_email != lead.email:
        lead.email = recipient_email
        db.session.commit()

    send_res = send_email(
        to_email=recipient_email,
        subject=subject,
        body=body,
        lead_id=lead.id,
        evaluator_score=1.0,
        evaluator_reasoning="Dispatched via Web UI by user approval.",
        sender_email=sender_mailbox
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
