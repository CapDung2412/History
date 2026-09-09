from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class LocationRecord:
    address: str | None
    city: str | None
    province: str | None
    country: str | None
    latitude: float | None
    longitude: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SourceRecord:
    id: str
    item_id: str
    citation: str
    title: str | None = None
    url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ImageRecord:
    id: str
    item_id: str
    filename: str
    relative_path: str
    drive_url: str | None
    caption: str
    year: int | None
    view: str | None
    sort_order: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HistoricalInfoRecord:
    title: str
    description: str
    historical_period: str | None
    year: int | None
    event: str | None
    source: str | None
    source_status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ArtifactRecord:
    id: str
    slug: str
    name: str
    category: str
    tags: tuple[str, ...]
    dataset_name: str
    dataset_version: str
    location: LocationRecord
    historical_info: HistoricalInfoRecord
    images: tuple[ImageRecord, ...]
    sources: tuple[SourceRecord, ...] = ()
    published: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StoryRecord:
    item_id: str
    quick: dict[str, Any]
    overview: dict[str, Any]
    deep: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ChallengeOptionRecord:
    id: str
    label: str
    is_correct: bool
    sort_order: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ChallengeRecord:
    id: str
    item_id: str
    type: str
    question: str
    options: tuple[ChallengeOptionRecord, ...]
    explanation: str
    source_field: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RecognitionRecord:
    request_id: str
    status: str
    candidate_ids: tuple[str, ...] = ()
    resolved_item_id: str | None = None
    top1_score: float | None = None
    score_margin: float | None = None
    quality_issues: tuple[str, ...] = ()
    quality_metrics: dict[str, float | int | bool | None] = field(default_factory=dict)
    duration_ms: float | None = None
    component_timings_ms: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FeedbackRecord:
    request_id: str
    is_correct: bool
    selected_item_id: str | None = None
    no_match: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
