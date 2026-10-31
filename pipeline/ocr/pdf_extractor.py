"""
pdf_extractor.py — Layer 1 & Orchestrator of the three-layer OCR pipeline.

Flow for each page:
  1. Try digital text extraction (pdfplumber / pypdf)
  2. Score confidence: word count, character quality, whitespace ratio
  3. If confidence < threshold → hand off to ocr_engine.py (Tesseract)
  4. If tables detected        → hand off to table_extractor.py
  5. Return a PageResult for every page

Usage:
    from pipeline.ocr import extract_pdf
    pages = extract_pdf("report.pdf")
    for p in pages:
        print(p["page_num"], p["text"][:200], p["method"])
"""

import io
import os
import re
from dataclasses import dataclass, field, asdict
from typing import Optional

from ..config import OCR_CONFIDENCE_THRESHOLD, OCR_EXTRACT_TABLES


# ─────────────────────────────────────────────────────────────────
# PageResult — one record per PDF page
# ─────────────────────────────────────────────────────────────────

@dataclass
class PageResult:
    """Structured result for one PDF page."""
    page_num:       int
    text:           str
    tables:         list        = field(default_factory=list)   # list of markdown table strings
    method:         str         = "digital"   # "digital" | "ocr" | "empty"
    confidence:     float       = 100.0       # 0-100 text quality score
    has_tables:     bool        = False
    word_count:     int         = 0
    char_count:     int         = 0
    error:          Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


# ─────────────────────────────────────────────────────────────────
# Confidence Scoring
# ─────────────────────────────────────────────────────────────────

def _score_text(text: str) -> float:
    """
    Score text quality 0-100.
    High score = clean digital text.
    Low score  = likely scanned / garbled → trigger OCR.
    """
    if not text or len(text.strip()) < 10:
        return 0.0

    words = text.split()
    total_chars = len(text)
    if total_chars == 0:
        return 0.0

    # Penalize: high ratio of non-printable / special characters
    clean_chars = sum(1 for c in text if c.isalnum() or c in " .,;:!?-\n'\"()")
    char_quality = (clean_chars / total_chars) * 100

    # Penalize: very short words on average (OCR artefacts)
    avg_word_len = sum(len(w) for w in words) / max(len(words), 1)
    length_score = min(avg_word_len / 4.0 * 100, 100)

    # Penalize: excessive whitespace (extraction failure)
    whitespace_ratio = text.count(" ") / max(total_chars, 1)
    ws_penalty = max(0, (1 - whitespace_ratio * 4)) * 100

    score = (char_quality * 0.5) + (length_score * 0.3) + (ws_penalty * 0.2)
    return round(min(max(score, 0), 100), 1)


# ─────────────────────────────────────────────────────────────────
# Layer 1: Digital Text Extraction (pdfplumber)
# ─────────────────────────────────────────────────────────────────

def _extract_with_pdfplumber(pdf_bytes: bytes) -> list[dict]:
    """
    Extract per-page text + detect tables using pdfplumber.
    Returns list of {page_num, raw_text, raw_tables} dicts.
    """
    try:
        import pdfplumber
    except ImportError:
        return []

    pages_data = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for i, page in enumerate(pdf.pages):
            raw_text = page.extract_text() or ""
            raw_tables = []

            if OCR_EXTRACT_TABLES:
                try:
                    tables = page.extract_tables()
                    for table in (tables or []):
                        if table:
                            raw_tables.append(table)
                except Exception:
                    pass

            pages_data.append({
                "page_num": i + 1,
                "raw_text": raw_text,
                "raw_tables": raw_tables,
            })
    return pages_data


def _extract_with_pypdf(pdf_bytes: bytes) -> list[dict]:
    """Fallback: extract page text with pypdf (no table support)."""
    try:
        from pypdf import PdfReader
    except ImportError:
        try:
            import PyPDF2 as pypdf_fallback
            PdfReader = pypdf_fallback.PdfReader
        except ImportError:
            return []

    pages_data = []
    reader = PdfReader(io.BytesIO(pdf_bytes))
    for i, page in enumerate(reader.pages):
        pages_data.append({
            "page_num": i + 1,
            "raw_text": page.extract_text() or "",
            "raw_tables": [],
        })
    return pages_data


# ─────────────────────────────────────────────────────────────────
# Table → Markdown Formatter
# ─────────────────────────────────────────────────────────────────

def _table_to_markdown(raw_table: list[list]) -> str:
    """Convert a pdfplumber raw table to a clean Markdown table string."""
    if not raw_table:
        return ""

    from .table_extractor import raw_table_to_markdown
    return raw_table_to_markdown(raw_table)


# ─────────────────────────────────────────────────────────────────
# Main Orchestrator
# ─────────────────────────────────────────────────────────────────

def extract_pdf(source: str | bytes, filename: str = "", max_pages: Optional[int] = None) -> list[dict]:
    """
    Full three-layer PDF extraction pipeline.

    Args:
        source:    File path (str) or raw PDF bytes.
        filename:  Optional display name (used in logs).
        max_pages: Optional cap on pages to extract (useful for large SEC reports).

    Returns:
        List of PageResult.to_dict() — one dict per page.
        Each dict contains: page_num, text, tables, method,
                            confidence, has_tables, word_count, char_count
    """
    # Load bytes
    if isinstance(source, (str, os.PathLike)):
        filename = filename or os.path.basename(source)
        with open(source, "rb") as f:
            pdf_bytes = f.read()
    else:
        pdf_bytes = source

    print(f"    [OCR] Processing: {filename or 'PDF'}")

    # --- Layer 1: Digital extraction ---
    pages_data = _extract_with_pdfplumber(pdf_bytes)
    if not pages_data:
        pages_data = _extract_with_pypdf(pdf_bytes)

    if not pages_data:
        print("        [WARN] No PDF reader available. Install: pip install pdfplumber")
        return []

    if max_pages and len(pages_data) > max_pages:
        pages_data = pages_data[:max_pages]
        print(f"        [INFO] Limiting extraction to first {max_pages} pages")

    total_pages = len(pages_data)
    results = []
    ocr_pages = 0

    for page_data in pages_data:
        pnum      = page_data["page_num"]
        raw_text  = page_data["raw_text"]
        raw_tables = page_data.get("raw_tables", [])

        # Score digital extraction quality
        confidence = _score_text(raw_text)
        method = "digital"
        final_text = raw_text

        # --- Layer 2: OCR fallback for low-confidence pages ---
        if confidence < OCR_CONFIDENCE_THRESHOLD:
            try:
                from .ocr_engine import ocr_page
                ocr_text = ocr_page(pdf_bytes, page_number=pnum)
                if ocr_text and len(ocr_text) > len(raw_text):
                    final_text = ocr_text
                    confidence = _score_text(ocr_text)
                    method = "ocr"
                    ocr_pages += 1
            except Exception as e:
                pass  # graceful: keep digital text even if OCR fails

        # --- Layer 3: Format extracted tables as Markdown ---
        md_tables = []
        for raw_table in raw_tables:
            md = _table_to_markdown(raw_table)
            if md:
                md_tables.append(md)

        # Append table markdown after page text
        combined_text = final_text.strip()
        if md_tables:
            combined_text += "\n\n" + "\n\n".join(md_tables)

        result = PageResult(
            page_num    = pnum,
            text        = combined_text.strip(),
            tables      = md_tables,
            method      = method,
            confidence  = confidence,
            has_tables  = bool(md_tables),
            word_count  = len(combined_text.split()),
            char_count  = len(combined_text),
        )
        results.append(result.to_dict())

    # Summary
    text_pages = total_pages - ocr_pages
    tables_with = sum(1 for r in results if r['has_tables'])
    print(f"        [OK] {total_pages} pages | {text_pages} digital | {ocr_pages} OCR | {tables_with} with tables")

    return results
