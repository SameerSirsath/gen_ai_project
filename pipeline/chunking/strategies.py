"""
strategies.py — Five document chunking strategies + automatic source-based routing.

┌──────────────────┬──────────────────────────────────────────────────────┐
│ Strategy         │ Best For                                             │
├──────────────────┼──────────────────────────────────────────────────────┤
│ fixed_token      │ Web pages, short articles, spreadsheet rows         │
│ sentence         │ News, blogs, LinkedIn posts                          │
│ semantic         │ Long research docs — splits at topic change points   │
│ page_aware       │ PDFs — respects page boundaries                      │
│ hierarchical     │ Structured docs with clear section headings          │
└──────────────────┴──────────────────────────────────────────────────────┘

Every strategy returns a list of chunk dicts:
{
  "text":           str,   # chunk content
  "chunk_index":    int,   # position within the parent record
  "total_chunks":   int,   # total number of chunks from this record
  "strategy":       str,   # which strategy was used
  "token_count":    int,   # estimated token count
  "page_number":    int,   # PDF page (only for page_aware strategy)
}
"""

import re
from typing import Optional

import nltk
try:
    nltk.data.find("tokenizers/punkt_tab")
except LookupError:
    nltk.download("punkt_tab", quiet=True)
try:
    nltk.data.find("tokenizers/punkt")
except LookupError:
    nltk.download("punkt", quiet=True)

from nltk.tokenize import sent_tokenize

from .token_counter import count_tokens, split_into_token_windows
from ..config import CHUNK_SIZE_TOKENS, CHUNK_OVERLAP_TOKENS, MIN_CHUNK_TOKENS


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

def _make_chunks(texts: list[str], strategy: str, page_numbers: list[int] = None) -> list[dict]:
    """Wrap a list of text strings into standardised chunk dicts."""
    if page_numbers is None:
        page_numbers = [0] * len(texts)

    # Filter out empty / too-short chunks
    valid = [
        (t.strip(), p) for t, p in zip(texts, page_numbers)
        if t.strip() and count_tokens(t.strip()) >= MIN_CHUNK_TOKENS
    ]

    total = len(valid)
    return [
        {
            "text":        text,
            "chunk_index": i,
            "total_chunks": total,
            "strategy":    strategy,
            "token_count": count_tokens(text),
            "page_number": page_num,
        }
        for i, (text, page_num) in enumerate(valid)
    ]


# ─────────────────────────────────────────────────────────────────
# Strategy 1: Fixed-Token
# ─────────────────────────────────────────────────────────────────

def chunk_fixed_token(
    text: str,
    chunk_size:    int = CHUNK_SIZE_TOKENS,
    overlap:       int = CHUNK_OVERLAP_TOKENS,
) -> list[dict]:
    """
    Split text into equal-sized token windows with overlap.

    Simple and predictable. Overlap prevents cutting important context
    at chunk boundaries.

         [====chunk0====]
                  [====chunk1====]
                           [====chunk2====]
    """
    windows = split_into_token_windows(text, chunk_size, overlap)
    return _make_chunks(windows, "fixed_token")


# ─────────────────────────────────────────────────────────────────
# Strategy 2: Sentence-Based
# ─────────────────────────────────────────────────────────────────

def chunk_sentence(
    text: str,
    chunk_size: int = CHUNK_SIZE_TOKENS,
    overlap:    int = CHUNK_OVERLAP_TOKENS,
) -> list[dict]:
    """
    Group sentences into chunks, never splitting mid-sentence.
    Respects natural language boundaries — ideal for narrative text.

    Overlap is implemented by prepending the last N sentences of the
    previous chunk to the next chunk.
    """
    sentences = sent_tokenize(text)
    if not sentences:
        return _make_chunks([text], "sentence")

    chunks = []
    current_sents: list[str] = []
    current_tokens = 0

    # Calculate approximate overlap in sentences
    overlap_sentences = max(1, overlap // 20)  # rough: 20 tokens per sentence

    for sent in sentences:
        sent_tokens = count_tokens(sent)
        if current_tokens + sent_tokens > chunk_size and current_sents:
            chunks.append(" ".join(current_sents))
            # Keep last few sentences as overlap
            current_sents = current_sents[-overlap_sentences:]
            current_tokens = sum(count_tokens(s) for s in current_sents)

        current_sents.append(sent)
        current_tokens += sent_tokens

    if current_sents:
        chunks.append(" ".join(current_sents))

    return _make_chunks(chunks, "sentence")


# ─────────────────────────────────────────────────────────────────
# Strategy 3: Semantic (embedding-based split points)
# ─────────────────────────────────────────────────────────────────

def chunk_semantic(
    text: str,
    chunk_size:       int   = CHUNK_SIZE_TOKENS,
    similarity_threshold: float = 0.4,
) -> list[dict]:
    """
    Split text where the topic changes, detected by a drop in cosine
    similarity between adjacent sentence embeddings.

    Uses sentence-transformers (offline) for embeddings.
    Falls back to sentence chunking if sentence-transformers is unavailable.

    Algorithm:
      1. Tokenize into sentences
      2. Embed each sentence
      3. Compute cosine similarity between consecutive sentences
      4. Split where similarity < threshold (topic change)
      5. Merge small segments to meet chunk_size budget
    """
    sentences = sent_tokenize(text)
    if len(sentences) <= 3:
        return chunk_sentence(text, chunk_size)

    # Try to get local embeddings
    try:
        from sentence_transformers import SentenceTransformer
        import numpy as np

        model = SentenceTransformer("all-MiniLM-L6-v2")
        embeddings = model.encode(sentences, show_progress_bar=False)

        # Compute cosine similarity between consecutive sentences
        def cosine_sim(a, b):
            return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-10))

        split_points = [0]
        for i in range(1, len(sentences)):
            sim = cosine_sim(embeddings[i - 1], embeddings[i])
            if sim < similarity_threshold:
                split_points.append(i)
        split_points.append(len(sentences))

        # Build segments from split points
        raw_segments = []
        for i in range(len(split_points) - 1):
            seg = " ".join(sentences[split_points[i]: split_points[i + 1]])
            raw_segments.append(seg)

        # Merge short segments to fill chunk_size budget
        final_chunks = []
        current = ""
        for seg in raw_segments:
            if count_tokens(current + " " + seg) <= chunk_size:
                current = (current + " " + seg).strip()
            else:
                if current:
                    final_chunks.append(current)
                current = seg
        if current:
            final_chunks.append(current)

        return _make_chunks(final_chunks, "semantic")

    except ImportError:
        # Graceful fallback: use sentence strategy
        return chunk_sentence(text, chunk_size)


# ─────────────────────────────────────────────────────────────────
# Strategy 4: Page-Aware (for PDFs)
# ─────────────────────────────────────────────────────────────────

def chunk_page_aware(
    pages: list[dict],
    chunk_size: int = CHUNK_SIZE_TOKENS,
    overlap:    int = CHUNK_OVERLAP_TOKENS,
) -> list[dict]:
    """
    Chunk PDF content while respecting page boundaries.

    Each page's text is chunked independently. Chunks never span across
    pages, preserving traceability to specific PDF pages.

    Args:
        pages: List of PageResult dicts from pipeline.ocr.extract_pdf()
               Each must have 'text' and 'page_num' keys.

    Returns:
        List of chunk dicts with accurate page_number metadata.
    """
    all_chunks = []
    for page in pages:
        page_text = page.get("text", "").strip()
        page_num  = page.get("page_num", 0)

        if not page_text or count_tokens(page_text) < MIN_CHUNK_TOKENS:
            continue

        if count_tokens(page_text) <= chunk_size:
            # Entire page fits in one chunk
            all_chunks.append({
                "text":         page_text,
                "chunk_index":  len(all_chunks),
                "total_chunks": 0,          # will be updated below
                "strategy":     "page_aware",
                "token_count":  count_tokens(page_text),
                "page_number":  page_num,
            })
        else:
            # Page is large — split it with overlap, keeping page_num
            windows = split_into_token_windows(page_text, chunk_size, overlap)
            for win in windows:
                win = win.strip()
                if win and count_tokens(win) >= MIN_CHUNK_TOKENS:
                    all_chunks.append({
                        "text":         win,
                        "chunk_index":  len(all_chunks),
                        "total_chunks": 0,
                        "strategy":     "page_aware",
                        "token_count":  count_tokens(win),
                        "page_number":  page_num,
                    })

    # Update total_chunks
    total = len(all_chunks)
    for chunk in all_chunks:
        chunk["total_chunks"] = total

    return all_chunks


# ─────────────────────────────────────────────────────────────────
# Strategy 5: Hierarchical (section-aware)
# ─────────────────────────────────────────────────────────────────

# Regex patterns for common section headers
_HEADER_RE = re.compile(
    r"^(?:"
    r"\d+[\.\)]\s+.+"           # "1. Introduction"  or "1) Overview"
    r"|[A-Z][A-Z\s]{3,}$"       # "EXECUTIVE SUMMARY"
    r"|#{1,4}\s+.+"             # "## Section"  (Markdown headers)
    r")",
    re.MULTILINE,
)


def chunk_hierarchical(
    text: str,
    chunk_size: int = CHUNK_SIZE_TOKENS,
    overlap:    int = CHUNK_OVERLAP_TOKENS,
) -> list[dict]:
    """
    Parse the document into sections based on header patterns,
    then chunk each section independently.

    Section structure preserved in chunk metadata via 'section_title'.

    Works best on annual reports, whitepapers, and structured articles
    that use numbered sections or ALL-CAPS headings.
    """
    lines = text.splitlines()
    sections: list[tuple[str, str]] = []  # (header, body)

    current_header = "Introduction"
    current_body_lines: list[str] = []

    for line in lines:
        if _HEADER_RE.match(line.strip()) and len(line.strip()) < 120:
            # Save current section, start new one
            if current_body_lines:
                body = "\n".join(current_body_lines).strip()
                if body:
                    sections.append((current_header, body))
            current_header = line.strip()
            current_body_lines = []
        else:
            current_body_lines.append(line)

    # Flush last section
    if current_body_lines:
        body = "\n".join(current_body_lines).strip()
        if body:
            sections.append((current_header, body))

    if not sections:
        # No headers found — fall back to sentence strategy
        return chunk_sentence(text, chunk_size, overlap)

    all_chunks: list[dict] = []
    for header, body in sections:
        section_chunks = chunk_sentence(body, chunk_size, overlap)
        for chunk in section_chunks:
            chunk["strategy"] = "hierarchical"
            chunk["section_title"] = header
            all_chunks.append(chunk)

    # Re-index
    total = len(all_chunks)
    for i, chunk in enumerate(all_chunks):
        chunk["chunk_index"] = i
        chunk["total_chunks"] = total

    return all_chunks


# ─────────────────────────────────────────────────────────────────
# Source → Strategy Router
# ─────────────────────────────────────────────────────────────────

#: Maps source type → strategy name
STRATEGY_ROUTER: dict[str, str] = {
    "local_pdf":               "page_aware",
    "pdf_download":            "page_aware",
    "company_website":         "sentence",
    "search_result":           "fixed_token",
    "search_pdf_link":         "page_aware",
    "linkedin_post_proxycurl": "sentence",
    "linkedin_post_public":    "sentence",
    "linkedin_about":          "sentence",
    "linkedin_search_snippet": "sentence",
    "spreadsheet":             "fixed_token",
}

_DEFAULT_STRATEGY = "sentence"


def chunk_record(
    record: dict,
    strategy:   str = "auto",
    chunk_size: int = CHUNK_SIZE_TOKENS,
    overlap:    int = CHUNK_OVERLAP_TOKENS,
    pages:      list[dict] = None,   # required for page_aware strategy
) -> list[dict]:
    """
    Auto-route a data record to the appropriate chunking strategy
    and return a list of chunk dicts.

    Args:
        record:     Any data record dict with at least 'text' and 'source' keys.
        strategy:   Explicit strategy name, or "auto" to route by source.
        chunk_size: Token budget per chunk.
        overlap:    Token overlap between chunks.
        pages:      PageResult list — required if strategy == "page_aware".

    Returns:
        List of chunk dicts (see module docstring for schema).
    """
    source = record.get("source", "")
    text   = record.get("text", "").strip()

    if strategy == "auto":
        strategy = STRATEGY_ROUTER.get(source, _DEFAULT_STRATEGY)

    if strategy == "page_aware":
        if pages:
            chunks = chunk_page_aware(pages, chunk_size, overlap)
        else:
            # No page data → fall back to sentence
            chunks = chunk_sentence(text, chunk_size, overlap)
            for c in chunks:
                c["strategy"] = "page_aware(fallback→sentence)"

    elif strategy == "fixed_token":
        chunks = chunk_fixed_token(text, chunk_size, overlap)

    elif strategy == "sentence":
        chunks = chunk_sentence(text, chunk_size, overlap)

    elif strategy == "semantic":
        chunks = chunk_semantic(text, chunk_size)

    elif strategy == "hierarchical":
        chunks = chunk_hierarchical(text, chunk_size, overlap)

    else:
        chunks = chunk_sentence(text, chunk_size, overlap)

    # Attach parent record metadata to every chunk
    for chunk in chunks:
        chunk.setdefault("source",  source)
        chunk.setdefault("url",     record.get("url", ""))
        chunk.setdefault("title",   record.get("title", ""))
        chunk.setdefault("company", record.get("company", ""))
        chunk.setdefault("topics",  record.get("topics", []))

    return chunks
