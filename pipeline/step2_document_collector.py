"""
step2_document_collector.py — PDF & Document Ingestion Module.

Handles:
  • Local PDF files → three-layer OCR pipeline (per-page results)
  • PDF URLs found during web scraping → download + OCR
  • Excel / CSV files → structured text
"""

import os
import io
import time
import requests
import pandas as pd

from .config import OUTPUT_DIR, REQUEST_TIMEOUT, USER_AGENT, REQUEST_DELAY
from .ocr import extract_pdf   # ← three-layer OCR pipeline


# ─────────────────────────────────────────────────────────────────
# 1. Local PDF Files
# ─────────────────────────────────────────────────────────────────

def read_local_pdfs(folder_path: str, company_name: str) -> list[dict]:
    """
    Reads all .pdf files in folder_path using the full OCR pipeline.
    Returns one record per PDF (with per-page data attached).
    """
    pdf_files = [f for f in os.listdir(folder_path) if f.lower().endswith(".pdf")]
    print(f"\n[PDF] Reading {len(pdf_files)} local PDFs from: {folder_path}")
    results = []

    for filename in pdf_files:
        filepath = os.path.join(folder_path, filename)
        try:
            pages = extract_pdf(filepath, filename)

            if not pages:
                print(f"        ⚠  No text extracted from {filename}")
                continue

            # Combine all pages into a single text for the record body
            full_text = "\n\n".join(
                f"[Page {p['page_num']}]\n{p['text']}"
                for p in pages if p.get("text")
            )

            results.append({
                "source":       "local_pdf",
                "url":          filepath,
                "title":        filename,
                "text":         full_text[:10000],   # cap for storage
                "company":      company_name,
                # Store page-level data for page_aware chunking
                "pages":        pages,
                "total_pages":  len(pages),
                "ocr_pages":    sum(1 for p in pages if p.get("method") == "ocr"),
                "tables_found": sum(1 for p in pages if p.get("has_tables")),
            })
            print(f"    ✓ {filename} — {len(pages)} pages")

        except Exception as e:
            print(f"    [WARN] Failed to read {filename}: {e}")

    return results


# ─────────────────────────────────────────────────────────────────
# 2. Download PDFs from URLs
# ─────────────────────────────────────────────────────────────────

def download_pdfs_from_urls(pdf_url_records: list[dict], company_name: str, max_pdfs: int = 3, max_pages_per_pdf: int = 15) -> list[dict]:
    """
    Downloads PDFs found during web scraping and runs OCR pipeline.
    """
    pdf_candidates = pdf_url_records[:max_pdfs]
    print(f"\n[PDF] Downloading up to {len(pdf_candidates)} remote PDFs for: {company_name}")
    results = []
    headers = {"User-Agent": USER_AGENT}

    for record in pdf_candidates:
        url = record.get("url", "")
        if not url:
            continue
        try:
            filename = url.split("?")[0].split("/")[-1] or "document.pdf"
            print(f"    [FETCH] Downloading: {filename}")
            resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            pdf_bytes = resp.content

            pages = extract_pdf(pdf_bytes, filename=filename, max_pages=max_pages_per_pdf)
            if not pages:
                continue

            full_text = "\n\n".join(
                f"[Page {p['page_num']}]\n{p['text']}"
                for p in pages if p.get("text")
            )

            results.append({
                "source":       "pdf_download",
                "url":          url,
                "title":        record.get("title", filename),
                "text":         full_text[:10000],
                "company":      company_name,
                "pages":        pages,
                "total_pages":  len(pages),
                "ocr_pages":    sum(1 for p in pages if p.get("method") == "ocr"),
                "tables_found": sum(1 for p in pages if p.get("has_tables")),
            })
            print(f"    ✓ Processed: {filename} ({len(pages)} pages extracted)")
            time.sleep(REQUEST_DELAY)

        except Exception as e:
            print(f"    [WARN] Failed to download {url}: {e}")

    return results


# ─────────────────────────────────────────────────────────────────
# 3. Spreadsheets (Excel / CSV)
# ─────────────────────────────────────────────────────────────────

def read_local_spreadsheets(folder_path: str, company_name: str) -> list[dict]:
    """
    Reads .xlsx, .xls, .csv files and converts them to structured text.
    """
    extensions = (".xlsx", ".xls", ".csv")
    files = [f for f in os.listdir(folder_path) if f.lower().endswith(extensions)]
    print(f"\n[DOCS] Reading {len(files)} spreadsheets from: {folder_path}")
    results = []

    for filename in files:
        filepath = os.path.join(folder_path, filename)
        try:
            if filename.lower().endswith(".csv"):
                df = pd.read_csv(filepath)
            else:
                try:
                    df = pd.read_excel(filepath, engine="openpyxl")
                except ImportError:
                    df = pd.read_excel(filepath)

            text_lines = [
                f"File: {filename}",
                f"Columns: {', '.join(df.columns.tolist())}",
                f"Rows: {len(df)}",
                "",
                "--- Sample Data (first 20 rows) ---",
                df.head(20).to_string(index=False),
            ]
            text = "\n".join(text_lines)

            results.append({
                "source":    "spreadsheet",
                "url":       filepath,
                "title":     filename,
                "text":      text[:5000],
                "company":   company_name,
                "dataframe": df.to_dict(orient="records"),
            })
            print(f"    ✓ {filename} ({len(df)} rows × {len(df.columns)} cols)")

        except Exception as e:
            print(f"    [WARN] Failed to read {filename}: {e}")

    return results


# ─────────────────────────────────────────────────────────────────
# Main Entry Point
# ─────────────────────────────────────────────────────────────────

def collect_documents(
    company_name: str,
    folder_path: str,
    pdf_url_records: list[dict] | None = None,
) -> list[dict]:
    """
    Master function: collects all document data.

    Args:
        company_name:    Target company name
        folder_path:     Local folder to scan for PDFs / spreadsheets
        pdf_url_records: PDF URL records found by the web scraper (optional)

    Returns:
        List of raw document records (each with 'pages' key for PDFs)
    """
    results = []
    results += read_local_pdfs(folder_path, company_name)
    results += read_local_spreadsheets(folder_path, company_name)

    if pdf_url_records:
        results += download_pdfs_from_urls(pdf_url_records, company_name)

    print(f"\n[DOCS] Total document records: {len(results)}")
    return results
