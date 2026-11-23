"""
app/models/encrypted_type.py — Fernet Column-Level Encryption TypeDecorator.
"""

from __future__ import annotations

import os
from flask import current_app
from sqlalchemy import TypeDecorator, Text
from cryptography.fernet import Fernet


class EncryptedText(TypeDecorator):
    """
    Column-level encryption TypeDecorator using Fernet symmetric encryption.
    Encrypts string values when saving to the database and decrypts them when retrieved.
    """
    impl = Text
    cache_ok = True

    def _get_fernet(self) -> Fernet:
        key = None
        try:
            if current_app:
                key = current_app.config.get("ENCRYPTION_KEY")
        except RuntimeError:
            pass

        if not key:
            key = os.getenv("ENCRYPTION_KEY", "")

        if isinstance(key, str):
            key = key.strip("'\"").encode("utf-8")
        elif isinstance(key, bytes):
            key = key.strip(b"'\"")

        if not key:
            raise ValueError("ENCRYPTION_KEY is not configured in app.config or environment.")

        return Fernet(key)

    def process_bind_param(self, value, dialect):
        if value is not None and value != "":
            fernet = self._get_fernet()
            val_bytes = value.encode("utf-8") if isinstance(value, str) else bytes(value)
            return fernet.encrypt(val_bytes).decode("utf-8")
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value != "":
            fernet = self._get_fernet()
            val_bytes = value.encode("utf-8") if isinstance(value, str) else bytes(value)
            return fernet.decrypt(val_bytes).decode("utf-8")
        return value
