"""
pipeline/agents/writer.py — Writer Agent.
Drafts concise, anti-template cold emails using research signals.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from pipeline.schemas import ResearchSignals, WriterOutput
from app.services.llm_adapter import RouterLLMClient


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
        llm_client = RouterLLMClient()

    primary_news = research.recent_news[0] if research.recent_news else "recent company developments"
    primary_pain_point = research.pain_points[0] if research.pain_points else "scaling operational efficiency"

    schema_dict = WriterOutput.model_json_schema()
    schema_str = json.dumps(schema_dict, indent=2)

    company_instruction = ""
    if company_context and company_context.strip():
        company_instruction = (
            f"\nOur Company Value Proposition & Capabilities:\n{company_context.strip()}\n"
            f"- Connect our specific enterprise solution directly to resolving their core pain point ({primary_pain_point}).\n"
        )

    prompt = (
        f"You are an enterprise SDR writing an end-to-end, high-converting, professional, formal sales outreach email.\n\n"
        f"Target Prospect Context & Signals:\n"
        f"- Recent News / Milestones: {research.recent_news}\n"
        f"- Primary Pain Point: {primary_pain_point}\n"
        f"- Context: {context}\n"
        f"{company_instruction}\n"
        f"Draft a complete, end-to-end formal B2B email with the following clear structure:\n"
        f"1. Formal Salutation: (e.g. 'Dear [Contact Name],' or 'Dear [Company] Leadership Team,')\n"
        f"2. Contextual Opening: Acknowledge their recent milestone, corporate expansion, or industry focus ({primary_news}).\n"
        f"3. Value Proposition: Articulate how our solution eliminates operational bottlenecks and directly solves {primary_pain_point}.\n"
        f"4. Concrete Impact: Provide a clear value proposition or metric (e.g. accelerating outbound efficiency, reducing manual overhead).\n"
        f"5. Professional Call to Action (CTA): Politely propose a brief 10-minute introductory conversation next week.\n"
        f"6. Formal Sign-off: 'Best regards,\\n[Your Name]\\nBizCorp AI Sales Outreach Team'\n\n"
        f"Extract the specific factual claims used into the 'claims_used' array.\n"
        f"Return ONLY strictly valid JSON matching the WriterOutput schema.\n\n"
        f"Schema:\n{schema_str}\n\n"
        f"JSON Output:"
    )

    system_prompt = (
        "You are an executive enterprise sales professional. "
        "Draft complete, polished, formal B2B sales emails grounded strictly in verified context facts. "
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
        body = (
            f"Dear Leadership Team,\n\n"
            f"I have been following your team's strategic trajectory and noted that {primary_news}.\n\n"
            f"Many fast-growing enterprise organizations face challenges when trying to solve {primary_pain_point} "
            f"while scaling operations. Our automated AI intelligence platform is purpose-built to streamline research, "
            f"eliminate manual overhead, and accelerate high-converting outbound pipelines.\n\n"
            f"Would you be open to a brief 10-minute introductory conversation this Thursday to explore how this can support your growth targets?\n\n"
            f"Best regards,\n"
            f"Enterprise Outreach Team\n"
            f"BizCorp AI"
        )
        return WriterOutput(
            subject=f"Strategic Initiative: Addressing {primary_pain_point} at Scale",
            body=body,
            claims_used=[primary_news, primary_pain_point],
        )
