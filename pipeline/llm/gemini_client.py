"""
gemini_client.py — Google Gemini LLM and Embedding Client Adapter.
"""

from __future__ import annotations

import json
import warnings
from typing import Any, Optional

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

import google.generativeai as genai
from config import settings
from .base import LLMClient, EmbeddingClient


class GeminiLLMClient:
    """
    Adapter for Google Gemini generative models implementing LLMClient Protocol.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        key = api_key or settings.GEMINI_API_KEY or settings.GOOGLE_API_KEY
        if not key:
            raise ValueError("GOOGLE_API_KEY or GEMINI_API_KEY required for Gemini backend.")
        genai.configure(api_key=key)
        self.model_name = model or settings.GEMINI_MODEL

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        json_schema: dict[str, Any] | type | None = None,
    ) -> str | dict[str, Any]:
        """Generate text or structured JSON with Gemini."""
        config: dict[str, Any] = {}
        if json_schema is not None:
            config["response_mime_type"] = "application/json"
            if isinstance(json_schema, dict):
                config["response_schema"] = json_schema
            elif hasattr(json_schema, "model_json_schema"):
                config["response_schema"] = json_schema

        model = genai.GenerativeModel(
            model_name=self.model_name,
            system_instruction=system if system else None,
            generation_config=config if config else None,
        )

        resp = model.generate_content(prompt)
        text = resp.text if hasattr(resp, "text") and resp.text else ""

        if json_schema is not None:
            try:
                # Strip markdown code fences if present
                clean = text.strip()
                if clean.startswith("```json"):
                    clean = clean[7:]
                if clean.startswith("```"):
                    clean = clean[3:]
                if clean.endswith("```"):
                    clean = clean[:-3]
                return json.loads(clean.strip())
            except Exception:
                return {"raw_text": text}

        return text


class GeminiEmbeddingClient:
    """
    Adapter for Google Gemini text embedding models implementing EmbeddingClient Protocol.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        key = api_key or settings.GEMINI_API_KEY or settings.GOOGLE_API_KEY
        if not key:
            raise ValueError("GOOGLE_API_KEY or GEMINI_API_KEY required for Gemini embeddings.")
        genai.configure(api_key=key)
        self.model_name = model or settings.EMBEDDING_MODEL_GOOGLE
        self._dimensions = settings.EMBEDDING_DIM or 3072

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors: list[list[float]] = []
        for t in texts:
            try:
                res = genai.embed_content(
                    model=self.model_name,
                    content=t,
                    task_type="retrieval_document",
                )
                vectors.append(res["embedding"])
            except Exception as e:
                print(f"    [GEMINI EMBED ERROR] {e}")
                vectors.append([0.0] * self.dimensions)
        return vectors

    def embed_one(self, text: str) -> list[float]:
        res = self.embed([text])
        return res[0] if res else [0.0] * self.dimensions
