from __future__ import annotations

import hashlib
import re
from uuid import UUID
from urllib.parse import urlparse

from .models import SourceRecord

PUBLIC_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def is_valid_public_id(value: str) -> bool:
    return bool(PUBLIC_ID_PATTERN.fullmatch(value))


def require_public_id(value: str, field_name: str = "item_id") -> str:
    if not is_valid_public_id(value):
        raise ValueError(f"{field_name} must be a lowercase ASCII slug")
    return value


def require_request_id(value: str) -> str:
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError) as exc:
        raise ValueError("request_id must be a UUID") from exc
    return str(parsed)


def source_record(item_id: str, raw_source: str | None) -> SourceRecord | None:
    citation = (raw_source or "").strip()
    if not citation:
        return None
    digest = hashlib.sha256(f"{item_id}\0{citation}".encode("utf-8")).hexdigest()[:24]
    parsed = urlparse(citation)
    url = citation if parsed.scheme in {"http", "https"} and parsed.netloc else None
    return SourceRecord(
        id=f"source-{digest}",
        item_id=item_id,
        citation=citation,
        url=url,
    )
