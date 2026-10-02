from __future__ import annotations

from pathlib import Path

from .analytics import AnalyticsStore, SqliteAnalyticsStore
from .content import build_artifact_challenge, build_story
from .helpers import require_public_id
from .loader import load_artifacts
from .models import (
    ArtifactRecord,
    ChallengeRecord,
    FeedbackRecord,
    ImageRecord,
    RecognitionRecord,
    StoryRecord,
)


class JsonHeritageRepository:
    """Read canonical content from JSON and keep anonymous events in local SQLite."""

    def __init__(
        self,
        json_root: Path,
        image_root: Path,
        *,
        analytics_store: AnalyticsStore | None = None,
        analytics_path: Path | None = None,
        skip_missing_images: bool = False,
    ) -> None:
        self.json_root = json_root
        self.image_root = image_root
        self._artifacts = load_artifacts(
            json_root,
            image_root,
            skip_missing_images=skip_missing_images,
        )
        if analytics_store is not None and analytics_path is not None:
            raise ValueError("Pass analytics_store or analytics_path, not both")
        self._analytics = analytics_store or SqliteAnalyticsStore(
            analytics_path or json_root.parent / "data" / "analytics.sqlite3"
        )
        self._catalog = tuple(
            self._artifacts[item_id] for item_id in sorted(self._artifacts)
        )

    def get_artifact(self, item_id: str) -> ArtifactRecord | None:
        return self._artifacts.get(require_public_id(item_id))

    def list_artifacts(self) -> tuple[ArtifactRecord, ...]:
        return tuple(self._artifacts[item_id] for item_id in sorted(self._artifacts))

    def get_story(self, item_id: str) -> StoryRecord | None:
        artifact = self.get_artifact(item_id)
        return build_story(artifact) if artifact else None

    def get_images(self, item_id: str) -> tuple[ImageRecord, ...]:
        artifact = self.get_artifact(item_id)
        return artifact.images if artifact else ()

    def get_challenge(self, item_id: str) -> ChallengeRecord | None:
        artifact = self.get_artifact(item_id)
        if artifact is None:
            return None
        return build_artifact_challenge(artifact, self._catalog)

    def record_recognition(self, record: RecognitionRecord) -> None:
        self._analytics.record_recognition(record)

    def get_recognition(self, request_id: str) -> RecognitionRecord | None:
        return self._analytics.get_recognition(request_id)

    def record_feedback(self, record: FeedbackRecord) -> None:
        self._analytics.record_feedback(record)
