"""
app.py — Main Entry Point for AI Sales Outreach Web Application.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Ensure root directory is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

load_dotenv()

from app import create_app

app = create_app()
app.config["ENCRYPTION_KEY"] = os.getenv("ENCRYPTION_KEY")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
