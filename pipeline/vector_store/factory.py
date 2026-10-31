"""
pipeline/vector_store/factory.py — Factory for instantiating VectorStore adapters.
"""

from __future__ import annotations

from typing import Optional
from config import settings
from .base import VectorStore
from .chroma_client import ChromaVectorStore
from .pinecone_adapter import PineconeVectorStore


def get_vector_store(
    backend: Optional[str] = None,
    namespace: str = "default",
    embedder=None,
) -> VectorStore:
    """
    Instantiate and return the configured VectorStore backend.

    Args:
        backend: "chroma" or "pinecone" (defaults to settings.VECTOR_BACKEND).
        namespace: Default collection or namespace name.
        embedder: Optional custom embedder instance.
    """
    chosen = (backend or settings.VECTOR_BACKEND).lower()

    if chosen == "chroma":
        return ChromaVectorStore(company_name=namespace, embedder=embedder)
    elif chosen == "pinecone":
        return PineconeVectorStore(embedder=embedder)
    else:
        raise ValueError(
            f"Unsupported vector backend: '{chosen}'. Supported options: 'chroma', 'pinecone'."
        )
