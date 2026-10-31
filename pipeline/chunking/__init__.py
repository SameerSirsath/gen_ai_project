# pipeline/chunking/__init__.py
"""
Chunking Package
================
Five document chunking strategies with automatic source-based routing.

Strategies
----------
  fixed_token   — Split at N tokens with K overlap.
                  Best for: web pages, short articles, spreadsheet rows.

  sentence      — Group sentences until token budget is reached.
                  Best for: news articles, LinkedIn posts, blog content.

  semantic      — Embed sentences; split where cosine similarity drops.
                  Best for: long research docs, reports needing topical coherence.

  page_aware    — Respect PDF page boundaries; chunk within each page.
                  Best for: annual reports, whitepapers, multi-page PDFs.

  hierarchical  — Parse section headers → subsections → paragraphs.
                  Best for: structured documents with clear headings.

Auto-routing
------------
  Source type → strategy:
    local_pdf / pdf_download  → page_aware
    company_website           → sentence
    search_result             → fixed_token
    linkedin_*                → sentence
    spreadsheet               → fixed_token

Public API
----------
  from pipeline.chunking import chunk_record
  chunks = chunk_record(record, strategy="auto")   # → list of chunk dicts
"""

from .strategies import (
    chunk_fixed_token,
    chunk_sentence,
    chunk_semantic,
    chunk_page_aware,
    chunk_hierarchical,
    chunk_record,
    STRATEGY_ROUTER,
)

__all__ = [
    "chunk_fixed_token",
    "chunk_sentence",
    "chunk_semantic",
    "chunk_page_aware",
    "chunk_hierarchical",
    "chunk_record",
    "STRATEGY_ROUTER",
]
