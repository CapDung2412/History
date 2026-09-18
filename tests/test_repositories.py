from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest

from src.repositories import (
    FeedbackRecord,
    JsonHeritageRepository,
    RecognitionRecord,
    RepositoryIntegrityError,
    RepositoryUnavailableError,
    SupabaseHeritageRepository,
    build_repository,
)
from src.repositories.fallback import FallbackHeritageRepository


def make_dataset(tmp_path: Path) -> tuple[Path, Path]:
    json_root = tmp_path / "JSON"
    image_root = tmp_path / "images"
    json_root.mkdir()
    image_root.mkdir()
    categories = [
        "historical_photograph",
        "military_artifact",
        "historical_map",
        "exhibition_panel",
    ]
    for index, category in enumerate(categories, start=1):
        item_id = f"item-{index}"
        filename = f"{item_id}_01.jpg"
        (image_root / filename).write_bytes(b"fixture")
        source = "https://museum.example/source" if index == 2 else None
        document = {
            "dataset_name": "Fixture",
            "version": "1.0",
            "locations": [
                {
                    "id": item_id,
                    "name": f"Hiện vật {index}",
                    "slug": item_id,
                    "category": category,
                    "tags": ["chu-de", f"nhom-{index}"],
                    "location": {
                        "address": "28 Võ Văn Tần",
                        "city": "Thành phố Hồ Chí Minh",
                        "province": "Thành phố Hồ Chí Minh",
                        "country": "Vietnam",
                        "latitude": None,
                        "longitude": None,
                    },
                    "historical_info": {
                        "title": f"Hiện vật {index}",
                        "description": f"Mô tả dữ liệu gốc của hiện vật {index}.",
                        "historical_period": "Giai đoạn thử nghiệm",
                        "year": 1960 + index,
                        "event": f"Sự kiện {index}",
                        "source": source,
                    },
                    "images": [
                        {
                            "id": f"{item_id}_01",
                            "filename": filename,
                            "drive_url": None,
                            "caption": f"Ảnh {index}",
                            "year": 1960 + index,
                            "view": "toan-canh",
                        }
                    ],
                }
            ],
        }
        (json_root / f"{item_id}.json").write_text(
            json.dumps(document, ensure_ascii=False), encoding="utf-8"
        )
    return json_root, image_root


def test_json_repository_preserves_content_and_marks_missing_source(tmp_path: Path) -> None:
    json_root, image_root = make_dataset(tmp_path)
    repository = JsonHeritageRepository(json_root, image_root)

    artifact = repository.get_artifact("item-1")
    assert artifact is not None
    assert artifact.historical_info.description == "Mô tả dữ liệu gốc của hiện vật 1."
    assert artifact.historical_info.source is None
    assert artifact.historical_info.source_status == "missing"
    assert artifact.images[0].relative_path == "item-1_01.jpg"

    story = repository.get_story("item-1")
    assert story is not None
    assert story.quick["name"] == "Hiện vật 1"
    assert story.deep["sources"] == []
    assert story.deep["source_notice"] == "Nguồn tư liệu đang được bổ sung"

    sourced = repository.get_artifact("item-2")
    assert sourced is not None
    assert sourced.historical_info.source_status == "available"
    assert sourced.sources[0].url == "https://museum.example/source"
    sourced_story = repository.get_story("item-2")
    assert sourced_story is not None
    assert sourced_story.deep["source_status"] == "available"
    assert "chưa được xác minh" in sourced_story.deep["source_notice"]


def test_json_repository_requires_explicit_consistent_source_verification(
    tmp_path: Path,
) -> None:
    json_root, image_root = make_dataset(tmp_path)
    path = json_root / "item-2.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["locations"][0]["historical_info"]["source_status"] = "verified"
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

    artifact = JsonHeritageRepository(json_root, image_root).get_artifact("item-2")
    assert artifact is not None
    assert artifact.historical_info.source_status == "verified"

    document["locations"][0]["historical_info"]["source"] = None
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(RepositoryIntegrityError, match="cannot mark an empty source"):
        JsonHeritageRepository(json_root, image_root)


def test_json_challenge_is_deterministic_and_uses_multiple_canonical_fields(
    tmp_path: Path,
) -> None:
    json_root, image_root = make_dataset(tmp_path)
    repository = JsonHeritageRepository(json_root, image_root)

    first = repository.get_challenge("item-1")
    second = repository.get_challenge("item-1")
    assert first == second
    assert first is not None
    assert len(first.options) == 4
    assert len(first.additional_questions) == 2
    assert len({first.id, *(question.id for question in first.additional_questions)}) == 3
    assert sum(option.is_correct for option in first.options) == 1
    assert first.source_field == "historical_info.event"

    challenges = [repository.get_challenge(f"item-{index}") for index in range(1, 5)]
    assert all(challenge is not None for challenge in challenges)
    assert {challenge.source_field for challenge in challenges if challenge} == {
        "category",
        "historical_info.description",
        "historical_info.event",
        "historical_info.year",
    }

    description_challenge = repository.get_challenge("item-3")
    assert description_challenge is not None
    correct_option = next(option for option in description_challenge.options if option.is_correct)
    assert correct_option.label == "Mô tả dữ liệu gốc của hiện vật 3."


def test_invalid_public_id_is_rejected(tmp_path: Path) -> None:
    json_root, image_root = make_dataset(tmp_path)
    repository = JsonHeritageRepository(json_root, image_root)
    with pytest.raises(ValueError):
        repository.get_artifact("../item-1")


def test_local_feedback_is_bound_to_server_request_context(tmp_path: Path) -> None:
    json_root, image_root = make_dataset(tmp_path)
    database = tmp_path / "analytics.sqlite3"
    repository = JsonHeritageRepository(json_root, image_root, analytics_path=database)
    request_id = str(uuid4())
    repository.record_recognition(
        RecognitionRecord(
            request_id=request_id,
            status="needs_confirmation",
            candidate_ids=("item-1", "item-2", "item-3"),
            top1_score=0.61,
            score_margin=0.02,
        )
    )

    with pytest.raises(ValueError, match="not offered"):
        repository.record_feedback(
            FeedbackRecord(request_id=request_id, is_correct=False, selected_item_id="item-4")
        )

    repository.record_feedback(
        FeedbackRecord(request_id=request_id, is_correct=False, selected_item_id="item-2")
    )
    with sqlite3.connect(database) as connection:
        stored = connection.execute(
            "SELECT selected_item_id, no_match FROM recognition_feedback"
        ).fetchone()
    assert stored == ("item-2", 0)


class UnavailableRepository:
    def __getattr__(self, _name: str):
        def unavailable(*_args, **_kwargs):
            raise RepositoryUnavailableError("offline")

        return unavailable


class BrokenRepository(UnavailableRepository):
    def get_artifact(self, _item_id: str):
        raise RepositoryIntegrityError("bad rows")


def test_fallback_only_handles_unavailable_repository(tmp_path: Path) -> None:
    json_root, image_root = make_dataset(tmp_path)
    fallback = JsonHeritageRepository(json_root, image_root)
    repository = FallbackHeritageRepository(UnavailableRepository(), fallback)  # type: ignore[arg-type]
    assert repository.get_artifact("item-1") == fallback.get_artifact("item-1")

    broken = FallbackHeritageRepository(BrokenRepository(), fallback)  # type: ignore[arg-type]
    with pytest.raises(RepositoryIntegrityError):
        broken.get_artifact("item-1")


class FeedbackTransport:
    def __init__(self) -> None:
        self.inserts: list[tuple[str, list[dict], str | None]] = []

    def select(self, table: str, **_kwargs):
        if table == "recognition_requests":
            return [{"candidate_ids": ["item-1", "item-2"], "resolved_item_id": "item-1"}]
        return []

    def insert(self, table: str, rows: list[dict], *, on_conflict: str | None = None):
        self.inserts.append((table, rows, on_conflict))


def test_supabase_feedback_does_not_trust_arbitrary_item_id() -> None:
    transport = FeedbackTransport()
    repository = SupabaseHeritageRepository(transport=transport)
    request_id = str(uuid4())
    with pytest.raises(ValueError, match="not offered"):
        repository.record_feedback(
            FeedbackRecord(request_id=request_id, is_correct=False, selected_item_id="item-9")
        )
    assert transport.inserts == []


@pytest.mark.parametrize("use_supabase", [False, True])
def test_correct_feedback_must_refer_to_server_prediction(tmp_path: Path, use_supabase: bool) -> None:
    request_id = str(uuid4())
    if use_supabase:
        repository = SupabaseHeritageRepository(transport=FeedbackTransport())
    else:
        json_root, image_root = make_dataset(tmp_path)
        repository = JsonHeritageRepository(json_root, image_root)
        repository.record_recognition(
            RecognitionRecord(
                request_id=request_id, status="accepted",
                candidate_ids=("item-1", "item-2"), resolved_item_id="item-1",
            )
        )
    with pytest.raises(ValueError, match="recognized result"):
        repository.record_feedback(
            FeedbackRecord(request_id=request_id, is_correct=True, selected_item_id="item-2")
        )


class RecoveringTransport:
    def __init__(self) -> None:
        self.offline = False
        self.requests: dict[str, dict] = {}
        self.feedback: dict[str, dict] = {}

    def select(self, table: str, *, filters: dict[str, str], **kwargs):
        if self.offline:
            raise RepositoryUnavailableError("offline")
        request_id = filters["request_id"].removeprefix("eq.")
        value = self.requests.get(request_id)
        return [value] if value else []

    def insert(self, table: str, rows: list[dict], *, on_conflict: str | None = None):
        if self.offline:
            raise RepositoryUnavailableError("offline")
        for row in rows:
            request_id = row["request_id"]
            target = self.requests if table == "recognition_requests" else self.feedback
            if request_id in target and on_conflict != "request_id":
                raise RepositoryIntegrityError("duplicate request")
            target[request_id] = row


@pytest.mark.parametrize("request_offline,feedback_offline", [(False, True), (True, False), (False, False)])
def test_fallback_keeps_durable_request_and_feedback_across_outages_and_restart(
    tmp_path: Path, request_offline: bool, feedback_offline: bool,
) -> None:
    json_root, image_root = make_dataset(tmp_path)
    analytics_path = tmp_path / "analytics.sqlite3"
    transport = RecoveringTransport()
    transport.offline = request_offline
    repository = build_repository(
        json_root, image_root, analytics_path=analytics_path, supabase_transport=transport,
    )
    request_id = str(uuid4())
    recognition = RecognitionRecord(
        request_id=request_id, status="needs_confirmation", candidate_ids=("item-1", "item-2"),
    )
    repository.record_recognition(recognition)

    # Recreate adapters to prove routing does not depend on a process-local map.
    repository = build_repository(
        json_root, image_root, analytics_path=analytics_path, supabase_transport=transport,
    )
    transport.offline = feedback_offline
    feedback = FeedbackRecord(request_id=request_id, is_correct=False, selected_item_id="item-2")
    repository.record_feedback(feedback)
    with sqlite3.connect(analytics_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM recognition_requests").fetchone() == (1,)
        assert connection.execute("SELECT selected_item_id FROM recognition_feedback").fetchone() == ("item-2",)
    if not feedback_offline:
        assert len(transport.requests) == 1
        assert len(transport.feedback) == 1
    with pytest.raises(RepositoryIntegrityError, match="already exists"):
        repository.record_feedback(feedback)


def test_local_request_uuid_is_canonicalized(tmp_path: Path) -> None:
    json_root, image_root = make_dataset(tmp_path)
    repository = JsonHeritageRepository(json_root, image_root)
    request_id = str(uuid4())
    repository.record_recognition(
        RecognitionRecord(request_id=request_id.upper(), status="rejected")
    )
    context = repository.get_recognition(request_id)
    assert context is not None and context.request_id == request_id
    repository.record_feedback(FeedbackRecord(request_id=request_id, is_correct=False, no_match=True))


def test_factory_uses_json_without_complete_supabase_configuration(tmp_path: Path) -> None:
    json_root, image_root = make_dataset(tmp_path)
    repository = build_repository(
        json_root,
        image_root,
        supabase_url="https://project.supabase.co",
        service_role_key=None,
    )
    assert isinstance(repository, JsonHeritageRepository)
