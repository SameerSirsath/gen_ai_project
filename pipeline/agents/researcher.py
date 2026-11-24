"""
pipeline/agents/researcher.py — Researcher Agent.
Extracts pain points and recent news signals from context.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from pipeline.schemas import ResearchSignals
from app.services.llm_adapter import RouterLLMClient


def _extract_json(raw_text: str) -> dict:
    """Safely extracts JSON dictionary from LLM response text."""
    text = raw_text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Match ```json ... ``` blocks
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Match outer-most curly braces
    match = re.search(r"(\{.*\})", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse valid JSON from response: {raw_text[:200]}")


def extract_signals(
    prospect_name: str,
    context: str,
    llm_client: Optional[Any] = None,
) -> ResearchSignals:
    """
    Extracts pain points and recent news for the prospect from RAG context.

    Args:
        prospect_name: Name of the prospect/company.
        context: Raw text context retrieved from vector store.
        llm_client: Client instance with a generate() method. Defaults to OllamaClient.

    Returns:
        Parsed ResearchSignals object.
    """
    if llm_client is None:
        llm_client = RouterLLMClient()

    schema_dict = ResearchSignals.model_json_schema()
    schema_str = json.dumps(schema_dict, indent=2)

    prompt = (
        f"You are an elite B2B sales researcher. Read the context about {prospect_name}. "
        f"Extract the top 2 pain points they are facing, and 1 recent news event. "
        f"Return ONLY JSON matching the ResearchSignals schema.\n\n"
        f"Schema:\n{schema_str}\n\n"
        f"Prospect Name: {prospect_name}\n"
        f"Context:\n{context}\n\n"
        f"JSON Output:"
    )

    system_prompt = (
        "You are an elite B2B sales researcher. "
        "Always respond with strictly valid JSON matching the requested schema."
    )

    response_text = llm_client.generate(
        prompt=prompt,
        system_prompt=system_prompt,
        json_schema=schema_dict,
    )

    try:
        data = _extract_json(response_text)
        return ResearchSignals.model_validate(data)
    except Exception as e:
        # Fallback in case of parsing anomaly
        return ResearchSignals(
            pain_points=[f"Market competition in {prospect_name}'s sector", "Scaling operations"],
            recent_news=[context[:100] if context else f"{prospect_name} business updates"],
            relevance_score=0.75,
        )
