"""
run_pipeline.py — Main Pipeline Orchestrator

Usage examples:
  python run_pipeline.py
  python run_pipeline.py --company "Tesla"
  python run_pipeline.py --company "Microsoft" --url "https://microsoft.com"
  python run_pipeline.py --company "OpenAI" --skip-web --skip-linkedin
  python run_pipeline.py --company "Tesla" --query "What is their revenue?"
  python run_pipeline.py --company "Tesla" --skip-web --skip-linkedin --skip-docs

Pipeline Steps:
  1 → Web scraping     (company website + search + news)
  2 → Document ingest  (local PDFs + Excel + downloaded PDFs via OCR)
  3 → LinkedIn posts   (public page + search snippets)
  4 → Preprocessing    (clean, deduplicate, smart chunk by source type)
  5 → Save outputs     (JSON, CSV, Excel, Markdown report)
  6 → Embed + store    (ChromaDB local vector database)
"""

import os
import sys
import argparse
import time

# ── Ensure UTF-8 console output on Windows ────────────────────────
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

sys.path.insert(0, os.path.dirname(__file__))

from pipeline.step1_web_scraper        import collect_web_data
from pipeline.step2_document_collector import collect_documents
from pipeline.step3_linkedin_posts     import collect_linkedin_data
from pipeline.step4_preprocessor      import preprocess
from pipeline.step5_storage           import save_all
from pipeline.vector_store            import VectorStore
from pipeline.config                  import OUTPUT_DIR


BANNER = """
╔══════════════════════════════════════════════════════════════╗
║      🚀  AI Sales Intelligence — Data Pipeline v2.0          ║
║         Web · PDFs · LinkedIn · OCR · ChromaDB               ║
╚══════════════════════════════════════════════════════════════╝"""


def _print_step(n: int, title: str):
    print(f"\n{'─'*62}")
    print(f"  STEP {n}: {title}")
    print(f"{'─'*62}")


# ─────────────────────────────────────────────────────────────────
# Pipeline Orchestrator
# ─────────────────────────────────────────────────────────────────

def run_pipeline(
    company_name:          str,
    company_url:           str  = "",
    docs_folder:           str  = "",
    skip_web:              bool = False,
    skip_docs:             bool = False,
    skip_linkedin:         bool = False,
    skip_vector_store:     bool = False,
    proxycurl_api_key:     str  = "",
    company_linkedin_url:  str  = "",
    query:                 str  = "",
):
    print(BANNER)
    print(f"\n  🎯 Target Company  : {company_name}")
    print(f"  🌐 Company URL     : {company_url or '(auto-detect)'}")
    print(f"  📁 Docs Folder     : {docs_folder or os.getcwd()}")
    print(f"  📦 Vector DB       : ./chroma_db/ (ChromaDB local)")
    print()

    if not docs_folder:
        docs_folder = os.path.dirname(os.path.abspath(__file__))

    t0 = time.time()
    all_raw = []

    # ── Step 1: Web ───────────────────────────────────────────────
    if not skip_web:
        _print_step(1, "Web Scraping — Website · Search Results · News")
        web_records = collect_web_data(company_name, company_url)
        all_raw.extend(web_records)
    else:
        _print_step(1, "Web Scraping [SKIPPED]")
        web_records = []

    # ── Step 2: Documents ─────────────────────────────────────────
    if not skip_docs:
        _print_step(2, "Document Ingestion — PDFs (OCR) · Excel · CSV")
        pdf_links = [r for r in web_records if r.get("source") == "search_pdf_link"]
        doc_records = collect_documents(
            company_name    = company_name,
            folder_path     = docs_folder,
            pdf_url_records = pdf_links,
        )
        all_raw.extend(doc_records)
    else:
        _print_step(2, "Document Ingestion [SKIPPED]")

    # ── Step 3: LinkedIn ──────────────────────────────────────────
    if not skip_linkedin:
        _print_step(3, "LinkedIn — Posts · Company Intelligence")
        li_records = collect_linkedin_data(
            company_name          = company_name,
            proxycurl_api_key     = proxycurl_api_key,
            company_linkedin_url  = company_linkedin_url,
        )
        all_raw.extend(li_records)
    else:
        _print_step(3, "LinkedIn Collection [SKIPPED]")

    # ── Step 4: Preprocess ────────────────────────────────────────
    _print_step(4, "Preprocessing — Clean · Deduplicate · Smart Chunk · AI Summary")
    preprocessed = preprocess(all_raw, company_name)

    # ── Step 5: Save Files ────────────────────────────────────────
    _print_step(5, "Saving Outputs — JSON · CSV · Excel · Markdown Report")
    output_paths = save_all(company_name, preprocessed)

    # ── Step 6: Vector Store ──────────────────────────────────────
    if not skip_vector_store:
        _print_step(6, "Vector Store — Embed Chunks → ChromaDB (local)")
        vs = VectorStore(company_name)
        stored = vs.upsert_chunks(preprocessed["records"])
        db_info = vs.info()
    else:
        _print_step(6, "Vector Store [SKIPPED]")
        db_info = {}
        stored  = 0

    # ── Optional: query ───────────────────────────────────────────
    if query and not skip_vector_store:
        print(f"\n{'─'*62}")
        print(f"  🔍 Query: {query}")
        print(f"{'─'*62}")
        vs = VectorStore(company_name)
        results = vs.query(query)
        _print_query_results(results)

    # ── Final Summary ─────────────────────────────────────────────
    elapsed = time.time() - t0
    df      = preprocessed["dataframe"]
    _print_summary(company_name, df, stored, db_info, output_paths, elapsed)

    return preprocessed, output_paths


def _print_query_results(results: list[dict]):
    if not results:
        print("  No results found.")
        return
    for i, r in enumerate(results, 1):
        print(f"\n  [{i}] Score: {r['score']}%  |  Source: {r['source']}  |  Page: {r.get('page_number', '-')}")
        print(f"      Title: {r.get('title', '')[:70]}")
        print(f"      {r['text'][:250]}…")


def _print_summary(company, df, stored, db_info, paths, elapsed):
    total = len(df)
    col = db_info.get("collection", "—")
    dims = db_info.get("dimensions", "—")
    emb  = db_info.get("embedder", "—")
    folder = paths.get("output_folder", "")
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                    ✅  PIPELINE COMPLETE                       ║
╠══════════════════════════════════════════════════════════════╣
║  Company          : {company:<40} ║
║  Total chunks     : {total:<40} ║
║  Stored in DB     : {stored:<40} ║
║  Embedding model  : {emb:<40} ║
║  Vector dims      : {str(dims):<40} ║
║  DB collection    : {col:<40} ║
║  Time elapsed     : {elapsed:.1f}s{'':<37} ║
╠══════════════════════════════════════════════════════════════╣
║  OUTPUT FILES (in output/ folder):                           ║
║   📄 company_report.md      Markdown intelligence report     ║
║   📊 processed_data.csv     All chunks as CSV                ║
║   📑 company_intelligence.xlsx  Excel report                 ║
║   🗂  raw_records.json       Full JSON data                   ║
║   🧠 ./chroma_db/           ChromaDB vector database         ║
╚══════════════════════════════════════════════════════════════╝
""")


# ─────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description="AI Sales Intelligence Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--company",        type=str, default="",    help="Target company name")
    p.add_argument("--url",            type=str, default="",    help="Company website URL")
    p.add_argument("--docs-folder",    type=str, default="",    help="Folder with local PDFs/Excel")
    p.add_argument("--skip-web",       action="store_true",     help="Skip web scraping")
    p.add_argument("--skip-docs",      action="store_true",     help="Skip document ingestion")
    p.add_argument("--skip-linkedin",  action="store_true",     help="Skip LinkedIn collection")
    p.add_argument("--skip-pinecone",  action="store_true",     help="Skip vector store (alias)")
    p.add_argument("--proxycurl-key",  type=str, default="",    help="ProxyCurl API key")
    p.add_argument("--linkedin-url",   type=str, default="",    help="Company LinkedIn URL")
    p.add_argument("--query",          type=str, default="",    help="Query vector store after pipeline")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    company = args.company
    if not company:
        print(BANNER)
        company = input("\n  Enter target company name [Default: Apple]: ").strip()
        if not company:
            company = "Apple"
            print(f"  [INFO] Defaulting to target company: {company}")

    run_pipeline(
        company_name         = company,
        company_url          = args.url,
        docs_folder          = args.docs_folder,
        skip_web             = args.skip_web,
        skip_docs            = args.skip_docs,
        skip_linkedin        = args.skip_linkedin,
        skip_vector_store    = args.skip_pinecone,
        proxycurl_api_key    = args.proxycurl_key or os.getenv("PROXYCURL_API_KEY", ""),
        company_linkedin_url = args.linkedin_url,
        query                = args.query,
    )
