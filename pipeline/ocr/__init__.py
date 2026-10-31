# pipeline/ocr/__init__.py
"""
OCR Package
===========
Three-layer PDF extraction system:

  Layer 1 — Digital text  (pdf_extractor.py)
             Fast; works on text-based PDFs.

  Layer 2 — Tesseract OCR  (ocr_engine.py)
             Used automatically when Layer 1 returns low-confidence text
             (scanned documents, image-only PDFs).

  Layer 3 — Table extraction  (table_extractor.py)
             Detects and converts tables to clean Markdown format.

Public API
----------
  from pipeline.ocr import extract_pdf
  pages = extract_pdf("report.pdf")   # → list of PageResult dicts
"""

from .pdf_extractor import extract_pdf, PageResult

__all__ = ["extract_pdf", "PageResult"]
