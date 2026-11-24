"""
app/services/llm_adapter.py — Adapter wrapping the Multi-Key LLM Router for Agents.
"""

from __future__ import annotations

from app.services.llm_router import call_llm


class RouterLLMClient:
    """
    Drop-in replacement for OllamaClient across researcher, writer, and evaluator agents.
    Routes queries dynamically across active Gemini and Groq API keys with automatic failover
    and generous token limits for formal, full-length emails.
    """

    def generate(self, prompt: str, system_prompt: str = "", json_schema: dict = None, max_tokens: int = 1800, **kwargs) -> str:
        # The router handles the Gemini->Groq fallback internally.
        return call_llm(prompt=prompt, system=system_prompt, max_tokens=max_tokens)
