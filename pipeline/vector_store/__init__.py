"""
pipeline/vector_store — Pluggable vector store layer supporting ChromaDB and Pinecone.
"""

from .base import Document, VectorStore
from .chroma_client import ChromaVectorStore
from .pinecone_adapter import PineconeVectorStore
from .embedder import Embedder
from .factory import get_vector_store

__all__ = [
    "Document",
    "VectorStore",
    "ChromaVectorStore",
    "PineconeVectorStore",
    "Embedder",
    "get_vector_store",
]
