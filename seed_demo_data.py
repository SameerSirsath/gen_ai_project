"""
seed_demo_data.py — Seeds the ChromaDB with rich demo data from local files.
Run this to populate the explorer before running explore.py.
"""
import sys, os
sys.path.insert(0, r'f:\AI_Sales')
os.environ['PYTHONIOENCODING'] = 'utf-8'

from pipeline.ocr import extract_pdf
from pipeline.chunking import chunk_page_aware, chunk_fixed_token
from pipeline.step2_document_collector import read_local_spreadsheets
from pipeline.step4_preprocessor import detect_topics, clean_text
from pipeline.vector_store import VectorStore
from datetime import datetime

COMPANY  = "AI Sales Outreach"
PDF_PATH = r'f:\AI_Sales\AI-Powered Sales Outreach.pdf'
ROOT     = r'f:\AI_Sales'

print("=== Seeding ChromaDB with local file data ===")
print()

all_chunks = []

# ── PDF: page-aware chunking ──────────────────────────────────────
print("[1/2] Processing PDF with OCR pipeline...")
if os.path.exists(PDF_PATH):
    pages = extract_pdf(PDF_PATH)
    pdf_chunks = chunk_page_aware(pages)
    for c in pdf_chunks:
        text = clean_text(c["text"])
        if not text.strip():
            continue
        c["source"]       = "local_pdf"
        c["title"]        = "AI-Powered Sales Outreach.pdf"
        c["url"]          = PDF_PATH
        c["company"]      = COMPANY
        c["topics"]       = detect_topics(text)
        c["processed_at"] = datetime.now().isoformat()
        c["text"]         = text
        all_chunks.append(c)
    print(f"   PDF: {len(pages)} pages -> {len(pdf_chunks)} chunks")

# ── Excel: fixed_token chunking ───────────────────────────────────
print("[2/2] Processing Excel spreadsheet...")
spreadsheets = read_local_spreadsheets(ROOT, COMPANY)
for record in spreadsheets:
    text = clean_text(record.get("text",""))
    if not text.strip():
        continue
    chunks = chunk_fixed_token(text, chunk_size=200, overlap=40)
    for c in chunks:
        c["source"]       = "spreadsheet"
        c["title"]        = record.get("title","")
        c["url"]          = record.get("url","")
        c["company"]      = COMPANY
        c["topics"]       = detect_topics(c["text"])
        c["processed_at"] = datetime.now().isoformat()
    all_chunks.extend(chunks)
    print(f"   Excel: {record['title']} -> {len(chunks)} chunks")

print()
print(f"Total chunks to store: {len(all_chunks)}")

# ── Store in ChromaDB ─────────────────────────────────────────────
print()
vs = VectorStore(COMPANY)
vs.reset_collection()
stored = vs.upsert_chunks(all_chunks, show_progress=True)
print()
info = vs.info()
print("ChromaDB collection info:")
for k,v in info.items():
    print(f"  {k}: {v}")

print()
print("Done! Now run: python explore.py")
