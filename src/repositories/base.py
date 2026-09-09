from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import (
    ArtifactRecord,
    ChallengeRecord,
    FeedbackRecord,
    ImageRecord,
    RecognitionRecord,
    StoryRecord,
)


class RepositoryError(RuntimeError):
    """Base error for repository operations."""


class RepositoryUnavailableError(RepositoryError):
    """The configured external repository could not be reached."""


class RepositoryIntegrityError(RepositoryError):
    """Stored data or an attempted write violates repository invariants."""


@runtime_checkable
class HeritageRepository(Protocol):
    def get_artifact(self, item_id: str) -> ArtifactRecord | None: ...

    def list_artifacts(self) -> tuple[ArtifactRecord, ...]: ...

    def get_story(self, item_id: str) -> StoryRecord | None: ...

    def get_images(self, item_id: str) -> tuple[ImageRecord, ...]: ...

    def get_challenge(self, item_id: str) -> ChallengeRecord | None: ...

    def record_recognition(self, record: RecognitionRecord) -> None: ...

    def record_feedback(self, record: FeedbackRecord) -> None: ...
