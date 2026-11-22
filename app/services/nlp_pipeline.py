"""
app/services/nlp_pipeline.py — NLP Extraction, Text Cleaning, and Chunking Pipeline.
"""

from __future__ import annotations

import re
import html
from typing import List, Dict, Any, Optional

# Lazy singletons for efficiency
_SPACY_NLP = None
_KEYBERT_MODEL = None
_TIKTOKEN_ENC = None


def get_spacy_nlp():
    """Lazy loader for spaCy English model."""
    global _SPACY_NLP
    if _SPACY_NLP is None:
        import spacy
        try:
            _SPACY_NLP = spacy.load("en_core_web_sm")
        except Exception:
            _SPACY_NLP = spacy.blank("en")
    return _SPACY_NLP


def get_keybert_model():
    """Lazy loader for KeyBERT model."""
    global _KEYBERT_MODEL
    if _KEYBERT_MODEL is None:
        try:
            from keybert import KeyBERT
            _KEYBERT_MODEL = KeyBERT()
        except Exception as e:
            print(f"[NLP Pipeline] Warning: Could not initialize KeyBERT ({e}). Using regex/spacy fallback.")
            _KEYBERT_MODEL = False
    return _KEYBERT_MODEL


def clean_text(raw_text: str) -> str:
    """
    Cleans raw input text:
    - Strips HTML tags
    - Unescapes HTML entities
    - Normalizes whitespace and line breaks
    """
    if not raw_text:
        return ""

    # Unescape HTML entities (&amp;, &lt;, etc.)
    text = html.unescape(raw_text)

    # Strip HTML tags
    text = re.sub(r"<[^>]+>", " ", text)

    # Remove non-printable / control characters except standard punctuation and newlines
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", " ", text)

    # Normalize multiple whitespaces and excessive newlines
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def extract_entities_and_keywords(cleaned_text: str, top_n: int = 5) -> Dict[str, Any]:
    """
    Uses spaCy for Named Entities and KeyBERT for top keywords/phrases.
    """
    entities = []
    keywords = []

    if not cleaned_text:
        return {"entities": entities, "keywords": keywords}

    # 1. spaCy Named Entities
    try:
        nlp = get_spacy_nlp()
        doc = nlp(cleaned_text[:5000])  # limit first 5000 chars for fast entity extraction
        for ent in doc.ents:
            if ent.label_ in ("PERSON", "ORG", "GPE", "PRODUCT", "MONEY", "DATE"):
                entities.append({
                    "text": ent.text.strip(),
                    "label": ent.label_
                })
        # Deduplicate entities by (text, label)
        seen = set()
        unique_entities = []
        for e in entities:
            key = (e["text"].lower(), e["label"])
            if key not in seen:
                seen.add(key)
                unique_entities.append(e)
        entities = unique_entities
    except Exception as e:
        print(f"[NLP Pipeline] spaCy entity extraction failed: {e}")

    # 2. KeyBERT Top Keywords/Phrases
    try:
        kw_model = get_keybert_model()
        if kw_model:
            extracted = kw_model.extract_keywords(
                cleaned_text[:3000],
                keyphrase_ngram_range=(1, 2),
                stop_words="english",
                top_n=top_n
            )
            keywords = [k[0] for k in extracted if isinstance(k, (list, tuple))]
    except Exception as e:
        print(f"[NLP Pipeline] KeyBERT extraction failed: {e}")

    # Fallback keyword extraction using nouns/entities if KeyBERT yields empty
    if not keywords and entities:
        keywords = [e["text"] for e in entities[:top_n]]

    return {"entities": entities, "keywords": keywords}


def chunk_text(
    text: str,
    chunk_size: int = 500,
    chunk_overlap: int = 50
) -> List[str]:
    """
    Splits text into chunks of `chunk_size` tokens with `chunk_overlap` tokens overlap.
    Uses tiktoken cl100k_base or word tokenization fallback.
    """
    if not text:
        return []

    global _TIKTOKEN_ENC
    try:
        if _TIKTOKEN_ENC is None:
            import tiktoken
            _TIKTOKEN_ENC = tiktoken.get_encoding("cl100k_base")

        tokens = _TIKTOKEN_ENC.encode(text)
        if len(tokens) <= chunk_size:
            return [text]

        chunks = []
        start = 0
        step = chunk_size - chunk_overlap
        while start < len(tokens):
            chunk_tokens = tokens[start : start + chunk_size]
            chunk_str = _TIKTOKEN_ENC.decode(chunk_tokens)
            chunks.append(chunk_str.strip())
            start += step

        return chunks
    except Exception:
        # Fallback to word-based chunking (~1.3 words per token)
        words = text.split()
        target_words = int(chunk_size * 0.75)
        overlap_words = int(chunk_overlap * 0.75)
        step = max(1, target_words - overlap_words)

        chunks = []
        for i in range(0, len(words), step):
            c = " ".join(words[i : i + target_words])
            if c:
                chunks.append(c)
        return chunks or [text]


def process_lead_text(raw_text: str) -> Dict[str, Any]:
    """
    Main pipeline entry point:
    1. Clean text
    2. Extract Entities + KeyBERT Keywords
    3. Generate 500-token chunks with 50-token overlap
    """
    cleaned = clean_text(raw_text)
    nlp_data = extract_entities_and_keywords(cleaned, top_n=5)
    chunks = chunk_text(cleaned, chunk_size=500, chunk_overlap=50)

    return {
        "cleaned_text": cleaned,
        "entities": nlp_data["entities"],
        "keywords": nlp_data["keywords"],
        "chunks": chunks,
    }
