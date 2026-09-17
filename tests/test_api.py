from __future__ import annotations

import io
from dataclasses import replace
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from src.ai.schemas import NarrationResponse
from src.api.app import create_app
from src.api.recognizer import RecognitionUnavailableError
from src.api.settings import APISettings
from src.config import Settings
from src.repositories.content import build_story
from src.repositories.models import (
    ArtifactRecord,
    ChallengeOptionRecord,
    ChallengeRecord,
    HistoricalInfoRecord,
    ImageRecord,
    LocationRecord,
)


def _core_settings(tmp_path: Path) -> Settings:
    return Settings(
        project_root=tmp_path,
        image_root=tmp_path,
        json_root=tmp_path,
        clip_model_name="test-model",
        clip_pretrained="test-weights",
        clip_device="cpu",
        pinecone_api_key="placeholder",
        pinecone_index_name="existing-index",
        pinecone_namespace="existing-namespace",
        pinecone_cloud="aws",
        pinecone_region="test-region",
    )


def _artifact(tmp_path: Path, suffix: str, category: str) -> ArtifactRecord:
    item_id = f"artifact-{suffix}"
    filename = f"{item_id}.jpg"
    Image.new("RGB", (30, 30), (80, 100, 120)).save(tmp_path / filename)
    return ArtifactRecord(
        id=item_id,
        slug=item_id,
        name=f"Hiện vật {suffix.upper()}",
        category=category,
        tags=(category,),
        dataset_name="Di San Lens",
        dataset_version="1.0",
        location=LocationRecord("28 Vo Van Tan", "Ho Chi Minh", None, "Vietnam", None, None),
        historical_info=HistoricalInfoRecord(
            title=f"Hiện vật {suffix.upper()}",
            description=f"Mô tả dữ liệu gốc của hiện vật {suffix.upper()}.",
            historical_period="1954–1975",
            year=None,
            event=f"Sự kiện {suffix.upper()}",
            source=None,
            source_status="missing",
        ),
        images=(
            ImageRecord(
                id=f"{item_id}_01",
                item_id=item_id,
                filename=filename,
                relative_path=filename,
                drive_url=None,
                caption=f"Ảnh {suffix.upper()}",
                year=None,
                view="front",
                sort_order=0,
            ),
        ),
    )


class FakeRepository:
    def __init__(self, artifacts: list[ArtifactRecord]) -> None:
        self.artifacts = {artifact.id: artifact for artifact in artifacts}
        self.recognitions = []
        self.feedback = []

    def get_artifact(self, item_id):
        return self.artifacts.get(item_id)

    def list_artifacts(self):
        return tuple(self.artifacts.values())

    def get_story(self, item_id):
        item = self.get_artifact(item_id)
        return build_story(item) if item else None

    def get_images(self, item_id):
        item = self.get_artifact(item_id)
        return item.images if item else ()

    def get_challenge(self, item_id):
        if item_id not in self.artifacts:
            return None
        options = (
            ChallengeOptionRecord("option-1", "Nhóm A", True, 0),
            ChallengeOptionRecord("option-2", "Nhóm B", False, 1),
        )
        return ChallengeRecord(
            "challenge-1", item_id, "single_choice", "Hiện vật thuộc nhóm nào?", options,
            "Câu trả lời dựa trên trường category.", "category"
        )

    def record_recognition(self, record):
        self.recognitions.append(record)

    def record_feedback(self, record):
        self.feedback.append(record)


class FakeEngine:
    def __init__(self, matches, *, error=False) -> None:
        self.matches = matches
        self.error = error
        self.query_calls = 0
        self.loaded = False

    def warmup(self):
        self.loaded = True
        if self.error:
            raise RecognitionUnavailableError("SDK details must stay private")
        return "test-model:test-weights", 512

    def query(self, _image, top_k):
        self.query_calls += 1
        self.requested_top_k = top_k
        if self.error:
            raise RecognitionUnavailableError("SDK details must stay private")
        return self.matches, {"clip": 2.0, "pinecone": 3.0}


def _match(item: str, score: float, view: int = 1) -> dict:
    return {
        "id": f"{item}:{item}_{view:02d}",
        "score": score,
        "metadata": {"item_id": item, "image_id": f"{item}_01"},
    }


def _query_png() -> bytes:
    y, x = np.indices((400, 400))
    mask = ((x // 8 + y // 8) % 2)[..., None]
    pixels = np.where(mask, np.array([50, 80, 140]), np.array([190, 140, 70])).astype(np.uint8)
    buffer = io.BytesIO()
    Image.fromarray(pixels).save(buffer, "PNG")
    return buffer.getvalue()


def _client(
    tmp_path: Path,
    matches,
    api_settings=None,
    *,
    error=False,
    learning_service=None,
    narration_service=None,
):
    artifacts = [
        _artifact(tmp_path, "a", "category-a"),
        _artifact(tmp_path, "b", "category-b"),
        _artifact(tmp_path, "c", "category-c"),
    ]
    repository = FakeRepository(artifacts)
    engine = FakeEngine(matches, error=error)
    app = create_app(
        api_settings=api_settings or APISettings(),
        core_settings=_core_settings(tmp_path),
        repository=repository,
        recognition_engine=engine,
        learning_service=learning_service,
        narration_service=narration_service,
    )
    return TestClient(app, raise_server_exceptions=False), repository, engine


def test_recognition_accepts_deduplicates_and_does_not_save_upload(tmp_path: Path) -> None:
    client, repository, engine = _client(
        tmp_path,
        [
            _match("artifact-a", 0.91, 1),
            _match("artifact-a", 0.90, 2),
            _match("artifact-b", 0.72),
            _match("artifact-c", 0.63),
        ],
    )
    before = {path.name for path in tmp_path.iterdir()}
    response = client.post(
        "/api/v1/recognitions", files={"file": ("query.png", _query_png(), "image/png")}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["recognition_status"] == "accepted"
    assert body["selected_item"]["item_id"] == "artifact-a"
    assert [entry["item_id"] for entry in body["candidates"]] == [
        "artifact-a", "artifact-b", "artifact-c"
    ]
    assert body["top_score"] == 0.91
    assert engine.requested_top_k == 50
    assert len(repository.recognitions) == 1
    assert {path.name for path in tmp_path.iterdir()} == before


def test_health_readiness_and_explicit_warmup(tmp_path: Path) -> None:
    client, _, engine = _client(tmp_path, [])
    assert client.get("/api/v1/health").json()["status"] == "ok"
    readiness = client.get("/api/v1/health/ready").json()
    assert readiness["status"] == "not_ready"
    assert readiness["model_loaded"] is False
    assert readiness["index_verified_at_load"] is False

    warmup = client.post("/api/v1/warmup")
    assert warmup.status_code == 200
    assert warmup.json()["embedding_dimension"] == 512
    assert engine.loaded is True
    assert client.get("/api/v1/health/ready").json()["status"] == "ready"


def test_recognition_three_states_and_quality_short_circuit(tmp_path: Path) -> None:
    # Separate directories keep media fixtures independent.
    needs_dir = tmp_path / "needs"
    needs_dir.mkdir()
    client, _, _ = _client(needs_dir, [_match("artifact-a", 0.80), _match("artifact-b", 0.76)])
    body = client.post(
        "/api/v1/recognitions", files={"file": ("query.png", _query_png(), "image/png")}
    ).json()
    assert body["recognition_status"] == "needs_confirmation"
    assert body["selected_item"] is None

    low_dir = tmp_path / "low"
    low_dir.mkdir()
    client, _, _ = _client(low_dir, [_match("artifact-a", 0.40), _match("artifact-b", 0.30)])
    body = client.post(
        "/api/v1/recognitions", files={"file": ("query.png", _query_png(), "image/png")}
    ).json()
    assert body["recognition_status"] == "rejected"
    assert body["candidates"] == []

    quality_dir = tmp_path / "quality"
    quality_dir.mkdir()
    client, _, engine = _client(quality_dir, [_match("artifact-a", 0.99)])
    dark = io.BytesIO()
    Image.new("RGB", (400, 400), (5, 5, 5)).save(dark, "PNG")
    body = client.post(
        "/api/v1/recognitions", files={"file": ("dark.png", dark.getvalue(), "image/png")}
    ).json()
    assert body["recognition_status"] == "rejected"
    assert body["quality"]["status"] == "failed"
    assert engine.query_calls == 0


def test_invalid_file_limits_and_safe_external_error(tmp_path: Path) -> None:
    invalid_dir = tmp_path / "invalid"
    invalid_dir.mkdir()
    client, _, _ = _client(invalid_dir, [])
    response = client.post(
        "/api/v1/recognitions", files={"file": ("fake.jpg", b"not an image", "image/jpeg")}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_image"

    limit_dir = tmp_path / "limit"
    limit_dir.mkdir()
    client, _, _ = _client(limit_dir, [], replace(APISettings(), max_upload_bytes=10))
    assert client.post(
        "/api/v1/recognitions", files={"file": ("big.png", _query_png(), "image/png")}
    ).status_code == 413

    pixels_dir = tmp_path / "pixels"
    pixels_dir.mkdir()
    client, _, _ = _client(pixels_dir, [], replace(APISettings(), max_image_pixels=100))
    tiny = io.BytesIO()
    Image.new("RGB", (11, 10)).save(tiny, "PNG")
    assert client.post(
        "/api/v1/recognitions", files={"file": ("pixels.png", tiny.getvalue(), "image/png")}
    ).status_code == 413

    error_dir = tmp_path / "error"
    error_dir.mkdir()
    client, _, _ = _client(error_dir, [], error=True)
    response = client.post(
        "/api/v1/recognitions", files={"file": ("query.png", _query_png(), "image/png")}
    )
    assert response.status_code == 503
    assert "SDK details" not in response.text


def test_content_story_challenge_media_and_feedback(tmp_path: Path) -> None:
    client, repository, _ = _client(
        tmp_path, [_match("artifact-a", 0.91), _match("artifact-b", 0.70)]
    )
    artifact = client.get("/api/v1/artifacts/artifact-a")
    assert artifact.status_code == 200
    assert artifact.headers["content-type"] == "application/json; charset=utf-8"
    assert artifact.json()["source_verified"] is False
    assert artifact.json()["source"] is None
    assert artifact.json()["images"][0]["url"].startswith("/media/")

    story = client.get("/api/v1/artifacts/artifact-a/story").json()
    assert story["item_id"] == "artifact-a"
    assert story["overview"]["description"] == "Mô tả dữ liệu gốc của hiện vật A."
    assert story["overview"]["event"] == "Sự kiện A"
    assert story["deep"]["source_verified"] is False
    assert story["deep"]["source"] is None

    learning = client.post("/api/v1/artifacts/artifact-a/learning-content")
    assert learning.status_code == 200
    assert learning.json()["generation_status"] == "fallback_missing_source"
    assert learning.json()["cache_status"] == "bypass"
    assert learning.json()["content"]["mindmap"]["central_label"] == "Hiện vật A"
    assert "chưa có đủ nguồn kiểm chứng" in learning.json()["notice"]

    narration = client.post(
        "/api/v1/artifacts/artifact-a/narrations", json={"variant": "short"}
    )
    assert narration.status_code == 200
    assert narration.json()["status"] == "fallback_required"
    assert narration.json()["audio_url"] is None
    assert narration.json()["transcript"]
    assert client.post(
        "/api/v1/artifacts/artifact-a/narrations", json={"variant": "invalid"}
    ).status_code == 422

    challenge = client.get("/api/v1/artifacts/artifact-a/challenge").json()
    assert challenge["item_id"] == "artifact-a"
    assert challenge["correct_option_id"] == "option-1"
    assert all("is_correct" not in option for option in challenge["options"])

    assert client.get("/api/v1/artifacts/artifact-a/images/artifact-a_01").status_code == 200
    thumbnail = client.get("/media/artifact-a.jpg?width=640")
    assert thumbnail.status_code == 200
    assert thumbnail.headers["content-type"].startswith("image/webp")
    assert "etag" in thumbnail.headers
    assert client.get(
        "/media/artifact-a.jpg?width=640",
        headers={"If-None-Match": thumbnail.headers["etag"]},
    ).status_code == 304
    assert client.get("/media/artifact-a.jpg?width=777").status_code == 400
    assert client.get("/api/v1/artifacts/missing").status_code == 404
    assert client.post("/api/v1/artifacts/missing/learning-content").status_code == 404

    recognition = client.post(
        "/api/v1/recognitions", files={"file": ("query.png", _query_png(), "image/png")}
    ).json()
    request_id = recognition["request_id"]
    feedback = client.post(
        f"/api/v1/recognitions/{request_id}/feedback", json={"is_correct": True}
    )
    assert feedback.status_code == 201
    assert repository.feedback[0].selected_item_id == "artifact-a"
    assert client.post(
        f"/api/v1/recognitions/{request_id}/feedback", json={"is_correct": True}
    ).status_code == 409


def test_feedback_rejects_client_supplied_item_outside_server_context(tmp_path: Path) -> None:
    client, _, _ = _client(
        tmp_path, [_match("artifact-a", 0.80), _match("artifact-b", 0.77)]
    )
    recognition = client.post(
        "/api/v1/recognitions", files={"file": ("query.png", _query_png(), "image/png")}
    ).json()
    response = client.post(
        f"/api/v1/recognitions/{recognition['request_id']}/feedback",
        json={"is_correct": False, "selected_item_id": "artifact-z"},
    )
    assert response.status_code == 422


def test_cached_narration_audio_supports_etag_and_range(tmp_path: Path) -> None:
    asset_id = "a" * 64
    audio_path = tmp_path / f"{asset_id}.wav"
    audio_path.write_bytes(b"RIFF" + b"\x00" * 60)

    class FakeNarrationService:
        def create(self, artifact_id: str, variant: str) -> NarrationResponse:
            return NarrationResponse(
                artifact_id=artifact_id,
                variant=variant,
                status="ready",
                cache_status="hit",
                transcript="Bản thuyết minh kiểm thử.",
                asset_id=asset_id,
                audio_url=f"/api/v1/narrations/{asset_id}/audio",
                mime_type="audio/wav",
                notice="Giọng đọc AI kiểm thử.",
            )

        def get_audio_path(self, requested_id: str):
            return audio_path if requested_id == asset_id else None

    client, _, _ = _client(
        tmp_path,
        [],
        narration_service=FakeNarrationService(),
    )
    created = client.post(
        "/api/v1/artifacts/artifact-a/narrations", json={"variant": "full"}
    )
    assert created.status_code == 200
    assert created.json()["asset_id"] == asset_id

    audio = client.get(f"/api/v1/narrations/{asset_id}/audio")
    assert audio.status_code == 200
    assert audio.headers["content-type"].startswith("audio/wav")
    assert audio.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert client.get(
        f"/api/v1/narrations/{asset_id}/audio",
        headers={"If-None-Match": audio.headers["etag"]},
    ).status_code == 304
    partial = client.get(
        f"/api/v1/narrations/{asset_id}/audio",
        headers={"Range": "bytes=0-3"},
    )
    assert partial.status_code == 206
    assert partial.content == b"RIFF"
