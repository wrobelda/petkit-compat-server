#!/usr/bin/env python3
"""Encode, decode, and redact profiled Petkit SoftAP TCP/JSON messages."""

from __future__ import annotations

import json
import struct
from typing import Any


MAX_BODY_BYTES = 64 * 1024
SECRET_KEY_PARTS = ("password", "passwd", "secret", "token", "credential")
SECRET_KEYS = frozenset(
    {
        "pwd",
        "psk",
        "session",
        "authorization",
        "auth",
        "apikey",
        "username",
        "email",
    }
)


def is_secret_key(key: object) -> bool:
    if not isinstance(key, str):
        return False
    normalized = "".join(
        character for character in key.casefold() if character.isalnum()
    )
    return normalized in SECRET_KEYS or any(
        part in normalized for part in SECRET_KEY_PARTS
    )


def encode_json(message: Any) -> bytes:
    body = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    if len(body) > MAX_BODY_BYTES:
        raise ValueError("SoftAP JSON body is too large")
    return struct.pack(">I", len(body)) + body


def decode_frame(frame: bytes) -> Any:
    if len(frame) < 4:
        raise ValueError("SoftAP frame is missing its length prefix")
    body_size = struct.unpack(">I", frame[:4])[0]
    if body_size > MAX_BODY_BYTES:
        raise ValueError("SoftAP JSON body is too large")
    if len(frame) != body_size + 4:
        raise ValueError(
            f"SoftAP frame length mismatch: header={body_size}, actual={len(frame) - 4}"
        )
    return json.loads(frame[4:].decode("utf-8"))


def redact(value: Any) -> Any:
    """Return a recursively redacted copy safe for diagnostic output."""
    if isinstance(value, dict):
        return {
            key: "<redacted>" if is_secret_key(key) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value
