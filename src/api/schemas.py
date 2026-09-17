from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class APIModel(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class HealthResponse(APIModel):
    status: Literal["ok", "ready", "not_ready"]
    version: str
    repository_ready: bool | None = None
    model_loaded: bool | None = None
    pinecone_configured: bool | None = None
    index_verified_at_load: bool | None = Field(
        default=None,
        description="Existing index was checked when the model runtime loaded; this is not a live network probe.",
    )


class WarmupResponse(APIModel):
    status: Literal["ready"]
    model_name: str
    embedding_dimension: int
    elapsed_ms: float


class QualityMetrics(APIModel):
    width: int
    height: int
    file_size_bytes: int
    pixel_count: int
    brightness: float
    blur_score: float
    sharpness: float
    brightness_mean: float
    brightness_p25: float
    brightness_p75: float
    laplacian_variance: float
    glare_ratio: float


class QualityIssueResponse(APIModel):
    code: str
    message: str
    guidance: str
    severity: Literal["warning", "error"] = "error"


class QualityAssessment(APIModel):
    status: Literal["passed", "failed", "warning"]
    metrics: QualityMetrics
    issues: list[QualityIssueResponse]


class LocationInfo(APIModel):
    address: str | None = None
    city: str | None = None
    province: str | None = None
    country: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class HistoricalInfo(APIModel):
    title: str
    description: str
    historical_period: str | None = None
    year: int | None = None
    event: str | None = None
    source: str | None = None
    source_status: str | None = None


class ArtifactImage(APIModel):
    id: str
    item_id: str | None = None
    filename: str
    relative_path: str | None = None
    drive_url: str | None = None
    caption: str
    year: int | None = None
    view: str | None = None
    sort_order: int | None = None
    url: str | None = None


class ArtifactResponse(APIModel):
    item_id: str
    slug: str | None = None
    name: str
    title: str | None = None
    category: str
    tags: list[str] = Field(default_factory=list)
    historical_period: str | None = None
    period: str | None = None
    year: int | None = None
    description: str
    event: str | None = None
    source: str | None = None
    source_verified: bool = False
    location: LocationInfo | None = None
    images: list[ArtifactImage]


class StoryQuick(APIModel):
    title: str
    category: str
    period: str | None = None
    year: int | None = None
    image: ArtifactImage | None = None


class StoryOverview(APIModel):
    description: str | None = None
    event: str | None = None
    what_it_is: str | None = None
    role: str | None = None
    context: str | None = None
    significance: str | None = None
    paragraphs: list[str] = Field(default_factory=list)


class StoryDeep(APIModel):
    description: str
    event: str | None = None
    people: list[str] = Field(default_factory=list)
    related_events: list[str] = Field(default_factory=list)
    images: list[ArtifactImage] = Field(default_factory=list)
    source: str | None = None
    source_verified: bool = False


class StoryResponse(APIModel):
    item_id: str
    quick: StoryQuick
    overview: StoryOverview
    deep: StoryDeep


class ChallengeOption(APIModel):
    id: str
    label: str


class ChallengeResponse(APIModel):
    id: str
    item_id: str
    type: str
    question: str
    options: list[ChallengeOption]
    correct_option_id: str
    explanation: str
    source_field: str


class RecognitionCandidate(APIModel):
    item_id: str
    location_id: str | None = None
    name: str
    title: str | None = None
    category: str
    period: str | None = None
    historical_period: str | None = None
    year: int | None = None
    score: float = Field(ge=-1.0, le=1.0, description="Cosine similarity, not an accuracy percentage")
    image_url: str | None = None
    image_caption: str | None = None


class RecognitionResponse(APIModel):
    request_id: UUID
    quality: QualityAssessment
    recognition_status: Literal["accepted", "needs_confirmation", "rejected"]
    confidence_label: str
    top_score: float | None = Field(default=None, ge=-1.0, le=1.0)
    score_margin: float | None = Field(default=None, ge=0.0, le=2.0)
    candidates: list[RecognitionCandidate]
    selected_item: RecognitionCandidate | None = None
    timings_ms: dict[str, float]


class FeedbackRequest(APIModel):
    is_correct: bool
    selected_item_id: str | None = Field(default=None, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    none_of_the_above: bool = False
    comment: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_selection(self) -> "FeedbackRequest":
        if self.none_of_the_above and self.selected_item_id:
            raise ValueError("selected_item_id and none_of_the_above cannot both be set")
        if not self.is_correct and not (self.selected_item_id or self.none_of_the_above):
            raise ValueError("Incorrect feedback requires a selected item or none_of_the_above")
        return self


class FeedbackResponse(APIModel):
    status: Literal["recorded"]
    request_id: UUID


class ErrorDetail(APIModel):
    code: str
    message: str
    request_id: UUID | None = None


class ErrorResponse(APIModel):
    detail: ErrorDetail
