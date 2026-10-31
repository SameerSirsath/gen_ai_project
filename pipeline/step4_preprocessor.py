"""
step4_preprocessor.py — Data Cleaning & Preprocessing Module.

Steps:
  1. Deduplicate records
  2. Clean text (unicode, whitespace, boilerplate)
  3. Filter short / low-quality records
  4. Route to the best chunking strategy per source type
  5. Extract structured fields (company info, topics, entities)
  6. AI-powered summarisation using OpenAI / Gemini (optional)
  7. Return cleaned DataFrame + chunks ready for embedding
"""

import re
import hashlib
import os
from datetime import datetime

import pandas as pd

import nltk
try:
    nltk.data.find("tokenizers/punkt_tab")
except LookupError:
    nltk.download("punkt_tab", quiet=True)
try:
    nltk.data.find("tokenizers/punkt")
except LookupError:
    nltk.download("punkt", quiet=True)

from .config import MIN_TEXT_LENGTH, OUTPUT_DIR, OPENAI_API_KEY, GOOGLE_API_KEY
from .chunking import chunk_record   # ← smart chunking router


# ─────────────────────────────────────────────────────────────────
# Step 4.1: Text Cleaning
# ─────────────────────────────────────────────────────────────────

_BOILERPLATE = [
    r"cookie policy", r"privacy policy", r"terms of service", r"all rights reserved",
    r"subscribe to our newsletter", r"follow us on", r"copyright \d{4}",
    r"javascript is disabled", r"please enable javascript", r"404 not found",
    r"access denied", r"403 forbidden",
]
_BOILERPLATE_RE = re.compile("|".join(_BOILERPLATE), re.IGNORECASE)


def clean_text(text: str) -> str:
    """Full text cleaning pipeline."""
    if not text:
        return ""
    # Fix encoding artifacts — preserve non-ASCII (accents, etc.)
    text = text.encode("utf-8", "ignore").decode("utf-8")
    # Remove URLs
    text = re.sub(r"https?://\S+", "[URL]", text)
    # Remove emails
    text = re.sub(r"\S+@\S+\.\S+", "[EMAIL]", text)
    # Remove phone numbers
    text = re.sub(r"[\+\(]?[0-9][0-9\-\(\)\s]{8,}[0-9]", "[PHONE]", text)
    # Collapse repeated punctuation
    text = re.sub(r"[.!?]{3,}", "...", text)
    # Strip boilerplate lines
    lines = [ln for ln in text.splitlines() if ln.strip() and not _BOILERPLATE_RE.search(ln)]
    text = "\n".join(lines)
    # Collapse whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


# ─────────────────────────────────────────────────────────────────
# Step 4.2: Deduplication
# ─────────────────────────────────────────────────────────────────

def deduplicate(records: list[dict]) -> list[dict]:
    """Remove duplicate records by URL and text fingerprint."""
    seen_urls, seen_hashes, unique = set(), set(), []
    for record in records:
        url = record.get("url", "")
        text_hash = hashlib.md5(record.get("text", "")[:500].encode()).hexdigest()
        if url and url in seen_urls:
            continue
        if text_hash in seen_hashes:
            continue
        seen_urls.add(url)
        seen_hashes.add(text_hash)
        unique.append(record)
    removed = len(records) - len(unique)
    print(f"    [DEDUP] Removed {removed} duplicates → {len(unique)} unique records")
    return unique


# ─────────────────────────────────────────────────────────────────
# Step 4.3: Quality Filter
# ─────────────────────────────────────────────────────────────────

def filter_records(records: list[dict]) -> list[dict]:
    """Keep only records with meaningful text."""
    good = [r for r in records if len(r.get("text", "")) >= MIN_TEXT_LENGTH]
    print(f"    [FILTER] Kept {len(good)}/{len(records)} records (min {MIN_TEXT_LENGTH} chars)")
    return good


# ─────────────────────────────────────────────────────────────────
# Step 4.4: Topic Detection
# ─────────────────────────────────────────────────────────────────

_TOPIC_KEYWORDS = {
    "products_services": r"\b(product|service|solution|platform|software|hardware|offer)\b",
    "financials":        r"\b(revenue|profit|loss|earnings|EBITDA|funding|valuation|IPO|ARR|MRR)\b",
    "leadership":        r"\b(CEO|CTO|CFO|COO|founder|president|director|executive|board)\b",
    "hiring":            r"\b(hiring|recruit|job opening|career|vacancy|join our team)\b",
    "partnership":       r"\b(partner|collaboration|alliance|joint venture|MOU|agreement)\b",
    "news_events":       r"\b(launch|announce|release|event|webinar|conference|award)\b",
    "technology":        r"\b(AI|machine learning|automation|cloud|blockchain|API|data|analytics)\b",
    "market_expansion":  r"\b(expand|growth|market|international|global|new region|enter)\b",
    "customer_success":  r"\b(customer|client|case study|testimonial|success story|ROI)\b",
    "culture_values":    r"\b(culture|values|diversity|inclusion|sustainability|ESG|mission)\b",
}


def detect_topics(text: str) -> list[str]:
    return [t for t, p in _TOPIC_KEYWORDS.items() if re.search(p, text, re.IGNORECASE)]


# ─────────────────────────────────────────────────────────────────
# Step 4.5: Structured Company Info Extraction
# ─────────────────────────────────────────────────────────────────

def extract_company_info(text: str, company_name: str) -> dict:
    info = {}
    money = re.findall(
        r"\$[\d,]+(?:\.\d+)?\s*(?:million|billion|M|B|K)?|\b\d+(?:\.\d+)?\s*(?:million|billion)\s*(?:dollars|USD)?",
        text, re.IGNORECASE
    )
    if money:
        info["financial_figures"] = money[:5]

    year = re.search(r"(?:founded|established|incorporated)\s+(?:in\s+)?(\d{4})", text, re.IGNORECASE)
    if year:
        info["founded_year"] = year.group(1)

    emp = re.search(r"(\d[\d,]+)\s+(?:employees|staff|people|team members)", text, re.IGNORECASE)
    if emp:
        info["employee_count"] = emp.group(1)

    hq = re.search(r"headquartered?\s+(?:in\s+)?([A-Z][a-z]+(?:,\s*[A-Z][a-z]+)?)", text)
    if hq:
        info["headquarters"] = hq.group(1)

    ceo = re.search(r"(?:CEO|Chief Executive Officer)[,\s]+([A-Z][a-z]+ [A-Z][a-z]+)", text)
    if ceo:
        info["ceo"] = ceo.group(1)

    return info


# ─────────────────────────────────────────────────────────────────
# Step 4.6: AI Summarisation
# ─────────────────────────────────────────────────────────────────

def ai_summarize(text: str, company_name: str) -> str:
    if not text.strip():
        return ""

    prompt = f"""You are a B2B sales intelligence analyst.
Analyse the following information about "{company_name}" and extract:
1. Company Overview (2-3 sentences)
2. Core Products / Services
3. Target Market / Customers
4. Recent News or Initiatives
5. Pain Points or Challenges
6. Sales Opportunity Signals

Text:
{text[:4000]}

Respond in clean bullet points under each heading."""

    if OPENAI_API_KEY:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=OPENAI_API_KEY)
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=800,
                temperature=0.3,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            print(f"    [WARN] OpenAI: {e}")

    if GOOGLE_API_KEY:
        try:
            import google.generativeai as genai
            genai.configure(api_key=GOOGLE_API_KEY)
            model = genai.GenerativeModel("gemini-2.5-flash")
            return model.generate_content(prompt).text.strip()
        except Exception as e:
            print(f"    [WARN] Gemini: {e}")

    return ""


# ─────────────────────────────────────────────────────────────────
# Step 4.7: Full Preprocessing Pipeline
# ─────────────────────────────────────────────────────────────────

def preprocess(all_records: list[dict], company_name: str) -> dict:
    """
    Master preprocessing function.

    Uses the new smart chunking router — each record is routed to the
    best chunking strategy based on its source type, with page-aware
    chunking for PDF records that carry per-page OCR data.

    Returns:
        {
          "records":      list of enriched chunk dicts (ready for embedding),
          "dataframe":    pandas DataFrame of all chunks,
          "summary":      AI-generated summary (if API key set),
          "company_info": extracted structured fields,
        }
    """
    print(f"\n{'='*60}")
    print(f"[PREPROCESS] Starting for: {company_name}")
    print(f"{'='*60}")
    print(f"  Input records: {len(all_records)}")

    # 4.1–4.2 Dedup + clean
    records = deduplicate(all_records)
    for r in records:
        r["text"] = clean_text(r.get("text", ""))

    # 4.3 Filter
    records = filter_records(records)

    # 4.4–4.5 Chunk + enrich
    all_chunks: list[dict] = []
    company_info_combined = {}
    strategy_counts: dict[str, int] = {}

    for record in records:
        # Detect topics on full record text
        topics = detect_topics(record["text"])
        info   = extract_company_info(record["text"], company_name)
        company_info_combined.update({k: v for k, v in info.items() if k not in company_info_combined})

        # Route to correct chunking strategy
        # For PDF records, pass per-page data for page_aware chunking
        pages = record.get("pages")  # list[PageResult] or None
        chunks = chunk_record(record, strategy="auto", pages=pages)

        # Enrich each chunk
        for chunk in chunks:
            chunk["topics"]       = topics
            chunk["processed_at"] = datetime.now().isoformat()
            all_chunks.append(chunk)

        # Track strategy usage
        for chunk in chunks:
            s = chunk.get("strategy", "unknown")
            strategy_counts[s] = strategy_counts.get(s, 0) + 1

    # Report strategy usage
    print(f"\n    [CHUNK] {len(all_chunks)} chunks from {len(records)} records")
    print(f"    [CHUNK] Strategy breakdown:")
    for strat, count in sorted(strategy_counts.items(), key=lambda x: -x[1]):
        print(f"              {strat:30s} {count} chunks")

    # 4.6 AI Summary
    combined_text = "\n\n".join([c["text"] for c in all_chunks[:20]])
    print(f"\n[AI] Generating company intelligence summary…")
    ai_summary = ai_summarize(combined_text, company_name)
    if ai_summary:
        print("    ✓ AI summary generated")
    else:
        print("    [INFO] No AI summary (set OPENAI_API_KEY or GOOGLE_API_KEY)")

    df = pd.DataFrame(all_chunks)

    return {
        "records":      all_chunks,
        "dataframe":    df,
        "summary":      ai_summary,
        "company_info": company_info_combined,
    }
