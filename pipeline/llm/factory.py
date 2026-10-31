"""
pipeline/llm/factory.py — Factory for instantiating LLM and Embedding clients.
"""

from __future__ import annotations

from typing import Optional
from config import settings

from .base import LLMClient, EmbeddingClient
from .gemini_client import GeminiLLMClient, GeminiEmbeddingClient
from .openai_client import OpenAILLMClient, OpenAIEmbeddingClient
from .groq_client import GroqLLMClient
from .onnx_client import ONNXLLMClient, ONNXEmbeddingClient


def get_llm(backend: Optional[str] = None) -> LLMClient:
    """
    Instantiate and return the configured LLM client.

    Args:
        backend: "gemini", "openai", "groq", or "onnx" (defaults to settings.LLM_BACKEND).
    """
    chosen = (backend or settings.LLM_BACKEND).lower()

    if chosen == "gemini":
        return GeminiLLMClient()
    elif chosen == "openai":
        return OpenAILLMClient()
    elif chosen == "groq":
        return GroqLLMClient()
    elif chosen == "onnx":
        return ONNXLLMClient()
    else:
        raise ValueError(
            f"Unsupported LLM backend: '{chosen}'. Supported options: 'gemini', 'openai', 'groq', 'onnx'."
        )


def get_embedder(backend: Optional[str] = None) -> EmbeddingClient:
    """
    Instantiate and return the configured Embedding client.

    Args:
        backend: "gemini", "openai", or "local" (defaults to settings.EMBEDDING_BACKEND).
    """
    chosen = (backend or settings.EMBEDDING_BACKEND).lower()

    if chosen == "gemini":
        return GeminiEmbeddingClient()
    elif chosen == "openai":
        return OpenAIEmbeddingClient()
    elif chosen in ("local", "onnx"):
        return ONNXEmbeddingClient()
    else:
        raise ValueError(
            f"Unsupported embedding backend: '{chosen}'. Supported options: 'gemini', 'openai', 'local'."
        )
