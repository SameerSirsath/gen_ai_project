"""
app/services/vector_service.py — ChromaDB Vector Store Integration Service.
Handles chunk indexing and semantic retrieval for leads and company profile.
"""

from __future__ import annotations

import uuid
from typing import List, Dict, Any, Optional

from pipeline.vector_store import get_vector_store, Document
from app.services.nlp_pipeline import process_lead_text


def sync_to_chroma(lead_id: Any, text: str) -> Dict[str, Any]:
    """
    Runs NLP cleaning, extraction, and chunking on input text,
    then embeds and stores the chunks into ChromaDB under namespace `lead_{lead_id}`.
    """
    if not text or not str(text).strip():
        return {"chunks_count": 0, "keywords": [], "entities": []}

    nlp_result = process_lead_text(text)
    chunks = nlp_result["chunks"]

    namespace = f"lead_{lead_id}"
    vs = get_vector_store(namespace=namespace)

    docs = []
    for idx, chunk in enumerate(chunks):
        doc_id = f"lead_{lead_id}_chunk_{idx}_{uuid.uuid4().hex[:6]}"
        metadata = {
            "lead_id": str(lead_id),
            "chunk_index": idx,
            "source": "lead_context",
        }
        docs.append(Document(id=doc_id, text=chunk, metadata=metadata))

    if docs:
        try:
            vs.add_documents(docs, namespace=namespace)
        except Exception as e:
            print(f"[VectorService] Error adding documents to ChromaDB: {e}")

    return {
        "chunks_count": len(docs),
        "keywords": nlp_result["keywords"],
        "entities": nlp_result["entities"],
    }


def sync_company_profile_to_chroma(company_text: str) -> Dict[str, Any]:
    """
    Embeds and stores the user's company profile into ChromaDB
    under the `our_company` namespace.
    """
    if not company_text or not company_text.strip():
        return {"chunks_count": 0}

    nlp_result = process_lead_text(company_text)
    chunks = nlp_result["chunks"]

    namespace = "our_company"
    vs = get_vector_store(namespace=namespace)

    docs = []
    for idx, chunk in enumerate(chunks):
        doc_id = f"company_profile_chunk_{idx}_{uuid.uuid4().hex[:6]}"
        metadata = {
            "source": "company_profile",
            "chunk_index": idx,
        }
        docs.append(Document(id=doc_id, text=chunk, metadata=metadata))

    if docs:
        try:
            vs.add_documents(docs, namespace=namespace)
        except Exception as e:
            print(f"[VectorService] Error indexing company profile in ChromaDB: {e}")

    return {"chunks_count": len(docs)}


def search_lead_context(lead_id: Any, query: str, top_k: int = 5) -> str:
    """
    Retrieves the top-k most semantically relevant chunks for a specific lead.
    Returns concatenated context string.
    """
    namespace = f"lead_{lead_id}"
    try:
        vs = get_vector_store(namespace=namespace)
        results = vs.query(text=query, top_k=top_k)
        if results:
            texts = [getattr(r, "text", getattr(r, "page_content", str(r))) for r in results]
            return "\n\n".join(texts)
    except Exception as e:
        logger.warning(f"[VectorService] Note: error querying lead context for {namespace}: {e}")
    return ""


def search_company_profile(query: str, top_k: int = 3) -> str:
    """
    Retrieves relevant capability and value proposition chunks
    from the `our_company` namespace.
    """
    namespace = "our_company"
    try:
        vs = get_vector_store(namespace=namespace)
        results = vs.query(text=query, top_k=top_k)
        if results:
            texts = [getattr(r, "text", getattr(r, "page_content", str(r))) for r in results]
            return "\n\n".join(texts)
    except Exception as e:
        logger.warning(f"[VectorService] Note: error querying company profile: {e}")
    return ""
