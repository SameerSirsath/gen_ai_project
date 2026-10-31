"""
demo.py — Interactive Terminal Demonstration
=============================================
Walks you through the entire pipeline live using the PDF and Excel
file already in the AI_Sales folder.

Run:
    python demo.py

What it shows:
    Step 1 → OCR the local "AI-Powered Sales Outreach.pdf"  (Layer 1 digital extraction)
    Step 2 → Read the local Excel research table
    Step 3 → Preprocess with smart chunking (page_aware for PDF, fixed_token for Excel)
    Step 4 → Store in ChromaDB (local vector DB)
    Step 5 → Interactive semantic search — type queries, see results
"""

import os
import sys
import time

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

# ── terminal colours (no external library needed) ──────────────────
def _c(text, code): return f"\033[{code}m{text}\033[0m"

BOLD    = lambda t: _c(t, "1")
GREEN   = lambda t: _c(t, "32")
CYAN    = lambda t: _c(t, "36")
YELLOW  = lambda t: _c(t, "33")
MAGENTA = lambda t: _c(t, "35")
RED     = lambda t: _c(t, "31")
DIM     = lambda t: _c(t, "2")
WHITE   = lambda t: _c(t, "97")


# ── helpers ────────────────────────────────────────────────────────

def banner():
    print()
    print(CYAN("╔══════════════════════════════════════════════════════════════╗"))
    print(CYAN("║") + BOLD(WHITE("    🚀  AI Sales Intelligence  —  Terminal Demo              ")) + CYAN("║"))
    print(CYAN("║") + DIM("    PDF OCR · Smart Chunking · ChromaDB Vector Search        ") + CYAN("║"))
    print(CYAN("╚══════════════════════════════════════════════════════════════╝"))
    print()

def section(title: str):
    print()
    print(YELLOW("▶ " + "─" * 58))
    print(YELLOW(f"  {title}"))
    print(YELLOW("  " + "─" * 58))

def ok(msg):   print(GREEN("  ✓ ") + msg)
def info(msg): print(CYAN("  ℹ ") + msg)
def warn(msg): print(YELLOW("  ⚠ ") + msg)
def err(msg):  print(RED("  ✗ ") + msg)

def pause(secs=0.6):
    time.sleep(secs)

def wait_key(prompt="  Press ENTER to continue…"):
    input(MAGENTA(prompt))

def progress_bar(label: str, total: int, current: int, width: int = 40):
    filled = int(width * current / max(total, 1))
    bar = "█" * filled + "░" * (width - filled)
    pct = int(current / max(total, 1) * 100)
    print(f"\r  {DIM(label)} [{GREEN(bar)}] {pct}%", end="", flush=True)
    if current >= total:
        print()


# ── path setup ─────────────────────────────────────────────────────
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT_DIR)

PDF_FILE   = os.path.join(ROOT_DIR, "AI-Powered Sales Outreach.pdf")
EXCEL_FILE = os.path.join(ROOT_DIR, "Research Papers Table for AI-Powered Sales Outreach Project.xlsx")


# ═══════════════════════════════════════════════════════════════════
# DEMO STEP 1 — Verify Files
# ═══════════════════════════════════════════════════════════════════

def demo_verify_files():
    section("DEMO STEP 1 — Verify Local Files")
    info(f"Looking in: {ROOT_DIR}")
    pause()

    all_ok = True
    for path, label in [(PDF_FILE, "PDF document"), (EXCEL_FILE, "Excel file")]:
        if os.path.exists(path):
            size_kb = os.path.getsize(path) // 1024
            ok(f"{label}: {os.path.basename(path)}  ({size_kb} KB)")
        else:
            warn(f"{label} NOT FOUND: {os.path.basename(path)}")
            all_ok = False

    if not all_ok:
        warn("Some files missing — demo will still run with available files.")
    pause()
    return all_ok


# ═══════════════════════════════════════════════════════════════════
# DEMO STEP 2 — Three-Layer PDF OCR
# ═══════════════════════════════════════════════════════════════════

def demo_pdf_ocr() -> list[dict]:
    section("DEMO STEP 2 — Three-Layer PDF OCR Pipeline")
    info("Layer 1: Digital text extraction  (pdfplumber)")
    info("Layer 2: Tesseract OCR fallback   (for scanned pages)")
    info("Layer 3: Table → Markdown         (structured data)")
    print()

    if not os.path.exists(PDF_FILE):
        warn("PDF not found — skipping OCR demo.")
        return []

    from pipeline.ocr import extract_pdf
    print(f"  Processing: {BOLD(os.path.basename(PDF_FILE))}")
    pause(0.4)

    pages = extract_pdf(PDF_FILE)

    if not pages:
        warn("No pages extracted (pdfplumber may not be installed).")
        return []

    print()
    ok(f"Extracted {len(pages)} pages")

    # Show per-page summary table
    print()
    print(DIM("  Page  │ Method   │ Confidence │ Words │ Tables"))
    print(DIM("  ──────┼──────────┼────────────┼───────┼───────"))
    for p in pages[:10]:
        method    = GREEN("digital") if p["method"] == "digital" else YELLOW("ocr")
        conf_col  = GREEN(f"{p['confidence']:5.1f}%") if p["confidence"] >= 60 else RED(f"{p['confidence']:5.1f}%")
        has_table = CYAN("yes") if p["has_tables"] else DIM("no ")
        print(f"  {p['page_num']:4d}  │ {method:<16} │ {conf_col:>10}   │ {p['word_count']:5d} │ {has_table}")

    if len(pages) > 10:
        print(DIM(f"  … and {len(pages) - 10} more pages"))

    # Show sample text from page 1
    print()
    print(DIM("  ── Sample text (page 1, first 400 chars) ──"))
    sample = pages[0].get("text", "")[:400].replace("\n", " ")
    print(f"  {DIM(sample)}…")

    # Show a table if found
    for p in pages:
        if p.get("tables"):
            print()
            print(DIM("  ── First extracted table ──"))
            table_lines = p["tables"][0].split("\n")[:8]
            for ln in table_lines:
                print(f"  {CYAN(ln)}")
            break

    pause(0.5)
    return pages


# ═══════════════════════════════════════════════════════════════════
# DEMO STEP 3 — Smart Chunking
# ═══════════════════════════════════════════════════════════════════

def demo_chunking(pages: list[dict]) -> list[dict]:
    section("DEMO STEP 3 — Smart Chunking Strategies")

    info("Strategy router picks the best strategy per source type:")
    print(f"  {DIM('local_pdf')}    → {GREEN('page_aware')}   (respects PDF page boundaries)")
    print(f"  {DIM('spreadsheet')} → {GREEN('fixed_token')}  (equal-size token windows)")
    print(f"  {DIM('web page')}    → {GREEN('sentence')}     (natural language boundaries)")
    print(f"  {DIM('research doc')}→ {GREEN('hierarchical')} (section-aware splitting)")
    print()

    from pipeline.chunking import chunk_page_aware, chunk_fixed_token, chunk_sentence
    from pipeline.chunking.token_counter import tokens_available

    tok_status = GREEN("tiktoken") if tokens_available() else YELLOW("word-based approx")
    info(f"Token counter: {tok_status}")
    pause(0.4)

    all_chunks = []

    # Chunk PDF pages with page_aware strategy
    if pages:
        print()
        info("Chunking PDF with page_aware strategy…")
        pause(0.3)
        pdf_chunks = chunk_page_aware(pages)
        all_chunks.extend([{**c, "source": "local_pdf",
                             "title": os.path.basename(PDF_FILE),
                             "url": PDF_FILE, "company": "Demo Company",
                             "topics": []} for c in pdf_chunks])
        ok(f"{len(pdf_chunks)} chunks from PDF ({len(pages)} pages → {len(pdf_chunks)} chunks)")

        # Show chunk distribution
        from_pages = {}
        for c in pdf_chunks:
            pg = c.get("page_number", 0)
            from_pages[pg] = from_pages.get(pg, 0) + 1
        print(DIM(f"  Chunks per page: { {k: v for k, v in list(sorted(from_pages.items()))[:8]} }"))

        # Show sample chunk
        if pdf_chunks:
            print()
            print(DIM("  ── Sample chunk (chunk 0) ──"))
            sample = pdf_chunks[0]["text"][:300].replace("\n", " ")
            print(f"  Tokens: {CYAN(str(pdf_chunks[0]['token_count']))} | Page: {CYAN(str(pdf_chunks[0]['page_number']))}")
            print(f"  {DIM(sample)}…")

    # Demo other strategies on synthetic text
    print()
    info("Demonstrating all 5 strategies on sample text…")
    pause(0.3)

    sample_text = """
    Tesla Inc. was founded in 2003 by Martin Eberhard and Marc Tarpenning, with Elon Musk joining as chairman.
    Tesla designs and manufactures electric vehicles, energy storage systems, and solar products.
    In 2023, Tesla reported revenue of $96.8 billion, a 19% increase year-over-year.
    The company operates Gigafactories in Nevada, Texas, Shanghai, and Berlin.
    Tesla's Model Y became the best-selling car globally in Q1 2023.
    The company has over 127,000 employees worldwide as of 2024.
    Recent strategic moves include the Dojo supercomputer project and FSD (Full Self-Driving) beta expansion.
    Tesla faces competition from BYD, Rivian, and traditional automakers transitioning to EVs.
    The energy division, including Powerwall and Megapack, represents a growing revenue segment.
    CEO Elon Musk has emphasized AI and autonomous driving as the core long-term value drivers.
    """

    from pipeline.chunking.strategies import (
        chunk_fixed_token, chunk_sentence, chunk_semantic,
        chunk_hierarchical
    )

    strategies = [
        ("fixed_token",   lambda: chunk_fixed_token(sample_text, chunk_size=80, overlap=15)),
        ("sentence",      lambda: chunk_sentence(sample_text, chunk_size=80, overlap=15)),
        ("semantic",      lambda: chunk_semantic(sample_text, chunk_size=80)),
        ("hierarchical",  lambda: chunk_hierarchical(sample_text, chunk_size=80, overlap=15)),
    ]

    print()
    print(f"  {'Strategy':<18} {'Chunks':>7} {'Avg tokens':>12} {'Notes'}")
    print(DIM("  " + "─" * 60))

    for name, fn in strategies:
        try:
            chunks = fn()
            avg_tok = int(sum(c["token_count"] for c in chunks) / max(len(chunks), 1))
            note = ""
            if name == "semantic":
                note = "(requires sentence-transformers)" if len(chunks) <= 2 else ""
            print(f"  {CYAN(name):<26} {str(len(chunks)):>7} {str(avg_tok):>12}  {DIM(note)}")
        except Exception as ex:
            print(f"  {YELLOW(name):<26} {'error':>7} {DIM(str(ex)[:40])}")

    pause(0.5)
    return all_chunks


# ═══════════════════════════════════════════════════════════════════
# DEMO STEP 4 — ChromaDB Vector Store
# ═══════════════════════════════════════════════════════════════════

def demo_vector_store(chunks: list[dict]) -> "VectorStore | None":
    section("DEMO STEP 4 — ChromaDB Local Vector Store")

    info("ChromaDB stores vectors locally on disk — no cloud, no API key.")
    info(f"Database path: {os.path.join(ROOT_DIR, 'chroma_db')}")
    print()

    try:
        from pipeline.vector_store import VectorStore
    except Exception as e:
        err(f"ChromaDB not available: {e}")
        print()
        print(f"  {YELLOW('Install:')} pip install chromadb")
        return None

    DEMO_COMPANY = "DemoCompany"

    print(f"  Creating collection for: {BOLD(DEMO_COMPANY)}")
    pause(0.4)

    try:
        vs = VectorStore(DEMO_COMPANY)
        emb_info = vs.embedder.info()
        ok(f"Embedder: {emb_info}")
        pause(0.3)

        if not chunks:
            warn("No chunks to store — creating synthetic sample chunks.")
            chunks = [
                {"text": "Tesla reported $96.8 billion revenue in 2023, a 19% increase.",
                 "source": "local_pdf", "title": "Tesla Report", "url": "", "company": DEMO_COMPANY,
                 "topics": ["financials"], "strategy": "page_aware", "token_count": 18,
                 "page_number": 1, "chunk_index": 0, "total_chunks": 5},
                {"text": "Tesla Model Y became the best-selling car globally in Q1 2023.",
                 "source": "local_pdf", "title": "Tesla Report", "url": "", "company": DEMO_COMPANY,
                 "topics": ["products_services"], "strategy": "page_aware", "token_count": 15,
                 "page_number": 2, "chunk_index": 1, "total_chunks": 5},
                {"text": "The company has over 127,000 employees worldwide as of 2024.",
                 "source": "local_pdf", "title": "Tesla Report", "url": "", "company": DEMO_COMPANY,
                 "topics": ["hiring"], "strategy": "page_aware", "token_count": 13,
                 "page_number": 3, "chunk_index": 2, "total_chunks": 5},
                {"text": "Elon Musk emphasized AI and autonomous driving as the core long-term value drivers.",
                 "source": "local_pdf", "title": "Tesla Report", "url": "", "company": DEMO_COMPANY,
                 "topics": ["technology", "leadership"], "strategy": "page_aware", "token_count": 16,
                 "page_number": 4, "chunk_index": 3, "total_chunks": 5},
                {"text": "Tesla faces competition from BYD, Rivian, and traditional automakers transitioning to EVs.",
                 "source": "search_result", "title": "Industry News", "url": "", "company": DEMO_COMPANY,
                 "topics": ["market_expansion"], "strategy": "fixed_token", "token_count": 16,
                 "page_number": 0, "chunk_index": 4, "total_chunks": 5},
            ]

        # Reset collection for clean demo
        vs.reset_collection()

        print()
        info(f"Upserting {len(chunks)} chunks into ChromaDB…")
        pause(0.3)

        stored = vs.upsert_chunks(chunks, show_progress=True)
        print()
        ok(f"{stored} vectors stored successfully")

        db_info = vs.info()
        print()
        print(f"  {'Collection':<18}: {CYAN(db_info['collection'])}")
        print(f"  {'Total vectors':<18}: {GREEN(str(db_info['total_vectors']))}")
        print(f"  {'Embedding model':<18}: {CYAN(db_info['embedder'])}")
        print(f"  {'Vector dimensions':<18}: {CYAN(str(db_info['dimensions']))}")
        print(f"  {'Storage path':<18}: {DIM(db_info['storage_path'])}")

        pause(0.5)
        return vs

    except Exception as e:
        err(f"Vector store error: {e}")
        import traceback
        traceback.print_exc()
        return None


# ═══════════════════════════════════════════════════════════════════
# DEMO STEP 5 — Interactive Semantic Search
# ═══════════════════════════════════════════════════════════════════

SAMPLE_QUERIES = [
    "What is the company's annual revenue?",
    "How many employees does the company have?",
    "What products or services does the company offer?",
    "Who is the CEO of the company?",
    "What are the company's main competitors?",
]


def demo_search(vs) -> None:
    section("DEMO STEP 5 — Interactive Semantic Search")

    if vs is None:
        warn("Vector store not available — skipping search demo.")
        return

    info("Type a question to search the vector store.")
    info("Type 'quit' or press ENTER with no input to exit.")
    print()

    # First: show pre-set example queries
    print(f"  {BOLD('Sample queries')} (or type your own):")
    for i, q in enumerate(SAMPLE_QUERIES, 1):
        print(f"  {DIM(str(i))}. {q}")
    print()

    while True:
        try:
            raw = input(MAGENTA("  🔍 Query: ")).strip()
        except (KeyboardInterrupt, EOFError):
            break

        if not raw or raw.lower() in ("quit", "exit", "q"):
            break

        # Allow selecting a sample by number
        if raw.isdigit() and 1 <= int(raw) <= len(SAMPLE_QUERIES):
            query = SAMPLE_QUERIES[int(raw) - 1]
            print(f"  Selected: {CYAN(query)}")
        else:
            query = raw

        print()
        results = vs.query(query, top_k=3)

        if not results:
            warn("No results found. Try a different query.")
            print()
            continue

        print(f"  {GREEN('Top results')} for: {BOLD(query)}")
        print(DIM("  " + "─" * 58))

        for i, r in enumerate(results, 1):
            score_color = GREEN if r["score"] >= 70 else YELLOW if r["score"] >= 40 else RED
            score_str = f"{r['score']:.1f}%"
            pg_str = str(r.get('page_number', '-'))
            print(f"\n  {BOLD('[' + str(i) + ']')}  Score: {score_color(score_str)}  |  "
                  f"Source: {CYAN(r['source'])}  |  "
                  f"Page: {DIM(pg_str)}")
            print(f"       Topics: {DIM(r.get('topics', ''))}")
            snippet = r["text"][:280].replace("\n", " ")
            ellipsis = "..." if len(r["text"]) > 280 else ""
            print(f"       {DIM(snippet)}{ellipsis}")

        print()


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

def main():
    banner()

    print(f"  This demo uses files already in your workspace:")
    print(f"  {DIM('  ' + os.path.basename(PDF_FILE))}")
    print(f"  {DIM('  ' + os.path.basename(EXCEL_FILE))}")
    print()
    wait_key()

    # Step 1: Verify files
    demo_verify_files()
    wait_key()

    # Step 2: OCR
    pages = demo_pdf_ocr()
    wait_key()

    # Step 3: Chunking
    chunks = demo_chunking(pages)
    wait_key()

    # Step 4: Vector store
    vs = demo_vector_store(chunks)
    wait_key()

    # Step 5: Interactive search
    demo_search(vs)

    # Done
    print()
    print(CYAN("╔══════════════════════════════════════════════════════════════╗"))
    print(CYAN("║") + BOLD(WHITE("   🎉  Demo complete!                                         ")) + CYAN("║"))
    print(CYAN("║") + DIM("   Run the full pipeline:                                     ") + CYAN("║"))
    print(CYAN("║") + CYAN("     python run_pipeline.py --company \"YourCompany\"           ") + CYAN("║"))
    print(CYAN("║") + DIM("   Query later:                                               ") + CYAN("║"))
    print(CYAN("║") + CYAN("     python run_pipeline.py --company \"YourCo\" --query \"...\" ") + CYAN("║"))
    print(CYAN("╚══════════════════════════════════════════════════════════════╝"))
    print()


if __name__ == "__main__":
    main()
