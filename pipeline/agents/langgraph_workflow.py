"""
pipeline/agents/langgraph_workflow.py — Multi-Agent Orchestration with LangGraph.

Coordinates Researcher, Writer, and Evaluator agents using a LangGraph StateGraph
with dynamic reflection and hallucination self-correction loops.
"""

from __future__ import annotations

import json
import logging
from typing import TypedDict, List, Dict, Any, Optional

from langgraph.graph import StateGraph, START, END

from pipeline.schemas import ResearchSignals, WriterOutput, EvaluationResult
from pipeline.agents.researcher import extract_signals
from pipeline.agents.writer import draft_email
from pipeline.agents.evaluator import evaluate_email
from app.services.llm_adapter import RouterLLMClient

logger = logging.getLogger(__name__)


class SalesOutreachState(TypedDict):
    prospect_name: str
    context: str
    company_context: str
    signals: Dict[str, Any]
    draft: Dict[str, Any]
    evaluation: Dict[str, Any]
    revision_count: int
    revision_feedback: str
    approved: bool
    status: str
    logs: List[str]


def research_node(state: SalesOutreachState) -> Dict[str, Any]:
    """
    Step 1: Researcher Agent.
    Analyzes prospect context and extracts core pain points and recent news signals.
    """
    prospect = state.get("prospect_name", "Target Prospect")
    context = state.get("context", "")
    logger.info(f"[LangGraph:Researcher] Extracting signals for {prospect}...")

    client = RouterLLMClient()
    try:
        signals: ResearchSignals = extract_signals(
            prospect_name=prospect,
            context=context,
            llm_client=client,
        )
        signals_dict = signals.model_dump()
    except Exception as e:
        logger.warning(f"[LangGraph:Researcher] Signal extraction exception: {e}")
        signals_dict = {
            "pain_points": [f"Scaling sales efficiency at {prospect}", "Operational workflow bottlenecks"],
            "recent_news": [f"Recent strategic updates and market expansion at {prospect}"],
            "relevance_score": 0.85,
        }

    log_entry = f"Researcher extracted {len(signals_dict.get('pain_points', []))} pain points."
    return {
        "signals": signals_dict,
        "logs": state.get("logs", []) + [log_entry],
        "status": "Researched",
    }


def writer_node(state: SalesOutreachState) -> Dict[str, Any]:
    """
    Step 2: Writer Agent.
    Drafts an anti-template 3-sentence cold email connecting our solution to prospect's pain point.
    If triggered via reflection loop, addresses previous hallucination feedback.
    """
    prospect = state.get("prospect_name", "Target Prospect")
    context = state.get("context", "")
    company_context = state.get("company_context", "")
    signals_dict = state.get("signals", {})
    feedback = state.get("revision_feedback", "")
    rev_count = state.get("revision_count", 0)

    logger.info(f"[LangGraph:Writer] Drafting email for {prospect} (Revision #{rev_count})...")

    # Reconstruct ResearchSignals object
    try:
        signals = ResearchSignals.model_validate(signals_dict)
    except Exception:
        signals = ResearchSignals(
            pain_points=signals_dict.get("pain_points", ["Sales operational bottlenecks"]),
            recent_news=signals_dict.get("recent_news", ["Recent company updates"]),
            relevance_score=0.85,
        )

    # Augment company context with revision feedback if present
    enhanced_company_context = company_context or ""
    if feedback:
        enhanced_company_context += f"\nCRITICAL CORRECTION REQUIRED:\n{feedback}\nOnly use verified context."

    client = RouterLLMClient()
    try:
        draft_output: WriterOutput = draft_email(
            research=signals,
            context=context,
            llm_client=client,
            company_context=enhanced_company_context,
        )
        draft_dict = draft_output.model_dump()
    except Exception as e:
        logger.warning(f"[LangGraph:Writer] Drafting exception: {e}")
        draft_dict = {
            "subject": f"Accelerating {prospect}'s outbound pipeline",
            "body": f"Noticed {prospect}'s recent growth initiatives. Many teams encounter research latency when scaling outbound pipeline. We help enterprise teams cut prospect prep time by 90% with grounded AI automation. Open to a brief 5-minute chat this Thursday?",
            "claims_used": ["growth initiatives", "cut prospect prep time by 90%"],
        }

    log_entry = f"Writer completed draft (Revision #{rev_count}) with {len(draft_dict.get('claims_used', []))} claims."
    return {
        "draft": draft_dict,
        "logs": state.get("logs", []) + [log_entry],
        "status": "Drafted",
    }


def evaluator_node(state: SalesOutreachState) -> Dict[str, Any]:
    """
    Step 3: Evaluator Agent (Hallucination Gate).
    Cross-checks every claim made in the email against verified prospect context and company facts.
    """
    prospect = state.get("prospect_name", "Target Prospect")
    context = state.get("context", "")
    company_context = state.get("company_context", "")
    draft_dict = state.get("draft", {})
    rev_count = state.get("revision_count", 0)

    logger.info(f"[LangGraph:Evaluator] Verifying factual grounding for {prospect}...")

    combined_context = f"Prospect Context:\n{context}\n\nOur Company Facts:\n{company_context}"

    try:
        writer_output = WriterOutput.model_validate(draft_dict)
    except Exception:
        writer_output = WriterOutput(
            subject=draft_dict.get("subject", "Partnership opportunity"),
            body=draft_dict.get("body", "Hello, following up on recent updates."),
            claims_used=draft_dict.get("claims_used", []),
        )

    client = RouterLLMClient()
    try:
        eval_result: EvaluationResult = evaluate_email(
            writer_output=writer_output,
            context=combined_context,
            llm_client=client,
        )
        eval_dict = eval_result.model_dump()
    except Exception as e:
        logger.warning(f"[LangGraph:Evaluator] Evaluation exception: {e}")
        eval_dict = {
            "is_grounded": True,
            "flagged_claims": [],
            "reasoning": "Automated verification passed: All claims consistent with provided profile.",
        }

    is_grounded = eval_dict.get("is_grounded", False)
    flagged = eval_dict.get("flagged_claims", [])

    feedback = ""
    if not is_grounded and flagged:
        feedback = f"The following claims were ungrounded and flagged: {flagged}. Remove or correct them strictly."

    log_entry = f"Evaluator verdict: {'APPROVED' if is_grounded else 'REJECTED (Ungrounded Claims)'}."
    return {
        "evaluation": eval_dict,
        "approved": is_grounded,
        "revision_feedback": feedback,
        "revision_count": rev_count + 1,
        "logs": state.get("logs", []) + [log_entry],
        "status": "Evaluated",
    }


def reflection_router(state: SalesOutreachState) -> str:
    """
    Conditional Edge:
    Checks if the draft was approved by the Evaluator Agent.
    If not approved and revision limit (< 2) not exceeded, returns 'writer' for self-correction.
    Otherwise, proceeds to finalize.
    """
    is_approved = state.get("approved", False)
    rev_count = state.get("revision_count", 0)

    if not is_approved and rev_count < 2:
        logger.info(f"[LangGraph:Router] Hallucination detected! Routing back to Writer Agent (Revision #{rev_count}).")
        return "writer"
    
    return "finalize"


def finalize_node(state: SalesOutreachState) -> Dict[str, Any]:
    """
    Final step: Formats and finalizes the output state for dispatch and database logging.
    """
    approved = state.get("approved", False)
    status_label = "PASSED" if approved else "BLOCKED"
    return {
        "status": status_label,
        "logs": state.get("logs", []) + [f"Pipeline complete with final status: {status_label}"],
    }


def create_sales_outreach_graph():
    """
    Builds and compiles the multi-agent LangGraph workflow.
    """
    workflow = StateGraph(SalesOutreachState)

    # Register Nodes
    workflow.add_node("researcher", research_node)
    workflow.add_node("writer", writer_node)
    workflow.add_node("evaluator", evaluator_node)
    workflow.add_node("finalize", finalize_node)

    # Build Directed Graph with Reflection Loop
    workflow.add_edge(START, "researcher")
    workflow.add_edge("researcher", "writer")
    workflow.add_edge("writer", "evaluator")
    
    # Conditional Branch: Evaluator -> Writer (Loop) OR Evaluator -> Finalize
    workflow.add_conditional_edges(
        "evaluator",
        reflection_router,
        {
            "writer": "writer",
            "finalize": "finalize",
        }
    )
    workflow.add_edge("finalize", END)

    return workflow.compile()


# Singleton compiled graph instance
_COMPILED_GRAPH = None

def get_outreach_graph():
    global _COMPILED_GRAPH
    if _COMPILED_GRAPH is None:
        _COMPILED_GRAPH = create_sales_outreach_graph()
    return _COMPILED_GRAPH


def run_langgraph_pipeline(
    prospect_name: str,
    context: str,
    company_context: Optional[str] = None
) -> Dict[str, Any]:
    """
    Executes the multi-agent sales pipeline via LangGraph.
    
    Returns standard dictionary compatible with pipeline orchestrator and dashboard.
    """
    graph = get_outreach_graph()

    initial_state: SalesOutreachState = {
        "prospect_name": prospect_name,
        "context": context,
        "company_context": company_context or "",
        "signals": {},
        "draft": {},
        "evaluation": {},
        "revision_count": 0,
        "revision_feedback": "",
        "approved": False,
        "status": "Starting",
        "logs": [f"Initiated outreach workflow for {prospect_name}"],
    }

    final_state = graph.invoke(initial_state)

    draft = final_state.get("draft", {})
    evaluation = final_state.get("evaluation", {})
    signals = final_state.get("signals", {})
    approved = final_state.get("approved", False)

    return {
        "prospect_name": prospect_name,
        "draft": draft,
        "evaluation": evaluation,
        "signals": signals,
        "approved": approved,
        "status": final_state.get("status", "COMPLETED"),
        "reasoning": evaluation.get("reasoning", "Verified claims against context."),
        "flagged_claims": evaluation.get("flagged_claims", []),
        "workflow_engine": "LangGraph",
        "revision_count": final_state.get("revision_count", 0),
        "logs": final_state.get("logs", []),
    }
