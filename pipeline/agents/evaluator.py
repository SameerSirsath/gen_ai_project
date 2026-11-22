"""
pipeline/agents/evaluator.py — Evaluator Agent (Hallucination Gate).
Cross-references claims against verified context to prevent hallucinations.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from pipeline.schemas import WriterOutput, EvaluationResult
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


def evaluate_email(
    writer_output: WriterOutput,
    context: str,
    llm_client: Optional[Any] = None,
) -> EvaluationResult:
    """
    Evaluates factual claims in email against verified context.

    Args:
        writer_output: WriterOutput from the Writer Agent.
        context: Raw RAG context text.
        llm_client: Client instance with a generate() method. Defaults to OllamaClient.

    Returns:
        Parsed EvaluationResult object.
    """
    if llm_client is None:
        llm_client = OllamaClient()

    schema_dict = EvaluationResult.model_json_schema()
    schema_str = json.dumps(schema_dict, indent=2)

    prompt = (
        f"You are a strict fact-checker.\n"
        f"Here are the claims made in an email: {writer_output.claims_used}.\n"
        f"Here is the verified context: {context}.\n"
        f"Does the context explicitly support EVERY claim? "
        f"If any claim is unsupported or contradicted, set is_grounded to False and list the bad claims in flagged_claims. "
        f"Return ONLY JSON matching the EvaluationResult schema.\n\n"
        f"Schema:\n{schema_str}\n\n"
        f"JSON Output:"
    )

    system_prompt = (
        "You are a rigorous, zero-tolerance fact-checker for enterprise sales communications. "
        "Strictly evaluate claims against the provided context. "
        "Always respond with valid JSON matching the schema."
    )

    response_text = llm_client.generate(
        prompt=prompt,
        system_prompt=system_prompt,
        json_schema=schema_dict,
    )

    try:
        data = _extract_json(response_text)
        return EvaluationResult.model_validate(data)
    except Exception as e:
        # If extraction failed, perform simple string containment sanity check
        unsupported = [
            claim for claim in writer_output.claims_used
            if claim.lower() not in context.lower()
        ]
        is_grounded = len(unsupported) == 0
        return EvaluationResult(
            is_grounded=is_grounded,
            flagged_claims=unsupported,
            reasoning="Automated context verification based on factual consistency." if is_grounded else f"Claims not explicitly found in context: {unsupported}",
        )
