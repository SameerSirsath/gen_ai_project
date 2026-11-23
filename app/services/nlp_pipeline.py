"""
app/services/nlp_pipeline.py — NLP Extraction, Text Chunking, and ChromaDB Sync Pipeline.
"""

from __future__ import annotations

import re
import logging
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
import spacy
from keybert import KeyBERT
import chromadb
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)

# Initialize singletons as specified
nlp = spacy.load("en_core_web_sm")
kw_model = KeyBERT()
chroma_client = chromadb.PersistentClient(path="./chroma_db")

# Initialize text splitter
text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)

TARGET_ENTITIES = {"ORG", "PERSON", "GPE", "MONEY", "PRODUCT"}


def clean_text(raw_text: str) -> str:
    """
    Strips HTML using BeautifulSoup and cleans whitespace using regex.
    """
    if not raw_text:
        return ""
    soup = BeautifulSoup(raw_text, "html.parser")
    text = soup.get_text(separator=" ")
    return re.sub(r"\s+", " ", text).strip()


def process_and_sync_to_chroma(lead_id: int, raw_text: str) -> Dict[str, Any]:
    """
    1. Clean Text: Use BeautifulSoup to strip HTML. Use regex to clean whitespace.
    2. NLP Extraction: Use spaCy to extract entities (ORG, PERSON, GPE, MONEY, PRODUCT).
       Use KeyBERT to extract top 5 keywords.
    3. Chunking: Use RecursiveCharacterTextSplitter (chunk_size=500, chunk_overlap=50).
    4. ChromaDB Sync: Get or create collection lead_{lead_id} (cosine space).
       Upsert the chunks with metadata: lead_id, chunk_index, keywords, entities.
    5. Returns dict with status, chunks_created, keywords, and entity_count.
    """
    # 1. Clean Text
    cleaned = clean_text(raw_text)
    if not cleaned:
        return {
            "status": "success",
            "chunks_created": 0,
            "keywords": [],
            "entity_count": 0,
        }

    # 2. NLP Extraction
    doc = nlp(cleaned)
    extracted_entities: List[str] = []
    for ent in doc.ents:
        if ent.label_ in TARGET_ENTITIES:
            text_val = ent.text.strip()
            if text_val and text_val not in extracted_entities:
                extracted_entities.append(text_val)

    top_entities = extracted_entities[:5]

    # KeyBERT extraction (top 5 keywords)
    keywords: List[str] = []
    try:
        kw_results = kw_model.extract_keywords(
            cleaned,
            keyphrase_ngram_range=(1, 2),
            stop_words="english",
            top_n=5,
        )
        keywords = [k[0] for k in kw_results]
    except Exception as e:
        logger.warning(f"KeyBERT extraction error: {e}. Falling back to entity tokens.")
        keywords = top_entities[:5]

    # 3. Chunking
    chunks = text_splitter.split_text(cleaned)
    if not chunks and cleaned:
        chunks = [cleaned]

    # 4. ChromaDB Sync
    collection_name = f"lead_{lead_id}"
    collection = chroma_client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"}
    )

    ids: List[str] = []
    metadatas: List[Dict[str, Any]] = []

    keywords_str = ", ".join(keywords)
    entities_str = ", ".join(top_entities)

    for i, chunk in enumerate(chunks):
        chunk_id = f"lead_{lead_id}_chunk_{i}"
        ids.append(chunk_id)
        metadatas.append({
            "lead_id": int(lead_id),
            "chunk_index": i,
            "keywords": keywords_str,
            "entities": entities_str,
        })

    if chunks:
        collection.upsert(
            ids=ids,
            documents=chunks,
            metadatas=metadatas,
        )

    # 5. Return dict
    return {
        "status": "success",
        "chunks_created": len(chunks),
        "keywords": keywords,
        "entity_count": len(extracted_entities),
    }


def process_lead_text(raw_text: str) -> Dict[str, Any]:
    """
    Backward-compatibility helper returning cleaned text, chunks, keywords, and entities.
    """
    cleaned = clean_text(raw_text)
    if not cleaned:
        return {"cleaned_text": "", "chunks": [], "keywords": [], "entities": []}

    doc = nlp(cleaned)
    entities = [ent.text.strip() for ent in doc.ents if ent.label_ in TARGET_ENTITIES]
    top_entities = list(dict.fromkeys(entities))[:5]

    try:
        kw_results = kw_model.extract_keywords(cleaned, top_n=5, stop_words="english")
        keywords = [k[0] for k in kw_results]
    except Exception:
        keywords = top_entities[:5]

    chunks = text_splitter.split_text(cleaned)
    return {
        "cleaned_text": cleaned,
        "chunks": chunks or [cleaned],
        "keywords": keywords,
        "entities": top_entities,
    }
