from __future__ import annotations

from dataclasses import replace

from src.api.confidence import decide_confidence, deduplicate_matches, normalize_similarity
from src.api.settings import APISettings


def _match(item: str, image: str, score: float) -> dict:
    return {
        "id": f"{item}:{image}",
        "score": score,
        "metadata": {"item_id": item, "image_id": image},
    }


def test_deduplicate_keeps_best_view_and_three_distinct_items() -> None:
    results = deduplicate_matches(
        [
            _match("artifact-a", "a1", 0.81),
            _match("artifact-a", "a2", 0.92),
            _match("artifact-b", "b1", 0.88),
            _match("artifact-c", "c1", 0.70),
            _match("artifact-d", "d1", 0.60),
        ],
        limit=3,
    )
    assert [result.item_id for result in results] == ["artifact-a", "artifact-b", "artifact-c"]
    assert results[0].match_id.endswith("a2")


def test_score_normalization_clamps_domain_and_drops_non_finite_values() -> None:
    assert normalize_similarity(1.7) == 1.0
    assert normalize_similarity(-3) == -1.0
    assert normalize_similarity(float("nan")) is None
    assert normalize_similarity("not-a-score") is None


def test_confidence_gate_uses_score_and_margin() -> None:
    settings = APISettings()
    high_margin = deduplicate_matches([_match("a", "1", 0.85), _match("b", "1", 0.70)])
    assert decide_confidence(high_margin, settings).status == "accepted"

    close = deduplicate_matches([_match("a", "1", 0.80), _match("b", "1", 0.76)])
    assert decide_confidence(close, settings).status == "needs_confirmation"

    low = deduplicate_matches([_match("a", "1", 0.40), _match("b", "1", 0.30)])
    assert decide_confidence(low, settings).status == "rejected"


def test_high_score_without_runner_up_requires_confirmation() -> None:
    only = deduplicate_matches([_match("a", "1", 0.95)])
    assert decide_confidence(only, replace(APISettings(), confidence_accept=0.8)).status == "needs_confirmation"
