# pipeline/vector_store/__init__.py
"""
Vector Store Package  (local ChromaDB)
=======================================
Provides a local, persistent vector database powered by ChromaDB.
No cloud account or API key required — data lives in ./chroma_db/

Components
----------
  embedder.py       — Generates text embeddings.
                      Priority: OpenAI → Google → sentence-transformers (offline).

  chroma_client.py  — ChromaDB wrapper: create collection, upsert chunks,
                      semantic search, list collections, delete.

Typical flow
------------
  1. embedder.embed(texts)          → list of float vectors
  2. chroma.upsert(chunks, vectors) → stored in local DB
  3. chroma.query("revenue Q4")     → top-K relevant chunks

Public API
----------
  from pipeline.vector_store import VectorStore
  vs = VectorStore(company_name="Tesla")
  vs.upsert_chunks(chunks)                      # embed + store
  results = vs.query("What is their revenue?")  # semantic search
  vs.info()                                     # collection stats
"""

from .chroma_client import VectorStore

__all__ = ["VectorStore"]
