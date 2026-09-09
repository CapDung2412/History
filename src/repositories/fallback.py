from __future__ import annotations

from collections.abc import Callable
import logging
from typing import TypeVar

from .base import HeritageRepository, RepositoryError, RepositoryUnavailableError
from .json_repository import JsonHeritageRepository
from .models import (
    ArtifactRecord,
    ChallengeRecord,
    FeedbackRecord,
    ImageRecord,
    RecognitionRecord,
    StoryRecord,
)

T = TypeVar("T")
logger = logging.getLogger(__name__)


class FallbackHeritageRepository:
    """Fall back to JSON for unavailable reads; persist analytics locally before mirroring.

    SQLite is the durable analytics journal. A network failure cannot split a
    request and its feedback between repositories. Remote mirrors use the same
    request UUID; consumers must not sum the local journal and its remote mirror.
    """

    def __init__(self, primary: HeritageRepository, fallback: JsonHeritageRepository) -> None:
        self.primary = primary
        self.fallback = fallback

    def _read(self, primary: Callable[[], T], fallback: Callable[[], T]) -> T:
        try:
            return primary()
        except RepositoryUnavailableError:
            return fallback()

    def get_artifact(self, item_id: str) -> ArtifactRecord | None:
        return self._read(
            lambda: self.primary.get_artifact(item_id),
            lambda: self.fallback.get_artifact(item_id),
        )

    def list_artifacts(self) -> tuple[ArtifactRecord, ...]:
        return self._read(self.primary.list_artifacts, self.fallback.list_artifacts)

    def get_story(self, item_id: str) -> StoryRecord | None:
        return self._read(
            lambda: self.primary.get_story(item_id),
            lambda: self.fallback.get_story(item_id),
        )

    def get_images(self, item_id: str) -> tuple[ImageRecord, ...]:
        return self._read(
            lambda: self.primary.get_images(item_id),
            lambda: self.fallback.get_images(item_id),
        )

    def get_challenge(self, item_id: str) -> ChallengeRecord | None:
        return self._read(
            lambda: self.primary.get_challenge(item_id),
            lambda: self.fallback.get_challenge(item_id),
        )

    def record_recognition(self, record: RecognitionRecord) -> None:
        self.fallback.record_recognition(record)
        try:
            self.primary.record_recognition(record)
        except RepositoryError as exc:
            logger.warning("Remote recognition mirror failed (%s); local journal retained", type(exc).__name__)

    def record_feedback(self, record: FeedbackRecord) -> None:
        self.fallback.record_feedback(record)
        context = self.fallback.get_recognition(record.request_id)
        # Local feedback validation already proved that this context exists.
        assert context is not None
        try:
            # An earlier request write may have timed out or failed. Replay its
            # immutable server context before feedback; the primary upserts UUIDs.
            self.primary.record_recognition(context)
            self.primary.record_feedback(record)
        except RepositoryError as exc:
            logger.warning("Remote feedback mirror failed (%s); local journal retained", type(exc).__name__)
