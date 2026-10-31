"""
openai_client.py — OpenAI LLM and Embedding Client Adapter.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from config import settings
from .base import LLMClient, EmbeddingClient


class OpenAILLMClient:
    """
    Adapter for OpenAI chat completions implementing LLMClient Protocol.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        key = api_key or settings.OPENAI_API_KEY
        if not key:
            raise ValueError("OPENAI_API_KEY is required for OpenAI backend.")
        from openai import OpenAI
        self._client = OpenAI(api_key=key)
        self.model_name = model or settings.OPENAI_MODEL

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        json_schema: dict[str, Any] | type | None = None,
    ) -> str | dict[str, Any]:
        """Generate text or JSON using OpenAI."""
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        kwargs: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
        }
        if json_schema is not None:
            kwargs["response_format"] = {"type": "json_object"}

        res = self._client.chat.completions.create(**kwargs)
        content = res.choices[0].message.content or ""

        if json_schema is not None:
            try:
                return json.loads(content)
            except Exception:
                return {"raw_text": content}

        return content


class OpenAIEmbeddingClient:
    """
    Adapter for OpenAI text embeddings implementing EmbeddingClient Protocol.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        key = api_key or settings.OPENAI_API_KEY
        if not key:
            raise ValueError("OPENAI_API_KEY is required for OpenAI embeddings.")
        from openai import OpenAI
        self._client = OpenAI(api_key=key)
        self.model_name = model or settings.EMBEDDING_MODEL_OPENAI
        self._dimensions = 1536

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors: list[list[float]] = []
        batch_size = settings.EMBEDDING_BATCH_SIZE
        for i in range(0, len(texts), batch_size):
            batch = [t[:32000] for t in texts[i : i + batch_size]]
            try:
                resp = self._client.embeddings.create(
                    model=self.model_name,
                    input=batch,
                )
                vectors.extend([item.embedding for item in resp.data])
            except Exception as e:
                print(f"    [OPENAI EMBED ERROR] {e}")
                vectors.extend([[0.0] * self.dimensions] * len(batch))
        return vectors

    def embed_one(self, text: str) -> list[float]:
        res = self.embed([text])
        return res[0] if res else [0.0] * self.dimensions
