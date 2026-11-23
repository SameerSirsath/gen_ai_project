"""
tests/test_frontend_render.py — Verify all frontend pages and Jinja2 templates render cleanly.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv()

from app import create_app
from app.models.db import db, Lead, LeadContext, CompanyProfile, User, ApiKey


def test_render_all_pages():
    app = create_app()
    client = app.test_client()

    pages = [
        ("/", 200, "Scale Your Sales with"),
        ("/login", 200, "Sign in to your AI Sales SDR Dashboard"),
        ("/register", 200, "Get Started Free"),
        ("/dashboard", 200, "Outreach Intelligence Dashboard"),
        ("/profile", 200, "Company Profile & Knowledge Base"),
        ("/api-keys", 200, "LLM API Keys & Multi-Key Routing"),
        ("/leads", 200, "Prospects & Leads Pipeline"),
    ]

    print("=== Testing Frontend Page Routes ===")
    for route, expected_status, text_snippet in pages:
        res = client.get(route)
        print(f"Testing route {route} -> Status: {res.status_code}")
        assert res.status_code == expected_status, f"Route {route} returned {res.status_code}, expected {expected_status}"
        assert text_snippet in res.get_data(as_text=True), f"Snippet '{text_snippet}' not found in {route}"

    # Test Lead Workspace with existing or newly created lead
    with app.app_context():
        lead = Lead.query.first()
        if not lead:
            lead = Lead(company_name="Test Enterprise Inc", contact_name="Alice Smith", email="alice@test.com")
            db.session.add(lead)
            db.session.commit()
        lead_id = lead.id

    res_ws = client.get(f"/leads/{lead_id}")
    print(f"Testing route /leads/{lead_id} -> Status: {res_ws.status_code}")
    assert res_ws.status_code == 200
    assert "Lead Context & NLP Analysis" in res_ws.get_data(as_text=True)

    # Test Auth Login POST
    res_login = client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=True)
    print(f"Testing POST /login -> Status: {res_login.status_code}")
    assert res_login.status_code == 200
    assert "Outreach Intelligence Dashboard" in res_login.get_data(as_text=True)

    print("\n=======================================================")
    print("ALL FRONTEND PAGES & ROUTES RENDERED CLEANLY (200 OK)!")
    print("=======================================================")


if __name__ == "__main__":
    test_render_all_pages()
