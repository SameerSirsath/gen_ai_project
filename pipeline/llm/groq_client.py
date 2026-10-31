"""
groq_client.py — Groq LLaMA 3.1 LLM Client Adapter.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from config import settings
from .base import LLMClient


class GroqLLMClient:
    """
    Adapter for Groq LLaMA 3.1 chat completions implementing LLMClient Protocol.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        key = api_key or settings.GROQ_API_KEY
        if not key:
            raise ValueError("GROQ_API_KEY is required for Groq backend.")
        from groq import Groq
        self._client = Groq(api_key=key)
        self.model_name = model or settings.GROQ_MODEL or "llama-3.1-70b-versatile"

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        json_schema: dict[str, Any] | type | None = None,
    ) -> str | dict[str, Any]:
        """Generate text or JSON via Groq LLaMA 3.1."""
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
                clean = content.strip()
                if clean.startswith("```json"):
                    clean = clean[7:]
                if clean.startswith("```"):
                    clean = clean[3:]
                if clean.endswith("```"):
                    clean = clean[:-3]
                return json.loads(clean.strip())
            except Exception:
                return {"raw_text": content}

        return content
