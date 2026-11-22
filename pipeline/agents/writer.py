"""
pipeline/agents/writer.py — Writer Agent.
Drafts concise, anti-template cold emails using research signals.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from pipeline.schemas import ResearchSignals, WriterOutput
from pipeline.llm.ollama_client import OllamaClient


def _extract_json(raw_text: str) -> dict:
    """Safely extracts JSON dictionary from LLM response text."""
    text = raw_text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    match = re.search(r"(\{.*\})", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse valid JSON from response: {raw_text[:200]}")


def draft_email(
    research: ResearchSignals,
    context: str,
    llm_client: Optional[Any] = None,
    company_context: Optional[str] = None,
) -> WriterOutput:
    """
    Drafts a personalized cold email grounded in research signals and context.

    Args:
        research: ResearchSignals extracted by the Researcher Agent.
        context: Raw RAG context text about prospect.
        llm_client: Client instance with a generate() method. Defaults to OllamaClient.
        company_context: Optional context regarding our own company value prop/services.

    Returns:
        Parsed WriterOutput object.
    """
    if llm_client is None:
        llm_client = OllamaClient()

    primary_news = research.recent_news[0] if research.recent_news else "recent company developments"
    primary_pain_point = research.pain_points[0] if research.pain_points else "scaling operational efficiency"

    schema_dict = WriterOutput.model_json_schema()
    schema_str = json.dumps(schema_dict, indent=2)

    company_instruction = ""
    if company_context and company_context.strip():
        company_instruction = (
            f"\nOur Company Value Proposition & Services:\n{company_context.strip()}\n"
            f"- In Sentence 2, connect our capability directly to solving their pain point ({primary_pain_point}).\n"
        )

    prompt = (
        f"You are a top-performing SDR. Write a cold email.\n"
        f"- Sentence 1 MUST reference this recent news: {research.recent_news}.\n"
        f"- Sentence 2 MUST address this pain point: {primary_pain_point}.\n"
        f"{company_instruction}"
        f"- Sentence 3 must be a soft call-to-action.\n"
        f"Do not use generic corporate jargon. Keep it under 75 words. "
        f"Extract the factual claims you used. Return ONLY JSON matching the WriterOutput schema.\n\n"
        f"Schema:\n{schema_str}\n\n"
        f"Verified Context:\n{context}\n\n"
        f"JSON Output:"
    )

    system_prompt = (
        "You are a top-performing sales development representative. "
        "Draft concise 3-sentence cold emails with exact factual grounding. "
        "Always respond with strictly valid JSON matching the schema."
    )

    response_text = llm_client.generate(
        prompt=prompt,
        system_prompt=system_prompt,
        json_schema=schema_dict,
    )

    try:
        data = _extract_json(response_text)
        return WriterOutput.model_validate(data)
    except Exception:
        # Fallback in case of parsing anomaly
        s1 = f"I saw that {primary_news}."
        s2 = f"We help leaders solve {primary_pain_point} without disrupting existing workflows."
        s3 = "Would you be open to a 10-minute chat this Thursday to explore this?"
        body = f"{s1} {s2} {s3}"
        return WriterOutput(
            subject=f"Idea regarding {primary_news[:30]}",
            body=body,
            claims_used=[primary_news, primary_pain_point],
        )
