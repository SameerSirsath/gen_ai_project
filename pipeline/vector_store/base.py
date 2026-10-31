"""
pipeline/vector_store/base.py — Core VectorStore Protocol and Document Model.

Defines the contract for vector storage engines (ChromaDB local, Pinecone cloud, etc.).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable
from pydantic import BaseModel, Field


class Document(BaseModel):
    """
    Standardized document payload across vector stores.
    """
    id: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    embedding: list[float] | None = None
    score: float | None = None

    def __getitem__(self, item: str) -> Any:
        """
        Dictionary-like attribute access for backwards compatibility
        with legacy dictionary chunk structures.
        """
        if hasattr(self, item):
            val = getattr(self, item)
            if val is not None:
                return val
        return self.metadata.get(item)

    def get(self, key: str, default: Any = None) -> Any:
        """Safe dict-like lookup."""
        if hasattr(self, key):
            val = getattr(self, key)
            return val if val is not None else default
        return self.metadata.get(key, default)


@runtime_checkable
class VectorStore(Protocol):
    """
    Protocol that any vector database adapter must implement.
    """

    def add_documents(self, docs: list[Document], namespace: str) -> None:
        """
        Add or upsert documents to a specific collection/namespace.

        Args:
            docs: List of Document models with text, metadata, and optional embeddings.
            namespace: Target namespace or collection name (e.g. company name).
        """
        ...

    def query(
        self,
        text: str,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
        namespace: str | None = None,
    ) -> list[Document]:
        """
        Query for the top_k most similar documents to the input text.

        Args:
            text: Query text string.
            top_k: Maximum number of candidate documents to retrieve.
            filters: Optional metadata filtering criteria.
            namespace: Target collection or namespace to search within.

        Returns:
            List of matching Document models sorted by relevance score descending.
        """
        ...

    def delete(self, namespace: str, ids: list[str] | None = None) -> None:
        """
        Delete documents by IDs, or drop the entire namespace if IDs is None.

        Args:
            namespace: Collection or namespace name.
            ids: Optional list of document IDs to delete. If None, clear the namespace.
        """
        ...
