"""
pipeline/llm package — Multi-backend LLM and Embedding abstraction.
"""

from .base import LLMClient, EmbeddingClient
from .gemini_client import GeminiLLMClient, GeminiEmbeddingClient
from .openai_client import OpenAILLMClient, OpenAIEmbeddingClient
from .groq_client import GroqLLMClient
from .onnx_client import ONNXLLMClient, ONNXEmbeddingClient
from .factory import get_llm, get_embedder

__all__ = [
    "LLMClient",
    "EmbeddingClient",
    "GeminiLLMClient",
    "GeminiEmbeddingClient",
    "OpenAILLMClient",
    "OpenAIEmbeddingClient",
    "GroqLLMClient",
    "ONNXLLMClient",
    "ONNXEmbeddingClient",
    "get_llm",
    "get_embedder",
]
