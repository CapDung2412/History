from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Literal

from .settings import APISettings

RecognitionStatus = Literal["accepted", "needs_confirmation", "rejected"]


@dataclass(frozen=True, slots=True)
class RankedMatch:
    item_id: str
    score: float
    match_id: str
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ConfidenceDecision:
    status: RecognitionStatus
    label: str
    top_score: float | None
    margin: float | None


def normalize_similarity(value: object) -> float | None:
    """Return a finite cosine score clamped to its mathematical [-1, 1] range."""

    try:
        score = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(score):
        return None
    return max(-1.0, min(1.0, score))


def _item_id(match: dict[str, Any]) -> str:
    metadata = match.get("metadata") or {}
    value = metadata.get("item_id") or metadata.get("location_id")
    if value:
        return str(value)
    # Dataset vector IDs use <location-id>:<image-id>.
    return str(match.get("id", "")).split(":", 1)[0]


def deduplicate_matches(matches: Iterable[dict[str, Any]], limit: int = 3) -> list[RankedMatch]:
    """Keep the best image view per heritage item, sorted by cosine similarity."""

    best: dict[str, RankedMatch] = {}
    for match in matches:
        item_id = _item_id(match)
        score = normalize_similarity(match.get("score"))
        if not item_id or score is None:
            continue
        ranked = RankedMatch(
            item_id=item_id,
            score=score,
            match_id=str(match.get("id", "")),
            metadata=dict(match.get("metadata") or {}),
        )
        current = best.get(item_id)
        if current is None or ranked.score > current.score:
            best[item_id] = ranked
    return sorted(best.values(), key=lambda result: result.score, reverse=True)[:limit]


def decide_confidence(matches: list[RankedMatch], settings: APISettings) -> ConfidenceDecision:
    if not matches:
        return ConfidenceDecision("rejected", "Chưa đủ dữ liệu", None, None)

    top_score = matches[0].score
    margin = top_score - matches[1].score if len(matches) > 1 else None
    if (
        top_score >= settings.confidence_accept
        and margin is not None
        and margin >= settings.confidence_margin
    ):
        return ConfidenceDecision("accepted", "Độ tin cậy cao", top_score, margin)
    if top_score >= settings.confidence_candidate:
        return ConfidenceDecision("needs_confirmation", "Cần xác nhận", top_score, margin)
    return ConfidenceDecision("rejected", "Chưa đủ dữ liệu", top_score, margin)
