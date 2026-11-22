"""
pipeline/orchestrator.py — Multi-Agent Pipeline Orchestrator.
Coordinates Researcher, Writer, and Evaluator agents with ChromaDB retrieval and local Ollama inference.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from pipeline.llm.ollama_client import OllamaClient
from pipeline.schemas import ResearchSignals, WriterOutput, EvaluationResult
from pipeline.agents.researcher import extract_signals
from pipeline.agents.writer import draft_email
from pipeline.agents.evaluator import evaluate_email


OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"
DISPATCH_FILE = OUTPUT_DIR / "dispatched_emails.json"


def query_chromadb_context(prospect_name: str, top_k: int = 5) -> str:
    """
    Retrieves top_k context chunks from ChromaDB for the given prospect.
    """
    try:
        from pipeline.vector_store import get_vector_store
        vs = get_vector_store(namespace=prospect_name)
        results = vs.query(query_text=f"{prospect_name} company overview news pain points", top_k=top_k)
        if results:
            texts = [r.get("text", "") for r in results if r.get("text")]
            return "\n\n".join(texts)
    except Exception as e:
        # If vector store query fails or namespace doesn't exist, log and continue
        pass
    return ""


def _save_dispatched_email(prospect_name: str, writer_output: WriterOutput, evaluation: EvaluationResult) -> None:
    """Saves approved outreach email to dispatched_emails.json."""
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        records = []
        if DISPATCH_FILE.exists():
            try:
                with open(DISPATCH_FILE, "r", encoding="utf-8") as f:
                    records = json.load(f)
            except Exception:
                records = []

        records.append({
            "prospect_name": prospect_name,
            "subject": writer_output.subject,
            "body": writer_output.body,
            "claims_used": writer_output.claims_used,
            "evaluator_reasoning": evaluation.reasoning,
        })

        with open(DISPATCH_FILE, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[Orchestrator] Warning: could not save dispatch record: {e}")


def run_agent_pipeline(prospect_name: str, context: str) -> dict:
    """
    Runs the multi-agent sales outreach pipeline:
    1. Researcher Agent -> extracts signals (pain points, news)
    2. Writer Agent     -> drafts concise 3-sentence cold email
    3. Evaluator Agent  -> strict hallucination gate check
    """
    try:
        # Step 1: Initialize Local LLM Client
        llm = OllamaClient()

        # Step 2: Researcher Agent
        signals: ResearchSignals = extract_signals(prospect_name, context, llm_client=llm)
        print(f"[Researcher] Found signals: {signals.model_dump_json()}")

        # Step 3: Writer Agent
        draft: WriterOutput = draft_email(signals, context, llm_client=llm)
        print(f"[Writer] Drafted email: {draft.model_dump_json()}")

        # Step 4: Evaluator Agent
        eval_result: EvaluationResult = evaluate_email(draft, context, llm_client=llm)
        print(f"[Evaluator] Fact-check status: is_grounded={eval_result.is_grounded}")

        # Step 5: Hallucination Gate Decision
        if not eval_result.is_grounded:
            print(f"🚨 HALLUCINATION BLOCKED: {eval_result.reasoning}")
            return {
                "success": False,
                "approved": False,
                "signals": signals.model_dump(),
                "draft": draft.model_dump(),
                "evaluation": eval_result.model_dump(),
                "reasoning": eval_result.reasoning,
                "flagged_claims": eval_result.flagged_claims,
            }

        print("✅ EMAIL APPROVED")
        _save_dispatched_email(prospect_name, draft, eval_result)

        return {
            "success": True,
            "approved": True,
            "signals": signals.model_dump(),
            "draft": draft.model_dump(),
            "evaluation": eval_result.model_dump(),
            "email": {
                "subject": draft.subject,
                "body": draft.body,
                "claims_used": draft.claims_used,
            },
        }

    except Exception as e:
        print(f"[Orchestrator] Error during pipeline execution: {e}")
        return {
            "success": False,
            "approved": False,
            "error": str(e),
        }


def run_outreach_pipeline(prospect_name: str, prospect_info: str = "") -> dict:
    """
    Convenience wrapper that retrieves ChromaDB context if not provided,
    then executes run_agent_pipeline.
    """
    context = prospect_info
    if not context.strip():
        print(f"[Orchestrator] Querying ChromaDB context for '{prospect_name}'...")
        context = query_chromadb_context(prospect_name)
        if not context.strip():
            context = f"{prospect_name} company overview, market position, and recent product launches."

    return run_agent_pipeline(prospect_name, context)
