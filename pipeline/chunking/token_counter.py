"""
token_counter.py — Token counting utilities.

Uses tiktoken (OpenAI's tokenizer) when available, falls back to a
simple word-based approximation (1 token ≈ 0.75 words).

This keeps the chunking strategies model-agnostic while still producing
correctly-sized chunks for LLM context windows.
"""

from typing import Optional

# ─────────────────────────────────────────────
# Global tokenizer cache
# ─────────────────────────────────────────────

_TOKENIZER = None          # tiktoken tokenizer instance
_TIKTOKEN_AVAILABLE = None # None = not yet checked


def _get_tokenizer():
    """Lazy-load the tiktoken tokenizer (cl100k_base, used by GPT-4 / embeddings)."""
    global _TOKENIZER, _TIKTOKEN_AVAILABLE
    if _TIKTOKEN_AVAILABLE is None:
        try:
            import tiktoken
            _TOKENIZER = tiktoken.get_encoding("cl100k_base")
            _TIKTOKEN_AVAILABLE = True
        except ImportError:
            _TIKTOKEN_AVAILABLE = False
    return _TOKENIZER if _TIKTOKEN_AVAILABLE else None


# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────

def count_tokens(text: str) -> int:
    """
    Count tokens in a string.
    Uses tiktoken if available, otherwise approximates: tokens ≈ words * 1.35
    """
    tokenizer = _get_tokenizer()
    if tokenizer:
        return len(tokenizer.encode(text))
    # Approximation: average English word ≈ 1.35 tokens
    return int(len(text.split()) * 1.35)


def split_into_token_windows(
    text: str,
    max_tokens: int,
    overlap_tokens: int = 0,
) -> list[str]:
    """
    Split text into windows of max_tokens with optional overlap.
    This is the building block for fixed-token chunking.

    Args:
        text:           Input text.
        max_tokens:     Maximum tokens per window.
        overlap_tokens: How many tokens from the end of one window
                        to repeat at the start of the next.

    Returns:
        List of text windows (strings).
    """
    tokenizer = _get_tokenizer()

    if tokenizer:
        tokens = tokenizer.encode(text)
        windows = []
        start = 0
        while start < len(tokens):
            end = min(start + max_tokens, len(tokens))
            chunk_tokens = tokens[start:end]
            windows.append(tokenizer.decode(chunk_tokens))
            if end == len(tokens):
                break
            start += max_tokens - overlap_tokens
        return windows

    # Fallback: word-based splitting (1 word ≈ 0.75 tokens)
    words = text.split()
    word_chunk  = int(max_tokens / 1.35)
    word_overlap = int(overlap_tokens / 1.35)
    windows = []
    start = 0
    while start < len(words):
        end = min(start + word_chunk, len(words))
        windows.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start += word_chunk - word_overlap
    return windows


def tokens_available() -> bool:
    """Returns True if tiktoken is installed and working."""
    return _get_tokenizer() is not None
