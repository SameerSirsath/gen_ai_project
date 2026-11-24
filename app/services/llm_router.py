"""
app/services/llm_router.py — Multi-Key LLM Router for Gemini & Groq.

Dynamically fetches active API keys from the database (decrypted automatically
by SQLAlchemy EncryptedText or Fernet) and routes requests with automatic
failover across multiple keys and providers.
Optimized for minimal token usage and robust fallback against rate limits (HTTP 429/403/503).
"""

from __future__ import annotations

import base64
import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import List, Optional
import httpx
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

# Model lists ordered by confirmed provider API support, high speed & accuracy
GROQ_MODELS = [
    "openai/gpt-oss-120b",
    "qwen/qwen3.6-27b",
]

GEMINI_MODELS = [
    "gemini-3.6-flash",
    "gemini-3.1-pro-preview",
]

FERNET_KEY = b"TmFqt9LDklXd67U9bNzVYkF3rkROLfYbYjxbvsTOLEg="


def _get_sqlite_keys(provider: str) -> List[str]:
    """Fallback helper to read active decrypted keys directly from local SQLite ai_sdr.db."""
    try:
        db_path = Path(__file__).resolve().parent.parent.parent / "ai_sdr.db"
        if not db_path.exists():
            return []
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT key_value FROM api_keys WHERE LOWER(provider) = LOWER(?) AND is_active = 1 ORDER BY id DESC",
            (provider,)
        )
        rows = cursor.fetchall()
        conn.close()

        cipher = Fernet(FERNET_KEY)
        keys = []
        for (enc_val,) in rows:
            if not enc_val:
                continue
            try:
                decrypted = cipher.decrypt(enc_val.encode("utf-8")).decode("utf-8")
                keys.append(decrypted)
            except Exception:
                keys.append(enc_val)
        return keys
    except Exception as e:
        logger.warning(f"Failed to query SQLite fallback keys: {e}")
        return []


def get_active_keys(provider: str) -> List[str]:
    """
    Queries the ApiKey table, filters by provider and is_active=True,
    and returns the decrypted list of key_value strings.
    """
    keys: List[str] = []
    try:
        from app.models.db import ApiKey
        db_keys = (
            ApiKey.query.filter(
                ApiKey.provider.ilike(provider),
                ApiKey.is_active == True  # noqa: E712
            ).all()
        )
        keys = [k.key_value for k in db_keys if k.key_value]
    except Exception:
        try:
            from app import create_app
            from app.models.db import ApiKey
            app = create_app()
            with app.app_context():
                db_keys = (
                    ApiKey.query.filter(
                        ApiKey.provider.ilike(provider),
                        ApiKey.is_active == True  # noqa: E712
                    ).all()
                )
                keys = [k.key_value for k in db_keys if k.key_value]
        except Exception:
            keys = _get_sqlite_keys(provider)

    if not keys:
        keys = _get_sqlite_keys(provider)

    # Also include environment variable fallback if not already in pool
    if provider.lower() == "gemini":
        env_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if env_key and env_key not in keys:
            keys.append(env_key)
    elif provider.lower() == "groq":
        env_key = os.getenv("GROQ_API_KEY")
        if env_key and env_key not in keys:
            keys.append(env_key)

    return keys


def call_llm(prompt: str, system: str = "", max_tokens: int = 1800) -> str:
    """
    Calls the LLM using active Groq and Gemini keys with intelligent automatic fallback
    across models and keys. Handles HTTP 404 (model not found) by switching to the next model,
    and HTTP 429 (rate limit) by rotating to the next API key.
    """
    groq_keys = get_active_keys("groq")
    gemini_keys = get_active_keys("gemini")

    # 1. Try Groq models
    for model_id in GROQ_MODELS:
        for i, key in enumerate(groq_keys, start=1):
            try:
                groq_url = "https://api.groq.com/openai/v1/chat/completions"
                messages = []
                if system:
                    messages.append({"role": "system", "content": system})
                messages.append({"role": "user", "content": prompt})

                groq_payload = {
                    "model": model_id,
                    "messages": messages,
                    "temperature": 0.5,
                    "max_tokens": max(max_tokens, 1024),
                }
                headers = {
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                }

                with httpx.Client(timeout=30.0) as client:
                    response = client.post(groq_url, headers=headers, json=groq_payload)

                if response.status_code == 200:
                    print(f"[Router] Success using Groq with model {model_id}.")
                    logger.info(f"[Router] Success using Groq with model {model_id}.")
                    return response.json()["choices"][0]["message"]["content"]
                elif response.status_code == 404:
                    print(f"[Router] Model {model_id} not found (404). Switching to fallback model...")
                    logger.warning(f"[Router] Model {model_id} not found (404). Switching to fallback model...")
                    break
                elif response.status_code == 429:
                    print(f"[Router] Groq key {i} rate limited (429). Rotating key...")
                    logger.warning(f"[Router] Groq key {i} rate limited (429). Rotating key...")
                    continue
                else:
                    logger.warning(
                        f"[Router] Groq key {i} with {model_id} returned HTTP {response.status_code}: {response.text[:120]}"
                    )
                    continue
            except Exception as e:
                logger.warning(f"[Router] Groq key {i} encountered error: {e}")
                continue

    # 2. Try Gemini models
    for model_id in GEMINI_MODELS:
        for i, key in enumerate(gemini_keys, start=1):
            try:
                gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={key}"
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.35,
                        "maxOutputTokens": max_tokens,
                        "topP": 0.90,
                    }
                }
                if system:
                    payload["systemInstruction"] = {"parts": [{"text": system}]}

                with httpx.Client(timeout=30.0) as client:
                    response = client.post(
                        gemini_url,
                        headers={"Content-Type": "application/json"},
                        json=payload,
                    )

                if response.status_code == 200:
                    print(f"[Router] Success using Gemini with model {model_id}.")
                    logger.info(f"[Router] Success using Gemini with model {model_id}.")
                    return response.json()["candidates"][0]["content"]["parts"][0]["text"]
                elif response.status_code == 404:
                    print(f"[Router] Model {model_id} not found (404). Switching to fallback model...")
                    logger.warning(f"[Router] Model {model_id} not found (404). Switching to fallback model...")
                    break
                elif response.status_code == 429:
                    print(f"[Router] Gemini key {i} rate limited (429). Rotating key...")
                    logger.warning(f"[Router] Gemini key {i} rate limited (429). Rotating key...")
                    continue
                else:
                    logger.warning(
                        f"[Router] Gemini key {i} with {model_id} returned HTTP {response.status_code}: {response.text[:120]}"
                    )
                    continue
            except Exception as e:
                logger.warning(f"[Router] Gemini key {i} encountered error: {e}")
                continue

    raise RuntimeError("All API keys and fallback models exhausted.")


def call_gemini_multimodal(prompt: str, mime_type: str, base64_data: str) -> str:
    """
    Calls Gemini Vision / Multimodal model to extract text, tables, and company
    intelligence from attached images (PNG/JPG) or documents.
    Rotates across fallback models and active Gemini keys.
    """
    gemini_keys = get_active_keys("gemini")
    if not gemini_keys:
        return "No active Gemini keys available for multimodal analysis."

    for model_name in GEMINI_MODELS:
        for i, key in enumerate(gemini_keys, start=1):
            gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={key}"
            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": prompt},
                            {
                                "inlineData": {
                                    "mimeType": mime_type,
                                    "data": base64_data,
                                }
                            }
                        ]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.2,
                    "maxOutputTokens": 1000,
                }
            }

            try:
                with httpx.Client(timeout=30.0) as client:
                    response = client.post(
                        gemini_url,
                        headers={"Content-Type": "application/json"},
                        json=payload,
                    )
                    if response.status_code == 200:
                        data = response.json()
                        candidates = data.get("candidates", [])
                        if candidates and "content" in candidates[0]:
                            parts = candidates[0]["content"].get("parts", [])
                            if parts and "text" in parts[0]:
                                print(f"[Router] Success using Gemini with model {model_name}.")
                                logger.info(f"Gemini Multimodal succeeded [Key #{i}, Model: {model_name}].")
                                return parts[0]["text"]
                    elif response.status_code == 404:
                        print(f"[Router] Model {model_name} not found (404). Switching to fallback model...")
                        logger.warning(f"[Router] Model {model_name} not found (404). Switching to fallback model...")
                        break
                    elif response.status_code == 429:
                        print(f"[Router] Gemini key {i} rate limited (429). Rotating key...")
                        logger.warning(f"[Router] Gemini key {i} rate limited (429). Rotating key...")
                        continue
            except Exception as e:
                logger.warning(f"Gemini multimodal attempt failed on key #{i}: {e}")
                continue

    return "Failed to extract content via multimodal vision across all keys."
