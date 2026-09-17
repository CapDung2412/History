from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from typing import Any


# These fragments are characteristic of UTF-8 bytes decoded as a legacy
# single-byte encoding. They deliberately avoid ordinary Vietnamese text such
# as "Âu".
MOJIBAKE_FRAGMENTS = (
    "Ã¡",
    "Ã ",
    "Ã¢",
    "Ã£",
    "Ã¨",
    "Ã©",
    "Ãª",
    "Ã¬",
    "Ã²",
    "Ã³",
    "Ã´",
    "Ã¹",
    "Ãº",
    "Ä‘",
    "Æ¡",
    "Æ°",
    "áº",
    "á»",
)

_HTML_TAG = re.compile(r"<[^>]*>")
_HTTP_URL = re.compile(r"https?://\S+", flags=re.IGNORECASE)


def normalize_nfc(value: str) -> str:
    """Return a stable NFC string without changing its visible content."""

    return unicodedata.normalize("NFC", value)


def normalize_unicode_tree(value: Any) -> Any:
    """Normalize strings recursively at JSON/model trust boundaries."""

    if isinstance(value, str):
        return normalize_nfc(value)
    if isinstance(value, Mapping):
        return {
            normalize_nfc(key) if isinstance(key, str) else key: normalize_unicode_tree(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [normalize_unicode_tree(item) for item in value]
    if isinstance(value, tuple):
        return tuple(normalize_unicode_tree(item) for item in value)
    return value


def contains_mojibake(value: str) -> bool:
    return any(fragment in value for fragment in MOJIBAKE_FRAGMENTS)


def clean_speech_text(value: str) -> str:
    """Prepare plain Vietnamese text for TTS without HTML or URLs."""

    normalized = normalize_nfc(value)
    without_markup = _HTML_TAG.sub(" ", normalized)
    without_urls = _HTTP_URL.sub(" ", without_markup)
    return " ".join(without_urls.split())
