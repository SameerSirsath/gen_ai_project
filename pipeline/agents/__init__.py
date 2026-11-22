"""
pipeline/agents package — Multi-agent system (Researcher, Writer, Evaluator).
"""

from .researcher import extract_signals
from .writer import draft_email
from .evaluator import evaluate_email

__all__ = ["extract_signals", "draft_email", "evaluate_email"]
