"""
pipeline/schemas.py — Data contracts and Pydantic schemas for agent handoffs.
"""

from __future__ import annotations

from typing import List, Any
from pydantic import BaseModel, Field, field_validator


class ResearchSignals(BaseModel):
    """
    Data contract representing research signals extracted by the Researcher Agent.
    - pain_points: Max 2 items.
    - recent_news: Max 1 item.
    - relevance_score: Between 0.0 and 1.0.
    """
    pain_points: List[str] = Field(
        default_factory=list,
        description="Top pain points identified for the prospect (max 2 items)."
    )
    recent_news: List[str] = Field(
        default_factory=list,
        description="Recent company or prospect news events (max 1 item)."
    )
    relevance_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Relevance score between prospect context and outreach goal (between 0.0 and 1.0)."
    )

    @field_validator("pain_points", mode="before")
    @classmethod
    def cap_pain_points(cls, v: Any) -> List[str]:
        if isinstance(v, list):
            return [str(item) for item in v[:2]]
        elif isinstance(v, str):
            return [v]
        return []

    @field_validator("recent_news", mode="before")
    @classmethod
    def cap_recent_news(cls, v: Any) -> List[str]:
        if isinstance(v, list):
            return [str(item) for item in v[:1]]
        elif isinstance(v, str):
            return [v]
        return []

    @field_validator("relevance_score", mode="before")
    @classmethod
    def clamp_relevance(cls, v: Any) -> float:
        try:
            val = float(v)
            return max(0.0, min(1.0, val))
        except (ValueError, TypeError):
            return 0.5


class WriterOutput(BaseModel):
    """
    Data contract representing the formal outreach email drafted by the Writer Agent.
    - subject: Email subject line.
    - body: Complete formal B2B email body.
    - claims_used: The specific facts pulled from the context.
    """
    subject: str = Field(
        ...,
        description="Email subject line."
    )
    body: str = Field(
        ...,
        description="Complete formal B2B email body."
    )
    claims_used: List[str] = Field(
        default_factory=list,
        description="The specific facts pulled from the context."
    )

    @field_validator("claims_used", mode="before")
    @classmethod
    def ensure_claims_list(cls, v: Any) -> List[str]:
        if isinstance(v, list):
            return [str(item) for item in v]
        elif isinstance(v, str):
            return [v]
        return []


class EvaluationResult(BaseModel):
    """
    Data contract representing the fact-checking evaluation by the Evaluator Agent.
    - is_grounded: True if all claims are supported by context.
    - flagged_claims: Any claims that lack evidence.
    - reasoning: Brief explanation of the check.
    """
    is_grounded: bool = Field(
        ...,
        description="True if all claims are supported by context."
    )
    flagged_claims: List[str] = Field(
        default_factory=list,
        description="Any claims that lack evidence."
    )
    reasoning: str = Field(
        ...,
        description="Brief explanation of the fact-check audit."
    )

    @field_validator("flagged_claims", mode="before")
    @classmethod
    def ensure_flagged_list(cls, v: Any) -> List[str]:
        if isinstance(v, list):
            return [str(item) for item in v]
        elif isinstance(v, str):
            return [v]
        return []
