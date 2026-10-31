"""
chroma_client.py — Local ChromaDB Vector Store implementing VectorStore Protocol.

Configured with explicit HNSW parameters (M, construction_ef, search_ef)
derived directly from the central settings rather than relying on silent defaults.
"""

from __future__ import annotations

import os
import re
import uuid
from typing import Any, Optional

import chromadb
from config import settings

from .base import Document, VectorStore as VectorStoreProtocol
from .embedder import Embedder


class ChromaVectorStore:
    """
    Local ChromaDB-backed vector store implementing VectorStore Protocol.
    Manages collection-level storage and HNSW indexing.
    """

    def __init__(
        self,
        company_name: str = "default",
        embedder: Optional[Embedder] = None,
        m: Optional[int] = None,
        construction_ef: Optional[int] = None,
        search_ef: Optional[int] = None,
    ):
        """
        Initialize Chroma store.

        Args:
            company_name: Target company or namespace identifier.
            embedder: Optional Embedder instance.
            m: HNSW max connections per node (defaults to config: 32).
            construction_ef: HNSW dynamic list size during construction (defaults to config: 200).
            search_ef: HNSW search exploration factor (defaults to config: 100).
        """
        self.company_name = company_name
        self.collection_name = self._make_collection_name(company_name)
        self.embedder = embedder or Embedder()
        self.hnsw_m = m if m is not None else settings.CHROMA_HNSW_M
        self.hnsw_construction_ef = (
            construction_ef if construction_ef is not None else settings.CHROMA_HNSW_CONSTRUCTION_EF
        )
        self.hnsw_search_ef = (
            search_ef if search_ef is not None else settings.CHROMA_HNSW_SEARCH_EF
        )

        self._client: Optional[chromadb.PersistentClient] = None
        self._collection = None
        self._init_chroma()

    @staticmethod
    def _make_collection_name(name: str) -> str:
        """Sanitize name to match ChromaDB requirements."""
        safe = re.sub(r"[^a-zA-Z0-9_-]", "_", name.lower())
        safe = re.sub(r"_+", "_", safe).strip("_")
        return f"{settings.CHROMA_COLLECTION_PREFIX}_{safe}"[:62]

    def _init_chroma(self) -> None:
        """Connect to or create the ChromaDB collection with explicit HNSW configuration."""
        os.makedirs(settings.CHROMA_DIR, exist_ok=True)
        self._client = chromadb.PersistentClient(path=settings.CHROMA_DIR)

        metadata = {
            "company": self.company_name,
            "embedding": self.embedder.provider,
            "dims": str(self.embedder.dimensions),
            "hnsw:space": "cosine",
            "hnsw:M": self.hnsw_m,
            "hnsw:construction_ef": self.hnsw_construction_ef,
            "hnsw:search_ef": self.hnsw_search_ef,
        }

        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata=metadata,
        )

        # Dimension verification
        if self._collection.count() > 0:
            sample = self._collection.get(include=["embeddings"], limit=1)
            if sample.get("embeddings") and len(sample["embeddings"]) > 0:
                existing_dim = len(sample["embeddings"][0])
                if existing_dim != self.embedder.dimensions:
                    print(
                        f"    [CHROMA] Dimension mismatch: collection has {existing_dim}d, "
                        f"embedder has {self.embedder.dimensions}d. Recreating collection..."
                    )
                    self._client.delete_collection(self.collection_name)
                    self._collection = self._client.create_collection(
                        name=self.collection_name,
                        metadata=metadata,
                    )

    # ─────────────────────────────────────────────
    # VectorStore Protocol Implementation
    # ─────────────────────────────────────────────

    def add_documents(self, docs: list[Document], namespace: str) -> None:
        """Add documents to a Chroma collection (namespace)."""
        if not docs:
            return

        target_coll_name = self._make_collection_name(namespace)
        if target_coll_name != self.collection_name:
            coll = self._client.get_or_create_collection(
                name=target_coll_name,
                metadata={
                    "company": namespace,
                    "embedding": self.embedder.provider,
                    "dims": str(self.embedder.dimensions),
                    "hnsw:space": "cosine",
                    "hnsw:M": self.hnsw_m,
                    "hnsw:construction_ef": self.hnsw_construction_ef,
                    "hnsw:search_ef": self.hnsw_search_ef,
                },
            )
        else:
            coll = self._collection

        # Separate docs needing embeddings
        texts_to_embed = [d.text for d in docs if d.embedding is None]
        new_vecs = self.embedder.embed(texts_to_embed) if texts_to_embed else []
        vec_iter = iter(new_vecs)

        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict[str, Any]] = []
        embeddings: list[list[float]] = []

        for d in docs:
            ids.append(d.id or f"{target_coll_name}_{uuid.uuid4().hex[:12]}")
            documents.append(d.text)
            # Flatten metadata for Chroma compatibility
            flat_meta: dict[str, Any] = {}
            for k, v in d.metadata.items():
                if isinstance(v, (str, int, float, bool)):
                    flat_meta[k] = v
                elif isinstance(v, list):
                    flat_meta[k] = ", ".join(str(item) for item in v)
                else:
                    flat_meta[k] = str(v)
            metadatas.append(flat_meta)

            emb = d.embedding if d.embedding is not None else next(vec_iter)
            embeddings.append(emb)

        # Batch upsert in groups of 100
        batch_size = 100
        for i in range(0, len(ids), batch_size):
            coll.upsert(
                ids=ids[i : i + batch_size],
                documents=documents[i : i + batch_size],
                metadatas=metadatas[i : i + batch_size],
                embeddings=embeddings[i : i + batch_size],
            )

    def query(
        self,
        text: str,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
        namespace: str | None = None,
    ) -> list[Document]:
        """Query ChromaDB by semantic text similarity."""
        if not text.strip():
            return []

        coll = self._collection
        if namespace:
            target_name = self._make_collection_name(namespace)
            if target_name != self.collection_name:
                coll = self._client.get_or_create_collection(target_name)

        if coll.count() == 0:
            return []

        query_vec = self.embedder.embed_one(text)
        if not query_vec:
            return []

        kwargs: dict[str, Any] = {
            "query_embeddings": [query_vec],
            "n_results": min(top_k, max(coll.count(), 1)),
            "include": ["documents", "metadatas", "distances"],
        }
        if filters:
            kwargs["where"] = filters

        results = coll.query(**kwargs)
        output: list[Document] = []
        if not results or not results.get("ids") or not results["ids"][0]:
            return output

        for doc_id, doc_text, meta, dist in zip(
            results["ids"][0],
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            # ChromaDB cosine distance: 0 = identical, 2 = opposite
            similarity = round((1 - dist / 2) * 100, 1)
            meta_copy = dict(meta)
            meta_copy["score"] = similarity
            output.append(
                Document(
                    id=doc_id,
                    text=doc_text,
                    metadata=meta_copy,
                    score=similarity,
                )
            )

        return sorted(output, key=lambda d: d.score or 0.0, reverse=True)

    def delete(self, namespace: str, ids: list[str] | None = None) -> None:
        """Delete specific document IDs or entire collection."""
        target_name = self._make_collection_name(namespace)
        try:
            if ids:
                coll = self._client.get_collection(target_name)
                coll.delete(ids=ids)
            else:
                self._client.delete_collection(target_name)
                if target_name == self.collection_name:
                    self._init_chroma()
        except Exception as e:
            print(f"    [CHROMA] Delete warning: {e}")

    # ─────────────────────────────────────────────
    # Legacy helper methods for backwards compatibility
    # ─────────────────────────────────────────────

    def upsert_chunks(self, chunks: list[dict], show_progress: bool = True) -> int:
        """Legacy helper for existing pipeline code."""
        if not chunks:
            return 0
        valid = [c for c in chunks if c.get("text", "").strip()]
        if not valid:
            return 0

        docs = []
        for i, c in enumerate(valid):
            doc_id = f"{self.collection_name}_{uuid.uuid4().hex[:12]}"
            meta = {
                "company": str(c.get("company", self.company_name)),
                "source": str(c.get("source", "")),
                "title": str(c.get("title", ""))[:200],
                "url": str(c.get("url", ""))[:500],
                "page_number": int(c.get("page_number", 0)),
                "chunk_index": int(c.get("chunk_index", i)),
                "strategy": str(c.get("strategy", "")),
                "token_count": int(c.get("token_count", 0)),
                "topics": str(c.get("topics", "")),
                "source_date": str(c.get("source_date", "")),
                "ingested_at": str(c.get("ingested_at", "")),
            }
            docs.append(Document(id=doc_id, text=c["text"], metadata=meta))

        self.add_documents(docs, namespace=self.company_name)
        count = len(docs)
        print(f"    [CHROMA] ✓ Stored {count} chunks | Collection total: {self._collection.count()}")
        return count

    def info(self) -> dict:
        """Return collection stats."""
        count = self._collection.count() if self._collection else 0
        return {
            "collection": self.collection_name,
            "company": self.company_name,
            "total_vectors": count,
            "embedder": self.embedder.provider,
            "dimensions": self.embedder.dimensions,
            "storage_path": settings.CHROMA_DIR,
            "hnsw_m": self.hnsw_m,
            "hnsw_construction_ef": self.hnsw_construction_ef,
            "hnsw_search_ef": self.hnsw_search_ef,
        }

    def delete_collection(self) -> None:
        """Permanently delete collection."""
        self.delete(self.company_name)

    def reset_collection(self) -> None:
        """Reset collection to empty."""
        self.delete(self.company_name)
        self._init_chroma()

    @staticmethod
    def list_all_collections() -> list[str]:
        """List all collections."""
        try:
            client = chromadb.PersistentClient(path=settings.CHROMA_DIR)
            return [c.name for c in client.list_collections()]
        except Exception:
            return []


# Alias VectorStore to ChromaVectorStore for backwards compatibility
VectorStore = ChromaVectorStore
