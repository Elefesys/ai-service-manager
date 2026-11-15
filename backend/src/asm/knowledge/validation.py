"""Deterministic source normalization and complete UTF-8 chunk preview."""

import hashlib
import unicodedata
from typing import Any

from asm.configuration.models import scalar_text


def normalize_source(value: str) -> str:
    return unicodedata.normalize("NFC", scalar_text(value).replace("\r\n", "\n")).strip(
        " \t\n\r\f\v"
    )


def source_text(value: str) -> str:
    canonical = normalize_source(value)
    if not canonical.strip() or len(value.encode("utf-8")) > 2048:
        raise ValueError("Invalid source text")
    return value


def plan_source(value: str) -> dict[str, Any]:
    canonical = normalize_source(value)
    if not canonical.strip():
        return {"chunks": [], "issues": ["INVALID_TEXT"]}
    if len(canonical.encode("utf-8")) > 2048:
        return {"chunks": [], "issues": ["SOURCE_TOO_LARGE"]}
    parts: list[str] = []
    part = ""
    size = 0
    for letter in canonical:
        length = len(letter.encode("utf-8"))
        if size + length > 512:
            parts.append(part)
            part, size = "", 0
        part += letter
        size += length
    if part:
        parts.append(part)
    if len(parts) > 4:
        return {"chunks": [], "issues": ["CHUNK_LIMIT"]}
    return {
        "chunks": [
            {"ordinal": n, "text": text, "sha256": hashlib.sha256(text.encode()).hexdigest()}
            for n, text in enumerate(parts)
        ],
        "issues": [],
    }
