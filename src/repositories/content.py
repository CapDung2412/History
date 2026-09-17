from __future__ import annotations

import hashlib

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
    distractors = sorted(category for category in set(available_categories) if category != artifact.category)
    if len(distractors) < 3:
        return None

    challenge_id = f"challenge-{artifact.id}-category-v1"
    digest = hashlib.sha256(challenge_id.encode("utf-8")).digest()
    selected: list[str] = []
    remaining = list(distractors)
    for byte in digest:
        if not remaining or len(selected) == 3:
            break
        selected.append(remaining.pop(byte % len(remaining)))

    values = [artifact.category, *selected]
    values.sort(key=lambda value: hashlib.sha256(f"{challenge_id}\0{value}".encode()).digest())
    options = tuple(
        ChallengeOptionRecord(
            id=f"{challenge_id}-option-{index + 1}",
            label=category_label(value),
            is_correct=value == artifact.category,
            sort_order=index,
        )
        for index, value in enumerate(values)
    )
    correct_label = category_label(artifact.category)
    return ChallengeRecord(
        id=challenge_id,
        item_id=artifact.id,
        type="single_choice",
        question=f"“{artifact.name}” thuộc nhóm tư liệu nào?",
        options=options,
        explanation=f"Dữ liệu trưng bày phân loại hiện vật này là “{correct_label}”.",
        source_field="category",
    )
