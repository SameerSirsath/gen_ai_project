"""
pipeline/llm/base.py — Core Protocols for LLM & Embedding Adapters.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    """
    Protocol for text & structured JSON generation across LLM backends.
    """

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        json_schema: dict[str, Any] | type | None = None,
    ) -> str | dict[str, Any]:
        """
        Generate response from model.

        Args:
            prompt: User prompt content.
            system: Optional system instruction.
            json_schema: Optional JSON schema dictionary or Pydantic model for structured outputs.

        Returns:
            String response if json_schema is None; parsed dictionary if json_schema is provided.
        """
        ...


@runtime_checkable
class EmbeddingClient(Protocol):
    """
    Protocol for generating dense vector embeddings across backends.
    """

    @property
    def dimensions(self) -> int:
        """Embedding vector dimension."""
        ...

    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for a list of texts.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of float vectors.
        """
        ...

    def embed_one(self, text: str) -> list[float]:
        """
        Generate embedding for a single text string.
        """
        ...
