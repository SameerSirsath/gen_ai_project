"""
pipeline/orchestrator.py — Multi-Agent Pipeline Orchestrator.
Coordinates Researcher, Writer, and Evaluator agents with ChromaDB retrieval and local Ollama inference.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from pipeline.schemas import ResearchSignals, WriterOutput, EvaluationResult
from pipeline.agents.langgraph_workflow import run_langgraph_pipeline


OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"
DISPATCH_FILE = OUTPUT_DIR / "dispatched_emails.json"


def query_chromadb_context(prospect_name: str, top_k: int = 5) -> str:
    """
    Retrieves top_k context chunks from ChromaDB for the given prospect.
    """
    try:
        from pipeline.vector_store import get_vector_store
        vs = get_vector_store(namespace=prospect_name)
        results = vs.query(text=f"{prospect_name} company overview news pain points", top_k=top_k)
        if results:
            texts = [getattr(r, "text", getattr(r, "page_content", str(r))) for r in results]
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


def run_agent_pipeline(
    prospect_name: str,
    context: str,
    company_context: Optional[str] = None
) -> dict:
    """
    Runs the multi-agent sales outreach pipeline via LangGraph:
    1. Researcher Agent -> extracts signals (pain points, news)
    2. Writer Agent     -> drafts concise 3-sentence cold email pitching our solution
    3. Evaluator Agent  -> strict hallucination gate check
    4. Reflection loop  -> auto-corrects ungrounded drafts
    """
    try:
        # Step 1: Fetch our company profile context if not explicitly provided
        if not company_context:
            try:
                from app.services.vector_service import search_company_profile
                company_context = search_company_profile(f"{prospect_name} sales outreach solutions")
            except Exception:
                company_context = ""

        # Step 2: Run LangGraph Workflow
        result = run_langgraph_pipeline(
            prospect_name=prospect_name,
            context=context,
            company_context=company_context
        )

        draft = result.get("draft") or {}
        evaluation = result.get("evaluation") or {}
        approved = result.get("approved", False)

        if approved and draft:
            try:
                from pipeline.schemas import WriterOutput, EvaluationResult
                w_out = WriterOutput.model_validate(draft)
                e_out = EvaluationResult.model_validate(evaluation)
                _save_dispatched_email(prospect_name, w_out, e_out)
            except Exception:
                pass

        return {
            "success": True,
            "approved": approved,
            "status": "PASSED" if approved else "BLOCKED",
            "subject": draft.get("subject", ""),
            "body": draft.get("body", ""),
            "claims_used": draft.get("claims_used", []),
            "signals": result.get("signals", {}),
            "draft": draft,
            "evaluation": evaluation,
            "reasoning": result.get("reasoning", ""),
            "flagged_claims": result.get("flagged_claims", []),
            "workflow_engine": "LangGraph",
            "revision_count": result.get("revision_count", 0),
            "logs": result.get("logs", []),
        }

    except Exception as e:
        print(f"[Orchestrator] Error during pipeline execution: {e}")
        return {
            "success": False,
            "approved": False,
            "error": str(e),
            "workflow_engine": "LangGraph",
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
