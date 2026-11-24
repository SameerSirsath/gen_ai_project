"""
app/services/llm_adapter.py — Adapter wrapping the Multi-Key LLM Router for Agents.
"""

from __future__ import annotations

from app.services.llm_router import call_llm


class RouterLLMClient:
    """
    Drop-in replacement for OllamaClient across researcher, writer, and evaluator agents.
    Routes queries dynamically across active Groq and Gemini API keys with automatic failover.
    """

    def generate(self, prompt: str, system_prompt: str = "", json_schema: dict = None, **kwargs) -> str:
        # The router handles the Groq->Gemini fallback internally.
        # json_schema is ignored here because the agent prompts already force JSON.
        return call_llm(prompt=prompt, system=system_prompt)
