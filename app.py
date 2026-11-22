"""
app.py — Flask Web Application for AI Sales Outreach Agent.
Renders interactive dashboard and exposes /api/generate endpoint.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from flask import Flask, render_template, request, jsonify

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.orchestrator import run_agent_pipeline

app = Flask(__name__)


@app.route("/", methods=["GET"])
def index():
    """Renders the main dashboard interface."""
    return render_template("index.html")


@app.route("/api/generate", methods=["POST"])
def generate():
    """
    Accepts JSON {prospect_name, context}, executes multi-agent pipeline,
    and returns generation + evaluation status.
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        prospect_name = data.get("prospect_name", "").strip()
        context = data.get("context", "").strip()

        if not prospect_name:
            return jsonify({
                "status": "ERROR",
                "error": "Prospect Name is required."
            }), 400

        if not context:
            return jsonify({
                "status": "ERROR",
                "error": "Prospect Context is required."
            }), 400

        result = run_agent_pipeline(prospect_name=prospect_name, context=context)

        draft = result.get("draft") or {}
        evaluation = result.get("evaluation") or {}
        is_grounded = bool(result.get("approved"))
        status = "PASSED" if is_grounded else "BLOCKED"

        response_payload = {
            "status": status,
            "is_grounded": is_grounded,
            "subject": draft.get("subject", ""),
            "body": draft.get("body", ""),
            "claims_used": draft.get("claims_used", []),
            "flagged_claims": evaluation.get("flagged_claims", []) or result.get("flagged_claims", []),
            "reasoning": evaluation.get("reasoning", "") or result.get("reasoning", ""),
            "signals": result.get("signals", {}),
        }
        return jsonify(response_payload), 200

    except Exception as e:
        return jsonify({
            "status": "ERROR",
            "error": f"Agent pipeline failed: {str(e)}"
        }), 500


@app.errorhandler(500)
def internal_server_error(error):
    """Fallback 500 internal server error handler."""
    return jsonify({
        "status": "ERROR",
        "error": "Internal server error occurred."
    }), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
