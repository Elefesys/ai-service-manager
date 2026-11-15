"""Bounded canonical owner descriptions; no AI inference supplies authority."""

import unicodedata


def canonical_text(value: str, maximum: int) -> str:
    if (
        value != unicodedata.normalize("NFC", value.replace("\r\n", "\n")).strip(" \t\n\r\f\v")
        or not value
        or len(value.encode("utf-8")) > maximum
        or any(unicodedata.category(c).startswith("C") and c not in "\t\n" for c in value)
    ):
        raise ValueError("CANONICAL_TEXT_REQUIRED")
    return value
