"""
pipeline/llm/ollama_client.py — Local LLM Client via Ollama.
Connects to http://localhost:11434/api/generate.
"""

from __future__ import annotations

import os
import json
from typing import Any, Optional
import requests


class OllamaClient:
    """
    Ollama LLM client for local offline inference.
    """

    def __init__(
        self,
        host: str = "http://localhost:11434",
        model: Optional[str] = None,
        timeout: int = 120,
    ):
        self.host = host.rstrip("/")
        # Default to llama3.2:latest, fallback to llama3:latest or env var
        self.model = model or os.getenv("OLLAMA_MODEL", "llama3.2:latest")
        self.timeout = timeout
        self.url = f"{self.host}/api/generate"

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        json_schema: Optional[dict[str, Any]] = None,
        system: Optional[str] = None,
    ) -> str:
        """
        Generate response from local Ollama model.

        Args:
            prompt: User prompt content.
            system_prompt: Optional system instruction.
            json_schema: Optional JSON schema dictionary. Forces format="json" if provided.
            system: Alias for system_prompt.

        Returns:
            Raw response text from Ollama.
        """
        effective_system = system if system is not None else system_prompt

        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }

        if effective_system:
            payload["system"] = effective_system

        if json_schema is not None:
            # Force format="json" in the Ollama API payload
            payload["format"] = "json"

        try:
            response = requests.post(self.url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Ollama API request failed at {self.url}: {e}") from e
