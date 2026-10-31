"""
chroma_client.py — Local ChromaDB Vector Store

ChromaDB is a local, persistent vector database that lives entirely on disk.
No cloud account, no API key, no Docker — just pip install chromadb.

Data is stored in:  ./chroma_db/   (relative to project root)

One ChromaDB collection per company:
  "aisales_tesla"     → all Tesla chunks
  "aisales_microsoft" → all Microsoft chunks

Usage:
  from pipeline.vector_store import VectorStore

  vs = VectorStore("Tesla")
  vs.upsert_chunks(chunks)                          # store
  results = vs.query("What is their revenue?")      # search
  vs.info()                                         # stats
  vs.list_all_collections()                         # see all companies
"""

import os
import re
import uuid
import json
from typing import Optional

from ..config import CHROMA_DIR, CHROMA_COLLECTION_PREFIX, CHROMA_TOP_K
from .embedder import Embedder


class VectorStore:
    """
    Local ChromaDB-backed vector store.
    One instance = one company collection.
    """

    def __init__(self, company_name: str, embedder: Optional[Embedder] = None):
        """
        Args:
            company_name: Target company (e.g. "Tesla").
                          Collection name = "aisales_tesla".
            embedder:     Optional pre-created Embedder.
                          A new one is created automatically if not provided.
        """
        self.company_name     = company_name
        self.collection_name  = self._make_collection_name(company_name)
        self.embedder         = embedder or Embedder()
        self._client          = None
        self._collection      = None
        self._init_chroma()

    # ─────────────────────────────────────────────
    # Initialisation
    # ─────────────────────────────────────────────

    @staticmethod
    def _make_collection_name(company_name: str) -> str:
        """
        ChromaDB collection names must match: ^[a-zA-Z0-9][a-zA-Z0-9_-]{1,60}$
        """
        safe = re.sub(r"[^a-zA-Z0-9_-]", "_", company_name.lower())
        safe = re.sub(r"_+", "_", safe).strip("_")
        return f"{CHROMA_COLLECTION_PREFIX}_{safe}"[:62]

    def _init_chroma(self):
        """Connect to / create the ChromaDB persistent client and collection."""
        try:
            import chromadb
            from chromadb.config import Settings

            os.makedirs(CHROMA_DIR, exist_ok=True)

            self._client = chromadb.PersistentClient(path=CHROMA_DIR)

            # Get or create the collection for this company
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={
                    "company":   self.company_name,
                    "embedding": self.embedder.provider,
                    "dims":      str(self.embedder.dimensions),
                    "hnsw:space": "cosine",   # cosine similarity metric
                },
            )

            # Check if existing collection dimension matches current embedder
            if self._collection.count() > 0:
                sample = self._collection.get(include=["embeddings"], limit=1)
                if sample.get("embeddings") is not None and len(sample["embeddings"]) > 0:
                    existing_dim = len(sample["embeddings"][0])
                    if existing_dim != self.embedder.dimensions:
                        print(f"    [CHROMA] Dimension mismatch: collection has {existing_dim}d, "
                              f"current embedder has {self.embedder.dimensions}d ({self.embedder.provider}). Recreating collection...")
                        self._client.delete_collection(self.collection_name)
                        self._collection = self._client.create_collection(
                            name=self.collection_name,
                            metadata={
                                "company":   self.company_name,
                                "embedding": self.embedder.provider,
                                "dims":      str(self.embedder.dimensions),
                                "hnsw:space": "cosine",
                            },
                        )

            print(f"    [CHROMA] Collection '{self.collection_name}' ready "
                  f"({self._collection.count()} existing vectors)")
        except ImportError:
            print("    [CHROMA] ChromaDB not installed. Run: pip install chromadb")
            raise

    # ─────────────────────────────────────────────
    # Upsert
    # ─────────────────────────────────────────────

    def upsert_chunks(self, chunks: list[dict], show_progress: bool = True) -> int:
        """
        Embed and store a list of chunk dicts into ChromaDB.

        Args:
            chunks:        List of chunk dicts from the chunking module.
            show_progress: Print progress bar to terminal.

        Returns:
            Number of chunks stored.
        """
        if not chunks:
            return 0

        # Filter chunks with text
        valid = [c for c in chunks if c.get("text", "").strip()]
        if not valid:
            return 0

        print(f"\n    [CHROMA] Embedding {len(valid)} chunks via {self.embedder.provider}…")

        texts = [c["text"] for c in valid]
        vectors = self.embedder.embed(texts)

        if not vectors:
            print("    [CHROMA] Embedding failed — no vectors produced.")
            return 0

        # Build IDs and metadata for ChromaDB
        ids       = []
        metadatas = []
        documents = []

        for chunk, vector in zip(valid, vectors):
            # Unique ID = collection + chunk hash
            uid = f"{self.collection_name}_{uuid.uuid4().hex[:12]}"
            ids.append(uid)
            documents.append(chunk["text"])

            # ChromaDB metadata must be flat (str / int / float / bool only)
            meta = {
                "company":      str(chunk.get("company", self.company_name)),
                "source":       str(chunk.get("source", "")),
                "title":        str(chunk.get("title", ""))[:200],
                "url":          str(chunk.get("url", ""))[:500],
                "page_number":  int(chunk.get("page_number", 0)),
                "chunk_index":  int(chunk.get("chunk_index", 0)),
                "total_chunks": int(chunk.get("total_chunks", 1)),
                "strategy":     str(chunk.get("strategy", "")),
                "token_count":  int(chunk.get("token_count", 0)),
                "word_count":   int(chunk.get("word_count", len(chunk["text"].split()))),
                "topics":       ", ".join(chunk.get("topics", [])) if isinstance(chunk.get("topics"), list) else str(chunk.get("topics", "")),
                "processed_at": str(chunk.get("processed_at", "")),
                "section_title": str(chunk.get("section_title", "")),
            }
            metadatas.append(meta)

        # Upsert in batches of 100 (ChromaDB limit)
        batch_size = 100
        stored = 0
        for i in range(0, len(ids), batch_size):
            batch_ids   = ids[i: i + batch_size]
            batch_docs  = documents[i: i + batch_size]
            batch_meta  = metadatas[i: i + batch_size]
            batch_vecs  = vectors[i: i + batch_size]

            self._collection.upsert(
                ids        = batch_ids,
                documents  = batch_docs,
                metadatas  = batch_meta,
                embeddings = batch_vecs,
            )
            stored += len(batch_ids)

            if show_progress:
                pct = int(stored / len(ids) * 100)
                bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
                print(f"\r        [{bar}] {pct}% ({stored}/{len(ids)})", end="", flush=True)

        if show_progress:
            print()  # newline after progress bar

        total_now = self._collection.count()
        print(f"    [CHROMA] ✓ Stored {stored} chunks | Collection total: {total_now}")
        return stored

    # ─────────────────────────────────────────────
    # Query / Semantic Search
    # ─────────────────────────────────────────────

    def query(
        self,
        query_text: str,
        top_k:      int = CHROMA_TOP_K,
        filter_meta: Optional[dict] = None,
    ) -> list[dict]:
        """
        Semantic search: find the top_k most relevant chunks.

        Args:
            query_text:  Natural language query string.
            top_k:       Number of results to return.
            filter_meta: Optional ChromaDB metadata filter dict.
                         e.g. {"source": "local_pdf"} or {"page_number": 3}

        Returns:
            List of result dicts, each containing:
              text, score, source, title, url, page_number, chunk_index, topics
        """
        if not query_text.strip():
            return []

        query_vec = self.embedder.embed_one(query_text)
        if not query_vec:
            return []

        kwargs = dict(
            query_embeddings=[query_vec],
            n_results=min(top_k, max(self._collection.count(), 1)),
            include=["documents", "metadatas", "distances"],
        )
        if filter_meta:
            kwargs["where"] = filter_meta

        results = self._collection.query(**kwargs)

        output = []
        if not results or not results.get("ids"):
            return output

        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            # ChromaDB cosine distance: 0 = identical, 2 = opposite
            # Convert to similarity score 0-100
            similarity = round((1 - dist / 2) * 100, 1)
            output.append({
                "text":        doc,
                "score":       similarity,
                "source":      meta.get("source", ""),
                "title":       meta.get("title", ""),
                "url":         meta.get("url", ""),
                "page_number": meta.get("page_number", 0),
                "chunk_index": meta.get("chunk_index", 0),
                "strategy":    meta.get("strategy", ""),
                "topics":      meta.get("topics", ""),
            })

        return sorted(output, key=lambda x: x["score"], reverse=True)

    # ─────────────────────────────────────────────
    # Utility
    # ─────────────────────────────────────────────

    def info(self) -> dict:
        """Return collection statistics."""
        count = self._collection.count()
        return {
            "collection":  self.collection_name,
            "company":     self.company_name,
            "total_vectors": count,
            "embedder":    self.embedder.provider,
            "dimensions":  self.embedder.dimensions,
            "storage_path": CHROMA_DIR,
        }

    def delete_collection(self):
        """Permanently delete this company's collection from ChromaDB."""
        self._client.delete_collection(self.collection_name)
        print(f"    [CHROMA] Collection '{self.collection_name}' deleted.")

    def reset_collection(self):
        """Delete and recreate an empty collection (clears all data)."""
        self.delete_collection()
        self._init_chroma()

    @staticmethod
    def list_all_collections() -> list[str]:
        """List all company collections stored in ChromaDB."""
        try:
            import chromadb
            client = chromadb.PersistentClient(path=CHROMA_DIR)
            cols = client.list_collections()
            return [c.name for c in cols]
        except Exception:
            return []
