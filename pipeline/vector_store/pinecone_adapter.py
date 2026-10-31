"""
pinecone_adapter.py — Cloud Pinecone Vector Store Adapter.

Implements VectorStore Protocol using pinecone-client v3+ with ServerlessSpec.
Upserts in batches of 100 and routes namespace directly to Pinecone namespaces.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from config import settings

from .base import Document, VectorStore as VectorStoreProtocol
from .embedder import Embedder


class PineconeVectorStore:
    """
    Pinecone cloud-backed vector store implementing VectorStore Protocol.
    Uses ServerlessSpec index configuration and batch-upserting.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        index_name: Optional[str] = None,
        embedder: Optional[Embedder] = None,
    ):
        """
        Initialize Pinecone vector store adapter.

        Args:
            api_key: Pinecone API key (defaults to settings.PINECONE_API_KEY).
            index_name: Pinecone index name (defaults to settings.PINECONE_INDEX_NAME).
            embedder: Embedder instance (defaults to central Embedder).
        """
        self.api_key = api_key or settings.PINECONE_API_KEY
        if not self.api_key:
            raise ValueError(
                "[PINECONE ERROR] Missing PINECONE_API_KEY. "
                "Provide an API key or configure PINECONE_API_KEY in environment."
            )

        self.index_name = index_name or settings.PINECONE_INDEX_NAME
        self.embedder = embedder or Embedder()
        self.dimension = settings.EMBEDDING_DIM or self.embedder.dimensions or 3072

        self._pc = None
        self._index = None
        self._init_pinecone()

    def _init_pinecone(self) -> None:
        """Connect to Pinecone client and ensure the serverless index exists."""
        try:
            from pinecone import Pinecone, ServerlessSpec
        except ImportError as exc:
            raise ImportError(
                "pinecone-client is required for Pinecone backend. "
                "Install it with 'pip install pinecone-client'."
            ) from exc

        self._pc = Pinecone(api_key=self.api_key)

        existing = [idx["name"] for idx in self._pc.list_indexes()]
        if self.index_name not in existing:
            region = settings.PINECONE_REGION or settings.PINECONE_ENV or "us-east-1"
            cloud = settings.PINECONE_CLOUD or "aws"
            print(f"    [PINECONE] Creating serverless index '{self.index_name}' ({cloud}:{region}, {self.dimension}d)...")
            self._pc.create_index(
                name=self.index_name,
                dimension=self.dimension,
                metric="cosine",
                spec=ServerlessSpec(cloud=cloud, region=region),
            )

        self._index = self._pc.Index(self.index_name)

    # ─────────────────────────────────────────────
    # VectorStore Protocol Implementation
    # ─────────────────────────────────────────────

    def add_documents(self, docs: list[Document], namespace: str) -> None:
        """
        Upsert documents into Pinecone under the given namespace in batches of 100.
        """
        if not docs:
            return

        texts_to_embed = [d.text for d in docs if d.embedding is None]
        new_vecs = self.embedder.embed(texts_to_embed) if texts_to_embed else []
        vec_iter = iter(new_vecs)

        vectors: list[dict[str, Any]] = []
        for d in docs:
            doc_id = d.id or f"pine_{uuid.uuid4().hex[:12]}"
            emb = d.embedding if d.embedding is not None else next(vec_iter)

            # Metadata must fit Pinecone constraints: flat dict of str/int/float/bool/list[str]
            cleaned_meta: dict[str, Any] = {"text": d.text}
            for k, v in d.metadata.items():
                if isinstance(v, (str, int, float, bool)):
                    cleaned_meta[k] = v
                elif isinstance(v, list) and all(isinstance(x, str) for x in v):
                    cleaned_meta[k] = v
                else:
                    cleaned_meta[k] = str(v)

            vectors.append({"id": doc_id, "values": emb, "metadata": cleaned_meta})

        # Batch upsert in groups of 100
        batch_size = 100
        for i in range(0, len(vectors), batch_size):
            batch = vectors[i : i + batch_size]
            self._index.upsert(vectors=batch, namespace=namespace)

    def query(
        self,
        text: str,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
        namespace: str | None = None,
    ) -> list[Document]:
        """
        Query Pinecone by embedding the text and querying the target namespace.
        """
        if not text.strip():
            return []

        query_vec = self.embedder.embed_one(text)
        if not query_vec:
            return []

        ns = namespace or "default"
        kwargs: dict[str, Any] = {
            "vector": query_vec,
            "top_k": top_k,
            "include_metadata": True,
            "namespace": ns,
        }
        if filters:
            kwargs["filter"] = filters

        res = self._index.query(**kwargs)
        documents: list[Document] = []
        for match in res.get("matches", []):
            meta = match.get("metadata", {})
            doc_text = meta.pop("text", "")
            score = float(match.get("score", 0.0))
            # Convert cosine score 0.0-1.0 to percentage 0-100
            pct_score = round(score * 100, 1)
            meta["score"] = pct_score
            documents.append(
                Document(
                    id=match["id"],
                    text=doc_text,
                    metadata=meta,
                    score=pct_score,
                )
            )

        return sorted(documents, key=lambda d: d.score or 0.0, reverse=True)

    def delete(self, namespace: str, ids: list[str] | None = None) -> None:
        """
        Delete specified vector IDs or drop all records in the namespace.
        """
        try:
            if ids:
                self._index.delete(ids=ids, namespace=namespace)
            else:
                self._index.delete(delete_all=True, namespace=namespace)
        except Exception as e:
            print(f"    [PINECONE] Delete warning: {e}")
