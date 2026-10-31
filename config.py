"""
config.py — Central configuration for AI Sales Outreach Pipeline.

Powered by pydantic-settings BaseSettings.
Supports dynamic switching across vector stores, LLMs, and embedding backends
via environment variables or .env file.
"""

from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path
from typing import Literal, Optional
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

# ── Ensure UTF-8 output on Windows console ────────────────────────
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

_PROJECT_ROOT = Path(__file__).resolve().parent


class Settings(BaseSettings):
    """
    Application settings with environment variable overrides.
    """
    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # ═══════════════════════════════════════════════════════════════
    # 1. CORE BACKEND SELECTION
    # ═══════════════════════════════════════════════════════════════
    VECTOR_BACKEND: Literal["chroma", "pinecone"] = "chroma"
    LLM_BACKEND: Literal["gemini", "openai", "groq", "onnx"] = "gemini"
    EMBEDDING_BACKEND: Literal["gemini", "openai", "local"] = "gemini"
    EMBEDDING_DIM: int = 3072

    # ═══════════════════════════════════════════════════════════════
    # 2. VECTOR STORE CONFIGURATION (Pinecone & Chroma HNSW)
    # ═══════════════════════════════════════════════════════════════
    PINECONE_API_KEY: Optional[str] = None
    PINECONE_INDEX_NAME: str = "ai-sales"
    PINECONE_ENV: Optional[str] = None
    PINECONE_CLOUD: str = "aws"
    PINECONE_REGION: str = "us-east-1"

    # Chroma HNSW Parameters (explicitly exposed, non-silent defaults)
    CHROMA_HNSW_M: int = 32
    CHROMA_HNSW_CONSTRUCTION_EF: int = 200
    CHROMA_HNSW_SEARCH_EF: int = 100
    CHROMA_DIR: str = str(_PROJECT_ROOT / "chroma_db")
    CHROMA_COLLECTION_PREFIX: str = "aisales"
    CHROMA_TOP_K: int = 5

    # ═══════════════════════════════════════════════════════════════
    # 3. LLM & EMBEDDING CONFIGURATION
    # ═══════════════════════════════════════════════════════════════
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: str = "llama-3.1-70b-versatile"

    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    EMBEDDING_MODEL_OPENAI: str = "text-embedding-3-small"

    GOOGLE_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-1.5-flash"
    EMBEDDING_MODEL_GOOGLE: str = "models/gemini-embedding-001"

    EMBEDDING_MODEL_LOCAL: str = "all-MiniLM-L6-v2"
    EMBEDDING_BATCH_SIZE: int = 32

    # ═══════════════════════════════════════════════════════════════
    # 4. AGENT & EVALUATION THRESHOLDS
    # ═══════════════════════════════════════════════════════════════
    RECENCY_HALF_LIFE_DAYS: int = 90
    EVALUATOR_GROUNDING_THRESHOLD: float = 0.90
    DIFFERENTIATION_SIM_THRESHOLD: float = 0.85

    # ═══════════════════════════════════════════════════════════════
    # 5. PIPELINE & SCRAPING SETTINGS
    # ═══════════════════════════════════════════════════════════════
    OUTPUT_DIR: str = str(_PROJECT_ROOT / "output")
    SERPAPI_KEY: Optional[str] = None
    PROXYCURL_API_KEY: Optional[str] = None
    LINKEDIN_EMAIL: Optional[str] = None
    LINKEDIN_PASSWORD: Optional[str] = None

    REQUEST_TIMEOUT: int = 15
    REQUEST_DELAY: int = 2
    MAX_PAGES_PER_SITE: int = 10
    USER_AGENT: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    SEARCH_QUERIES: list[str] = [
        "{company} company overview",
        "{company} products services",
        "{company} recent news",
        "{company} annual report filetype:pdf",
        "{company} LinkedIn company",
        "{company} press release",
        "{company} leadership team CEO",
        "{company} funding investment",
    ]

    OCR_DPI: int = 300
    OCR_LANGUAGE: str = "eng"
    OCR_CONFIDENCE_THRESHOLD: int = 60
    OCR_EXTRACT_TABLES: bool = True
    TESSERACT_CMD: Optional[str] = None

    CHUNK_SIZE_TOKENS: int = 400
    CHUNK_OVERLAP_TOKENS: int = 80
    MIN_CHUNK_TOKENS: int = 40
    CHUNKING_STRATEGY: str = "auto"
    MIN_TEXT_LENGTH: int = 50
    MAX_TEXT_LENGTH: int = 5000

    @model_validator(mode="after")
    def validate_backend_credentials(self) -> Settings:
        """
        Validate backend selection against available credentials.
        Raises descriptive ValueError at startup if a chosen backend's key is missing.
        Gracefully resolves free-tier local defaults when running with no cloud keys.
        """
        # 1. Vector backend validation
        if self.VECTOR_BACKEND == "pinecone":
            if not self.PINECONE_API_KEY:
                raise ValueError(
                    "[CONFIG ERROR] VECTOR_BACKEND is set to 'pinecone', but PINECONE_API_KEY is missing. "
                    "Set PINECONE_API_KEY in your environment or switch to VECTOR_BACKEND=chroma."
                )

        # 2. LLM backend validation
        if self.LLM_BACKEND == "groq":
            if not self.GROQ_API_KEY:
                raise ValueError(
                    "[CONFIG ERROR] LLM_BACKEND is set to 'groq', but GROQ_API_KEY is missing. "
                    "Set GROQ_API_KEY in your environment or switch to LLM_BACKEND=gemini/onnx."
                )
        elif self.LLM_BACKEND == "openai":
            if not self.OPENAI_API_KEY:
                raise ValueError(
                    "[CONFIG ERROR] LLM_BACKEND is set to 'openai', but OPENAI_API_KEY is missing. "
                    "Set OPENAI_API_KEY in your environment or switch to LLM_BACKEND=gemini/onnx."
                )
        elif self.LLM_BACKEND == "gemini":
            gemini_key = self.GEMINI_API_KEY or self.GOOGLE_API_KEY
            if not gemini_key:
                if os.getenv("LLM_BACKEND") == "gemini":
                    raise ValueError(
                        "[CONFIG ERROR] LLM_BACKEND is set to 'gemini', but GOOGLE_API_KEY / GEMINI_API_KEY is missing. "
                        "Set GOOGLE_API_KEY in your environment or switch to LLM_BACKEND=onnx."
                    )
                # If gemini is only default and no keys exist, fallback to onnx
                object.__setattr__(self, "LLM_BACKEND", "onnx")

        # 3. Embedding backend validation
        if self.EMBEDDING_BACKEND == "openai":
            if not self.OPENAI_API_KEY:
                raise ValueError(
                    "[CONFIG ERROR] EMBEDDING_BACKEND is set to 'openai', but OPENAI_API_KEY is missing. "
                    "Set OPENAI_API_KEY in your environment or switch to EMBEDDING_BACKEND=gemini/local."
                )
        elif self.EMBEDDING_BACKEND == "gemini":
            gemini_key = self.GEMINI_API_KEY or self.GOOGLE_API_KEY
            if not gemini_key:
                if os.getenv("EMBEDDING_BACKEND") == "gemini":
                    raise ValueError(
                        "[CONFIG ERROR] EMBEDDING_BACKEND is set to 'gemini', but GOOGLE_API_KEY / GEMINI_API_KEY is missing. "
                        "Set GOOGLE_API_KEY in your environment or switch to EMBEDDING_BACKEND=local."
                    )
                # Fallback to local offline embedding
                object.__setattr__(self, "EMBEDDING_BACKEND", "local")
                object.__setattr__(self, "EMBEDDING_DIM", 384)

        return self

    def resolved_summary(self) -> str:
        """Format string of resolved configuration for pipeline startup banner."""
        return (
            f"[config] vector={self.VECTOR_BACKEND} "
            f"llm={self.LLM_BACKEND} "
            f"embedding={self.EMBEDDING_BACKEND} "
            f"dim={self.EMBEDDING_DIM}"
        )


# Singleton settings instance
settings = Settings()

# Module-level exports for backwards compatibility
OUTPUT_DIR = settings.OUTPUT_DIR
CHROMA_DIR = settings.CHROMA_DIR
VECTOR_BACKEND = settings.VECTOR_BACKEND
LLM_BACKEND = settings.LLM_BACKEND
EMBEDDING_BACKEND = settings.EMBEDDING_BACKEND
EMBEDDING_DIM = settings.EMBEDDING_DIM
OPENAI_API_KEY = settings.OPENAI_API_KEY or ""
GOOGLE_API_KEY = settings.GOOGLE_API_KEY or settings.GEMINI_API_KEY or ""
SERPAPI_KEY = settings.SERPAPI_KEY or ""
PROXYCURL_API_KEY = settings.PROXYCURL_API_KEY or ""
LINKEDIN_EMAIL = settings.LINKEDIN_EMAIL or ""
LINKEDIN_PASSWORD = settings.LINKEDIN_PASSWORD or ""
CHROMA_COLLECTION_PREFIX = settings.CHROMA_COLLECTION_PREFIX
CHROMA_TOP_K = settings.CHROMA_TOP_K
REQUEST_TIMEOUT = settings.REQUEST_TIMEOUT
REQUEST_DELAY = settings.REQUEST_DELAY
MAX_PAGES_PER_SITE = settings.MAX_PAGES_PER_SITE
USER_AGENT = settings.USER_AGENT
SEARCH_QUERIES = settings.SEARCH_QUERIES
OCR_DPI = settings.OCR_DPI
OCR_LANGUAGE = settings.OCR_LANGUAGE
OCR_CONFIDENCE_THRESHOLD = settings.OCR_CONFIDENCE_THRESHOLD
OCR_EXTRACT_TABLES = settings.OCR_EXTRACT_TABLES
TESSERACT_CMD = settings.TESSERACT_CMD or ""
CHUNK_SIZE_TOKENS = settings.CHUNK_SIZE_TOKENS
CHUNK_OVERLAP_TOKENS = settings.CHUNK_OVERLAP_TOKENS
MIN_CHUNK_TOKENS = settings.MIN_CHUNK_TOKENS
CHUNKING_STRATEGY = settings.CHUNKING_STRATEGY
EMBEDDING_MODEL_OPENAI = settings.EMBEDDING_MODEL_OPENAI
EMBEDDING_MODEL_GOOGLE = settings.EMBEDDING_MODEL_GOOGLE
EMBEDDING_MODEL_LOCAL = settings.EMBEDDING_MODEL_LOCAL
EMBEDDING_BATCH_SIZE = settings.EMBEDDING_BATCH_SIZE
MIN_TEXT_LENGTH = settings.MIN_TEXT_LENGTH
MAX_TEXT_LENGTH = settings.MAX_TEXT_LENGTH
RECENCY_HALF_LIFE_DAYS = settings.RECENCY_HALF_LIFE_DAYS
EVALUATOR_GROUNDING_THRESHOLD = settings.EVALUATOR_GROUNDING_THRESHOLD
DIFFERENTIATION_SIM_THRESHOLD = settings.DIFFERENTIATION_SIM_THRESHOLD
