from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import replace

from .models import (
    ArtifactRecord,
    ChallengeOptionRecord,
    ChallengeRecord,
    StoryRecord,
)

CATEGORY_LABELS = {
    "documentary_artifact": "Hiện vật tư liệu",
    "exhibition_panel": "Bảng trưng bày",
    "exhibition_space": "Không gian trưng bày",
    "historical_map": "Bản đồ lịch sử",
    "historical_model": "Mô hình lịch sử",
    "historical_photograph": "Ảnh tư liệu lịch sử",
    "military_artifact": "Hiện vật quân sự",
    "military_insignia": "Phù hiệu quân sự",
    "military_vehicle": "Phương tiện quân sự",
    "museum_exhibition": "Trưng bày bảo tàng",
}


def category_label(category: str) -> str:
    return CATEGORY_LABELS.get(category, category.replace("_", " "))


def build_story(artifact: ArtifactRecord) -> StoryRecord:
    history = artifact.historical_info
    images = [image.to_dict() for image in artifact.images]
    sources = [source.to_dict() for source in artifact.sources]
    primary_image = images[0] if images else None
    return StoryRecord(
        item_id=artifact.id,
        quick={
            "name": artifact.name,
            "title": history.title,
            "category": artifact.category,
            "category_label": category_label(artifact.category),
            "historical_period": history.historical_period,
            "year": history.year,
            "primary_image": primary_image,
        },
        overview={
            "description": history.description,
            "event": history.event,
        },
        deep={
            "description": history.description,
            "event": history.event,
            "images": images,
            "sources": sources,
            "source_status": history.source_status,
            "source_notice": (
                "Nguồn đã được đánh dấu xác minh trong quy trình biên tập"
                if history.source_status == "verified"
                else "Nguồn đi kèm dữ liệu hiện vật; chưa được xác minh độc lập"
                if history.source_status == "available"
                else "Nguồn tư liệu đang được bổ sung"
            ),
        },
    )


def build_category_challenge(
    artifact: ArtifactRecord,
    available_categories: tuple[str, ...],
) -> ChallengeRecord | None:
    correct_label = category_label(artifact.category)
    return _build_choice_challenge(
        artifact=artifact,
        source_field="category",
        question=f"“{artifact.name}” thuộc nhóm tư liệu nào?",
        correct_label=correct_label,
        distractor_labels=(
            category_label(category)
            for category in available_categories
            if category != artifact.category
        ),
        explanation=f"Dữ liệu trưng bày phân loại hiện vật này là “{correct_label}”.",
    )


def build_artifact_challenge(
    artifact: ArtifactRecord,
    catalog: tuple[ArtifactRecord, ...],
) -> ChallengeRecord | None:
    """Build a deterministic 2-3 question set while preserving the legacy API shape."""

    questions = build_artifact_challenges(artifact, catalog)
    if not questions:
        return None
    return replace(questions[0], additional_questions=questions[1:])


def build_artifact_challenges(
    artifact: ArtifactRecord,
    catalog: tuple[ArtifactRecord, ...],
    limit: int = 3,
) -> tuple[ChallengeRecord, ...]:
    """Build up to three grounded questions without treating a broad period as an event."""

    history = artifact.historical_info
    candidates: list[ChallengeRecord] = []

    statement = _content_statement(history.description)
    if statement:
        challenge = _build_choice_challenge(
            artifact=artifact,
            source_field="historical_info.description",
            question=f"Theo nội dung giới thiệu, nhận định nào đúng về “{artifact.name}”?",
            correct_label=statement,
            distractor_labels=(
                candidate_statement
                for item in catalog
                if item.id != artifact.id
                if (candidate_statement := _content_statement(item.historical_info.description))
            ),
            explanation=f"Nội dung mô tả cho biết: “{statement}”",
        )
        if challenge:
            candidates.append(challenge)

    if history.event:
        challenge = _build_choice_challenge(
            artifact=artifact,
            source_field="historical_info.event",
            question=f"Nội dung hoặc sự kiện nào gắn trực tiếp với “{artifact.name}”?",
            correct_label=history.event,
            distractor_labels=(
                item.historical_info.event
                for item in catalog
                if item.id != artifact.id and item.historical_info.event
            ),
            explanation=f"Dữ liệu hiện vật ghi nội dung/sự kiện là “{history.event}”.",
        )
        if challenge:
            candidates.append(challenge)

    if history.year is not None:
        year_label = str(history.year)
        challenge = _build_choice_challenge(
            artifact=artifact,
            source_field="historical_info.year",
            question=f"Mốc thời gian nào được ghi nhận cho “{artifact.name}”?",
            correct_label=year_label,
            distractor_labels=(
                str(item.historical_info.year)
                for item in catalog
                if item.id != artifact.id and item.historical_info.year is not None
            ),
            explanation=f"Mốc thời gian được ghi trong dữ liệu là {year_label}.",
        )
        if challenge:
            candidates.append(challenge)

    category_challenge = build_category_challenge(
        artifact,
        tuple(item.category for item in catalog),
    )
    if category_challenge:
        candidates.append(category_challenge)

    if not candidates:
        return ()

    selector = hashlib.sha256(artifact.id.encode("utf-8")).digest()[0]
    start = selector % len(candidates)
    ordered = candidates[start:] + candidates[:start]
    selected = ordered[: max(1, min(limit, 3))]
    return tuple(
        _rekey_challenge(challenge, artifact.id, index)
        for index, challenge in enumerate(selected)
    )


def _rekey_challenge(
    challenge: ChallengeRecord,
    artifact_id: str,
    index: int,
) -> ChallengeRecord:
    base_id = f"challenge-{artifact_id}-category-v1"
    challenge_id = base_id if index == 0 else f"{base_id}-q{index + 1}"
    options = tuple(
        replace(option, id=f"{challenge_id}-option-{option_index + 1}")
        for option_index, option in enumerate(challenge.options)
    )
    return replace(
        challenge,
        id=challenge_id,
        options=options,
        additional_questions=(),
    )


def _content_statement(description: str, max_length: int = 220) -> str | None:
    normalized = " ".join(description.split())
    if not normalized:
        return None

    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", normalized)
        if len(sentence.strip()) >= 24
    ]
    if not sentences:
        sentences = [normalized]

    generic_prefixes = (
        "hiện vật được nhận diện",
        "hiện vật được đặt",
        "tư liệu được đặt",
        "nguồn hiện có chưa",
    )
    sentence = min(
        sentences,
        key=lambda value: (
            value.casefold().startswith(generic_prefixes),
            abs(min(len(value), max_length) - 125),
        ),
    )
    if len(sentence) <= max_length:
        return sentence

    shortened = sentence[: max_length - 1].rsplit(" ", 1)[0].rstrip(" ,;")
    return f"{shortened}…"


def _build_choice_challenge(
    *,
    artifact: ArtifactRecord,
    source_field: str,
    question: str,
    correct_label: str,
    distractor_labels: Iterable[str | None],
    explanation: str,
) -> ChallengeRecord | None:
    challenge_id = f"challenge-{artifact.id}-category-v1"
    normalized_correct = correct_label.strip()
    unique: dict[str, str] = {}
    for raw_label in distractor_labels:
        label = str(raw_label or "").strip()
        key = label.casefold()
        if label and key != normalized_correct.casefold():
            unique.setdefault(key, label)

    remaining = sorted(unique.values(), key=str.casefold)
    digest = hashlib.sha256(f"{challenge_id}\0{source_field}".encode("utf-8")).digest()
    selected: list[str] = []
    for byte in digest:
        if not remaining or len(selected) == 3:
            break
        selected.append(remaining.pop(byte % len(remaining)))
    if len(selected) < 3:
        return None

    values = [normalized_correct, *selected]
    values.sort(
        key=lambda value: hashlib.sha256(
            f"{challenge_id}\0{source_field}\0{value}".encode("utf-8")
        ).digest()
    )
    options = tuple(
        ChallengeOptionRecord(
            id=f"{challenge_id}-option-{index + 1}",
            label=value,
            is_correct=value == normalized_correct,
            sort_order=index,
        )
        for index, value in enumerate(values)
    )
    return ChallengeRecord(
        id=challenge_id,
        item_id=artifact.id,
        type="single_choice",
        question=question,
        options=options,
        explanation=explanation,
        source_field=source_field,
    )
