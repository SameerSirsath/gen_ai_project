"""
app/services/llm_router.py — Multi-Key LLM Router for Groq & Gemini.

Dynamically fetches active API keys from the MySQL database (automatically
decrypted by SQLAlchemy's EncryptedText TypeDecorator) and routes requests
with automatic failover across multiple keys and providers.
"""

from __future__ import annotations

import json
import logging
import httpx
from typing import List

from flask import current_app
from app.models.db import ApiKey

logger = logging.getLogger(__name__)


def get_active_keys(provider: str) -> List[str]:
    """
    Queries the ApiKey table, filters by provider and is_active=True,
    and returns the decrypted list of key_value strings.
    """
    try:
        keys = (
            ApiKey.query.filter(
                ApiKey.provider.ilike(provider),
                ApiKey.is_active == True  # noqa: E712
            ).all()
        )
        return [k.key_value for k in keys if k.key_value]
    except RuntimeError:
        # Outside Flask application context: create a temporary app context
        from app import create_app
        app = create_app()
        with app.app_context():
            keys = (
                ApiKey.query.filter(
                    ApiKey.provider.ilike(provider),
                    ApiKey.is_active == True  # noqa: E712
                ).all()
            )
            return [k.key_value for k in keys if k.key_value]


def call_llm(prompt: str, system: str = "") -> str:
    """
    Calls the LLM using active Groq keys with failover.
    If all Groq keys fail, cascades to active Gemini keys.
    Raises RuntimeError if all keys are exhausted.
    """
    groq_keys = get_active_keys("groq")
    gemini_keys = get_active_keys("gemini")

    # 1. Attempt Groq keys (llama-3.3-70b-versatile)
    groq_url = "https://api.groq.com/openai/v1/chat/completions"
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    groq_payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": messages,
        "temperature": 0.7,
    }

    with httpx.Client(timeout=30.0) as client:
        for idx, key in enumerate(groq_keys, start=1):
            try:
                headers = {
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                }
                resp = client.post(groq_url, headers=headers, json=groq_payload)
                if resp.status_code == 200:
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    logger.info(f"Groq API call succeeded using key #{idx}.")
                    return content
                else:
                    logger.warning(
                        f"Groq key #{idx} returned HTTP {resp.status_code}: {resp.text[:120]}. Falling back..."
                    )
            except Exception as e:
                logger.warning(f"Groq key #{idx} failed with error: {e}. Falling back...")
                continue

        # 2. Fallback to Gemini keys (gemini-2.5-flash)
        gemini_model = "gemini-2.5-flash"
        gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent"

        gemini_payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ]
        }
        if system:
            gemini_payload["systemInstruction"] = {
                "parts": [{"text": system}]
            }

        for idx, key in enumerate(gemini_keys, start=1):
            try:
                headers = {
                    "Content-Type": "application/json",
                    "x-goog-api-key": key,
                }
                params = {"key": key}
                resp = client.post(gemini_url, headers=headers, params=params, json=gemini_payload)
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if candidates and "content" in candidates[0]:
                        parts = candidates[0]["content"].get("parts", [])
                        if parts and "text" in parts[0]:
                            logger.info(f"Gemini API call succeeded using key #{idx}.")
                            return parts[0]["text"]
                else:
                    logger.warning(
                        f"Gemini key #{idx} returned HTTP {resp.status_code}: {resp.text[:120]}. Falling back..."
                    )
            except Exception as e:
                logger.warning(f"Gemini key #{idx} failed with error: {e}. Falling back...")
                continue

    # 3. All keys exhausted
    raise RuntimeError("All API keys exhausted.")
