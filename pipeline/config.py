"""
config.py — Central configuration for the entire AI Sales pipeline.

API keys are loaded automatically from the .env file in the project root.
You can also override any value by setting it as an environment variable.
"""

import sys
import os
from pathlib import Path

# ── Ensure UTF-8 output on Windows console (prevents cp1252 charmap errors) ──
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── Auto-load .env from project root ──────────────────────────────
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(dotenv_path=_env_path, override=False)
    if _env_path.exists():
        print(f"[CONFIG] Loaded .env from: {_env_path}")
except ImportError:
    pass  # python-dotenv not installed — use OS environment variables only

_BASE = os.path.dirname(os.path.dirname(__file__))   # project root

# ═══════════════════════════════════════════════════════════════
# 1. API KEYS
#    Set as environment variables (recommended) or paste directly.
# ═══════════════════════════════════════════════════════════════
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY", "")
GOOGLE_API_KEY    = os.getenv("GOOGLE_API_KEY", "")
SERPAPI_KEY       = os.getenv("SERPAPI_KEY", "")
PROXYCURL_API_KEY = os.getenv("PROXYCURL_API_KEY", "")
LINKEDIN_EMAIL    = os.getenv("LINKEDIN_EMAIL", "")
LINKEDIN_PASSWORD = os.getenv("LINKEDIN_PASSWORD", "")

# ═══════════════════════════════════════════════════════════════
# 2. PATHS
# ═══════════════════════════════════════════════════════════════
OUTPUT_DIR   = os.path.join(_BASE, "output")
CHROMA_DIR   = os.path.join(_BASE, "chroma_db")   # local vector DB lives here

# ═══════════════════════════════════════════════════════════════
# 3. WEB SCRAPING
# ═══════════════════════════════════════════════════════════════
REQUEST_TIMEOUT    = 15
REQUEST_DELAY      = int(os.getenv("REQUEST_DELAY", 2))
MAX_PAGES_PER_SITE = 10
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
SEARCH_QUERIES = [
    "{company} company overview",
    "{company} products services",
    "{company} recent news",
    "{company} annual report filetype:pdf",
    "{company} LinkedIn company",
    "{company} press release",
    "{company} leadership team CEO",
    "{company} funding investment",
]

# ═══════════════════════════════════════════════════════════════
# 4. PDF / OCR SETTINGS
# ═══════════════════════════════════════════════════════════════
OCR_DPI                  = 300
OCR_LANGUAGE             = os.getenv("OCR_LANGUAGE", "eng")
OCR_CONFIDENCE_THRESHOLD = 60
OCR_EXTRACT_TABLES       = True
TESSERACT_CMD            = os.getenv("TESSERACT_CMD", "")

# ═══════════════════════════════════════════════════════════════
# 5. CHUNKING STRATEGY
# ═══════════════════════════════════════════════════════════════
CHUNK_SIZE_TOKENS    = int(os.getenv("CHUNK_SIZE_TOKENS", 400))
CHUNK_OVERLAP_TOKENS = int(os.getenv("CHUNK_OVERLAP_TOKENS", 80))
MIN_CHUNK_TOKENS     = 40
CHUNKING_STRATEGY    = os.getenv("CHUNKING_STRATEGY", "auto")

# ═══════════════════════════════════════════════════════════════
# 6. EMBEDDING MODEL
#
#   Priority: openai → google → sentence-transformers (local, free)
#   sentence-transformers runs 100% offline — no API key needed.
# ═══════════════════════════════════════════════════════════════
EMBEDDING_MODEL_OPENAI  = "text-embedding-3-small"   # 1536 dims
EMBEDDING_MODEL_GOOGLE  = os.getenv("EMBEDDING_MODEL_GOOGLE", "models/gemini-embedding-001")     # 3072 dims
EMBEDDING_MODEL_LOCAL   = "all-MiniLM-L6-v2"         # 384 dims, free & fast
EMBEDDING_BATCH_SIZE    = 32     # chunks to embed per API call

# ═══════════════════════════════════════════════════════════════
# 7. CHROMADB  (local vector database — persisted to disk)
#    One collection per company: "aisales_tesla", "aisales_microsoft", …
# ═══════════════════════════════════════════════════════════════
CHROMA_COLLECTION_PREFIX = "aisales"
CHROMA_TOP_K             = int(os.getenv("CHROMA_TOP_K", 5))

# ═══════════════════════════════════════════════════════════════
# 8. PREPROCESSING (shared)
# ═══════════════════════════════════════════════════════════════
MIN_TEXT_LENGTH = 50      # discard raw records shorter than this (chars)
MAX_TEXT_LENGTH = 5000    # char cap per chunk if tokenizer unavailable
