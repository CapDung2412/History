from __future__ import annotations

import io
import threading
import wave
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.ai.cache import AudioFileCache, LearningCacheRecord, SQLiteLearningContentCache
from src.ai.curated_videos import curated_videos_for
from src.ai.evidence import (
    EvidenceValidationError,
    build_evidence_catalog,
    build_fallback_content,
    ground_web_evidence,
    repair_generated_grounding,
    validate_generated_content,
)
from src.ai.providers import ProviderInvalidResponseError, ProviderUnavailableError
from src.ai.schemas import (
    DeepSection,
    GeneratedLearningContent,
    RelatedVideo,
    RelatedVideoDiscovery,
    WebEvidence,
)
from src.ai.service import LearningService, NarrationService
from src.repositories.models import (
    ArtifactRecord,
    HistoricalInfoRecord,
    ImageRecord,
    LocationRecord,
)


def _artifact(*, source: str | None, source_status: str) -> ArtifactRecord:
    return ArtifactRecord(
        id="artifact-test",
        slug="artifact-test",
        name="Bản đồ thử nghiệm",
        category="map",
        tags=("bản đồ", "tư liệu"),
        dataset_name="Di San Lens",
        dataset_version="1",
        location=LocationRecord(None, "Thành phố Hồ Chí Minh", None, "Việt Nam", None, None),
        historical_info=HistoricalInfoRecord(
            title="Bản đồ thử nghiệm",
            description="Bản đồ được mô tả trong hồ sơ thử nghiệm.",
            historical_period="Giai đoạn thử nghiệm",
            year=1975,
            event="Sự kiện thử nghiệm",
            source=source,
            source_status=source_status,
        ),
        images=(
            ImageRecord(
                id="artifact-test_01",
                item_id="artifact-test",
                filename="artifact-test.jpg",
                relative_path="artifact-test.jpg",
                drive_url=None,
                caption="Ảnh bản đồ trong hồ sơ",
                year=1975,
                view="front",
                sort_order=0,
            ),
        ),
    )


class Repository:
    def __init__(self, artifact: ArtifactRecord) -> None:
        self.artifact = artifact

    def get_artifact(self, item_id: str):
        return self.artifact if item_id == self.artifact.id else None


class StaticLearningCache:
    def __init__(self, record: LearningCacheRecord) -> None:
        self.record = record
        self.puts: list[LearningCacheRecord] = []

    def get(self, _cache_key: str) -> LearningCacheRecord:
        return self.record

    def put(self, record: LearningCacheRecord) -> None:
        self.puts.append(record)


def _target_artifact() -> ArtifactRecord:
    artifact = _artifact(source="Nguồn lưu trữ đã xác minh", source_status="verified")
    return replace(
        artifact,
        id="tuong-ba-me-bang-manh-bom",
        slug="tuong-ba-me-bang-manh-bom",
        name="Tượng bà mẹ bằng mảnh bom",
        historical_info=replace(
            artifact.historical_info,
            title="Tượng bà mẹ bằng mảnh bom",
            description=(
                "Tượng bà mẹ được tạo từ mảnh bom và trưng bày tại Bảo tàng "
                "Chứng tích Chiến tranh."
            ),
        ),
    )


class ContentProvider:
    model_name = "test-content-model"

    def __init__(self, artifact: ArtifactRecord, *, invalid: bool = False) -> None:
        catalog = build_evidence_catalog(artifact)
        self.content = build_fallback_content(artifact, catalog)
        self.content = self.content.model_copy(
            update={
                "web_evidence": [
                    WebEvidence(
                        ref="web.1",
                        title="Nguồn web kiểm thử",
                        url="https://example.org/heritage-source",
                        evidence_text=artifact.historical_info.description or artifact.name,
                    )
                ]
            }
        )
        self.content.factual_claims[0].evidence_refs.append("web.1")
        self.source_status = catalog.source_status
        self.artifact_id = artifact.id
        self.invalid = invalid
        self.calls = 0
        self.search_modes: list[bool] = []

    def generate(
        self,
        *,
        artifact_id: str,
        normalized_input: dict,
        use_web_search: bool = False,
    ):
        self.calls += 1
        assert artifact_id == self.artifact_id
        assert normalized_input["source_status"] == self.source_status
        self.search_modes.append(use_web_search)
        if self.invalid:
            raise ProviderInvalidResponseError()
        return self.content


class TrustedVideoContentProvider(ContentProvider):
    def __init__(self, artifact: ArtifactRecord, *, unavailable: bool = False) -> None:
        super().__init__(artifact)
        self.video_calls = 0
        self.video_unavailable = unavailable

    def discover_related_videos(
        self,
        *,
        artifact_id: str,
        normalized_input: dict,
    ) -> RelatedVideoDiscovery:
        self.video_calls += 1
        assert artifact_id == self.artifact_id
        assert normalized_input["artifact_id"] == artifact_id
        if self.video_unavailable:
            raise ProviderUnavailableError()
        youtube_url = "https://www.youtube.com/watch?v=AbCdEfGhI12"
        return RelatedVideoDiscovery(
            related_videos=[
                RelatedVideo(
                    title="Bản đồ thử nghiệm qua tư liệu bảo tàng",
                    url=youtube_url,
                    channel_name="Bảo tàng Lịch sử Quốc gia",
                    trust_level="official",
                    trust_reason=(
                        "Bảo tàng Lịch sử Quốc gia là cơ quan bảo tàng công bố video."
                    ),
                    scope="exact_artifact",
                    relevance="Video giới thiệu trực tiếp Bản đồ thử nghiệm.",
                    evidence_refs=["web.1"],
                )
            ],
            web_evidence=[
                WebEvidence(
                    ref="web.1",
                    title="Bản đồ thử nghiệm qua tư liệu bảo tàng",
                    url=youtube_url,
                    evidence_text="Video giới thiệu trực tiếp Bản đồ thử nghiệm.",
                )
            ],
        )


class SpeechProvider:
    model_name = "test-tts-model"
    voice_name = "test-voice"
    language = "vi-VN"
    instructions = "Đọc hoàn toàn bằng tiếng Việt."

    def __init__(self) -> None:
        self.calls = 0

    def synthesize(self, text: str) -> bytes:
        self.calls += 1
        assert text
        output = io.BytesIO()
        with wave.open(output, "wb") as writer:
            writer.setnchannels(1)
            writer.setsampwidth(2)
            writer.setframerate(8_000)
            writer.writeframes(b"\x00\x00" * 80)
        return output.getvalue()


def _learning_service(
    tmp_path: Path,
    artifact: ArtifactRecord,
    provider,
    *,
    prompt_version: str = "prompt-v1",
) -> LearningService:
    repository = Repository(artifact)
    return LearningService(
        lambda: repository,
        provider=provider,
        cache=SQLiteLearningContentCache(tmp_path / "learning.sqlite3"),
        prompt_version=prompt_version,
        schema_version="schema-v1",
    )


def test_missing_and_unverified_sources_use_web_search_and_return_sources(tmp_path: Path) -> None:
    for index, artifact in enumerate(
        (
            _artifact(source=None, source_status="missing"),
            _artifact(source="Nguồn chưa xác minh", source_status="available_unverified"),
        )
    ):
        provider = ContentProvider(artifact)
        service = _learning_service(tmp_path / str(index), artifact, provider)
        response = service.get("artifact-test")
        assert response.generation_status == "generated"
        assert response.cache_status == "miss"
        assert provider.calls == 1
        assert provider.search_modes == [True]
        assert any(reference.ref == "web.1" for reference in response.references)


def test_verified_content_uses_web_search_for_related_resources_and_is_cached(
    tmp_path: Path,
) -> None:
    artifact = _artifact(source="Hồ sơ lưu trữ đã xác minh", source_status="verified")
    provider = ContentProvider(artifact)
    service = _learning_service(tmp_path, artifact, provider)

    first = service.get("artifact-test")
    second = service.get("artifact-test")

    assert first.generation_status == "generated"
    assert first.cache_status == "miss"
    assert second.cache_status == "hit"
    assert provider.calls == 1
    assert provider.search_modes == [True]


def test_missing_video_gets_one_trusted_search_then_is_cached(tmp_path: Path) -> None:
    artifact = _artifact(source="Nguồn lưu trữ đã xác minh", source_status="verified")
    provider = TrustedVideoContentProvider(artifact)
    service = _learning_service(tmp_path, artifact, provider, prompt_version="prompt-v8")

    first = service.get("artifact-test")
    second = service.get("artifact-test")

    assert first.cache_status == "miss"
    assert second.cache_status == "hit"
    assert provider.calls == 1
    assert provider.video_calls == 1
    assert len(first.content.related_videos) == 1
    video = first.content.related_videos[0]
    assert video.channel_name == "Bảo tàng Lịch sử Quốc gia"
    assert video.trust_level == "official"
    assert video.evidence_refs == ["web.2"]
    assert any(reference.ref == "web.2" for reference in first.references)
    assert second.content.related_videos == first.content.related_videos


def test_trusted_video_search_failure_keeps_content_and_caches_result(
    tmp_path: Path,
) -> None:
    artifact = _artifact(source="Nguồn lưu trữ đã xác minh", source_status="verified")
    provider = TrustedVideoContentProvider(artifact, unavailable=True)
    service = _learning_service(tmp_path, artifact, provider, prompt_version="prompt-v8")

    first = service.get("artifact-test")
    second = service.get("artifact-test")

    assert first.generation_status == "generated"
    assert first.content.related_videos == []
    assert second.cache_status == "hit"
    assert provider.calls == 1
    assert provider.video_calls == 1


def test_curated_video_selector_is_narrow_and_scope_aware() -> None:
    assert curated_videos_for("unrelated-artifact") == ()

    target = curated_videos_for("tuong-ba-me-bang-manh-bom")
    assert len(target) == 3
    assert [video.scope for video in target] == [
        "site_or_museum",
        "site_or_museum",
        "broader_context",
    ]
    assert all("không" in video.relevance.casefold() for video in target)

    museum = curated_videos_for(
        "another-museum-artifact",
        location_address="28 Võ Văn Tần, Quận 3, Thành phố Hồ Chí Minh",
    )
    assert len(museum) == 2
    assert all(video.channel_name == "HTV Tin Tức" for video in museum)

    explosive_context = curated_videos_for(
        "another-explosive-artifact",
        description="Hiện vật phản ánh hậu quả bom mìn sau chiến tranh.",
    )
    assert len(explosive_context) == 1
    assert explosive_context[0].channel_name == "VTV24"
    assert explosive_context[0].scope == "broader_context"


def test_target_uses_curated_videos_without_second_provider_call(
    tmp_path: Path,
) -> None:
    artifact = _target_artifact()
    provider = TrustedVideoContentProvider(artifact)
    service = _learning_service(tmp_path, artifact, provider, prompt_version="prompt-v8")

    first = service.get(artifact.id)
    second = service.get(artifact.id)

    assert first.cache_status == "miss"
    assert second.cache_status == "hit"
    assert provider.calls == 1
    assert provider.video_calls == 0
    assert len(first.content.related_videos) == 3
    assert all(
        video.evidence_refs[0].startswith("curated.video.")
        for video in first.content.related_videos
    )
    curated_references = [
        reference
        for reference in first.references
        if reference.provenance == "editorial_curated"
    ]
    assert len(curated_references) == 3
    assert all(reference.source_status == "verified" for reference in curated_references)


def test_v8_cache_hit_without_videos_gets_curated_overlay_without_provider_call() -> None:
    artifact = _target_artifact()
    catalog = build_evidence_catalog(artifact)
    content = build_fallback_content(artifact, catalog).model_copy(deep=True)
    content.web_evidence = [
        WebEvidence(
            ref="web.1",
            title="Nguồn web kiểm thử",
            url="https://example.org/heritage-source",
            evidence_text=artifact.historical_info.description or artifact.name,
        )
    ]
    content.factual_claims[0].evidence_refs.append("web.1")
    provider = ContentProvider(artifact)
    cache = StaticLearningCache(
        LearningCacheRecord(
            cache_key="0" * 64,
            artifact_id=artifact.id,
            input_hash=catalog.input_hash,
            prompt_version="prompt-v8",
            schema_version="schema-v1",
            model=provider.model_name,
            locale="vi-VN",
            content=content,
        )
    )
    service = LearningService(
        lambda: Repository(artifact),
        provider=provider,
        cache=cache,
        prompt_version="prompt-v8",
        schema_version="schema-v1",
    )

    response = service.get(artifact.id)

    assert response.cache_status == "hit"
    assert provider.calls == 0
    assert len(response.content.related_videos) == 3
    assert len(
        [ref for ref in response.references if ref.provenance == "editorial_curated"]
    ) == 3


def test_dynamic_video_remains_preferred_over_curated_target(tmp_path: Path) -> None:
    artifact = _target_artifact()
    provider = ContentProvider(artifact)
    dynamic_url = "https://www.youtube.com/watch?v=AbCdEfGhI12"
    provider.content.web_evidence = [
        WebEvidence(
            ref="web.1",
            title="Video động đã được nguồn tìm kiếm xác nhận",
            url=dynamic_url,
            evidence_text=artifact.historical_info.description or artifact.name,
        )
    ]
    provider.content.related_videos = [
        RelatedVideo(
            title="Video động đã được nguồn tìm kiếm xác nhận",
            url=dynamic_url,
            channel_name="Bảo tàng Kiểm thử",
            trust_level="official",
            trust_reason="Bảo tàng Kiểm thử là đơn vị trực tiếp công bố video này.",
            scope="exact_artifact",
            relevance="Video động trình bày trực tiếp hiện vật được nhận diện.",
            evidence_refs=["web.1"],
        )
    ]
    service = _learning_service(tmp_path, artifact, provider, prompt_version="prompt-v8")

    response = service.get(artifact.id)

    assert [video.url for video in response.content.related_videos] == [dynamic_url]
    assert not any(
        reference.provenance == "editorial_curated"
        for reference in response.references
    )


def test_content_or_prompt_change_invalidates_learning_cache(tmp_path: Path) -> None:
    artifact = _artifact(source="Hồ sơ lưu trữ đã xác minh", source_status="verified")
    first_provider = ContentProvider(artifact)
    _learning_service(tmp_path, artifact, first_provider).get("artifact-test")

    changed = replace(
        artifact,
        historical_info=replace(
            artifact.historical_info,
            description="Mô tả trong hồ sơ đã được biên tập lại.",
        ),
    )
    changed_provider = ContentProvider(changed)
    changed_response = _learning_service(tmp_path, changed, changed_provider).get(
        "artifact-test"
    )
    prompt_provider = ContentProvider(artifact)
    prompt_response = _learning_service(
        tmp_path,
        artifact,
        prompt_provider,
        prompt_version="prompt-v2",
    ).get("artifact-test")

    assert changed_response.cache_status == "miss"
    assert prompt_response.cache_status == "miss"
    assert changed_provider.calls == 1
    assert prompt_provider.calls == 1


def test_invalid_provider_output_falls_back_without_cache(tmp_path: Path) -> None:
    artifact = _artifact(source="Hồ sơ lưu trữ đã xác minh", source_status="verified")
    provider = ContentProvider(artifact, invalid=True)
    response = _learning_service(tmp_path, artifact, provider).get("artifact-test")

    assert response.generation_status == "fallback_invalid_output"
    assert response.cache_status == "miss"
    assert response.content.mindmap.central_label == artifact.name


def test_fallback_notice_uses_reader_friendly_data_wording(tmp_path: Path) -> None:
    artifact = _artifact(source=None, source_status="missing")
    response = _learning_service(tmp_path, artifact, None).get("artifact-test")

    assert response.generation_status == "fallback_missing_source"
    assert "hồ sơ" not in response.notice.casefold()


@pytest.mark.parametrize(
    ("description", "expected_overview"),
    [
        (
            "Hiện vật ghi lại hoạt động phản chiến. Nhờ đó, người xem có thể hiểu bối cảnh. "
            "Hoạt động này diễn ra trong không gian công cộng.",
            "Hiện vật ghi lại hoạt động phản chiến. Hoạt động này diễn ra trong không gian công cộng.",
        ),
        (
            "Hiện vật này giúp người xem hiểu lịch sử.",
            "Bản đồ thử nghiệm",
        ),
    ],
)
def test_fallback_omits_audience_directed_source_sentences(
    description: str,
    expected_overview: str,
) -> None:
    artifact = _artifact(source=None, source_status="missing")
    artifact = replace(
        artifact,
        historical_info=replace(
            artifact.historical_info,
            description=description,
        ),
    )
    catalog = build_evidence_catalog(artifact)

    content = build_fallback_content(artifact, catalog)

    assert content.deep_sections[0].body == expected_overview
    assert "người xem" not in content.model_dump_json().casefold()


def test_evidence_gate_rejects_invented_fact_even_with_a_real_reference() -> None:
    artifact = _artifact(source="Hồ sơ lưu trữ đã xác minh", source_status="verified")
    catalog = build_evidence_catalog(artifact)
    content = build_fallback_content(artifact, catalog).model_copy(deep=True)
    content.factual_claims[0].text = "Một hiện vật khác không có trong hồ sơ"

    with pytest.raises(EvidenceValidationError, match="not an excerpt"):
        validate_generated_content(content, catalog)


def test_evidence_gate_accepts_supported_punctuation_variation() -> None:
    artifact = _artifact(source="Hồ sơ lưu trữ đã xác minh", source_status="verified")
    catalog = build_evidence_catalog(artifact)
    content = build_fallback_content(artifact, catalog).model_copy(deep=True)
    content.factual_claims[0].text = "Bản đồ, thử nghiệm!"

    validate_generated_content(content, catalog)


def test_fallback_uses_vietnamese_category_evidence() -> None:
    artifact = _artifact(source="Hồ sơ lưu trữ đã xác minh", source_status="verified")
    artifact = replace(artifact, category="historical_map")
    catalog = build_evidence_catalog(artifact)
    content = build_fallback_content(artifact, catalog)

    assert catalog.values["artifact.category_label"].value == "Bản đồ lịch sử"
    assert content.self_check is not None
    assert content.self_check.options[0].label == "Bản đồ lịch sử"
    assert content.self_check.evidence_refs == ["artifact.category_label"]


def test_uncited_web_evidence_gets_a_verbatim_grounding_claim() -> None:
    artifact = _artifact(source=None, source_status="missing")
    catalog = build_evidence_catalog(artifact)
    content = build_fallback_content(artifact, catalog).model_copy(deep=True)
    content.web_evidence = [
        WebEvidence(
            ref="web.1",
            title="Nguồn được dùng",
            url="https://example.org/used",
            evidence_text="Bản đồ thử nghiệm",
        ),
        WebEvidence(
            ref="web.2",
            title="Nguồn không dùng",
            url="https://example.org/unused",
            evidence_text="Bản đồ thử nghiệm",
        ),
    ]
    content.factual_claims[0].evidence_refs.append("web.1")

    grounded = ground_web_evidence(content)

    assert [evidence.ref for evidence in grounded.web_evidence] == ["web.1", "web.2"]
    assert any(
        claim.text == "Bản đồ thử nghiệm" and claim.evidence_refs == ["web.2"]
        for claim in grounded.factual_claims
    )
    validate_generated_content(grounded, catalog)


def test_learning_repairs_a_missing_web_reference_without_fallback(tmp_path: Path) -> None:
    artifact = _artifact(source=None, source_status="missing")
    provider = ContentProvider(artifact)
    provider.content.factual_claims[0].evidence_refs.remove("web.1")

    response = _learning_service(tmp_path, artifact, provider).get("artifact-test")

    assert response.generation_status == "generated"
    assert any(reference.ref == "web.1" for reference in response.references)


def test_learning_repairs_ungrounded_claim_instead_of_discarding_response(tmp_path: Path) -> None:
    artifact = _artifact(source="Hồ sơ lưu trữ đã xác minh", source_status="verified")
    provider = ContentProvider(artifact)
    provider.content.factual_claims[0].text = "Một hiện vật hoàn toàn khác"

    response = _learning_service(tmp_path, artifact, provider).get("artifact-test")

    assert response.generation_status == "generated"
    assert response.content.factual_claims[0].text == artifact.name
    assert "Một hiện vật hoàn toàn khác" not in response.content.factual_claims[0].text


def test_grounding_repair_preserves_direct_validator_as_a_strict_gate() -> None:
    artifact = _artifact(source="Hồ sơ lưu trữ đã xác minh", source_status="verified")
    catalog = build_evidence_catalog(artifact)
    content = build_fallback_content(artifact, catalog).model_copy(deep=True)
    content.factual_claims[0].text = "Một hiện vật hoàn toàn khác"

    repaired = repair_generated_grounding(content, catalog)

    assert repaired.factual_claims[0].text == artifact.name
    validate_generated_content(repaired, catalog)


def test_grounding_repair_reconciles_unknown_model_references() -> None:
    artifact = _artifact(source="Hồ sơ lưu trữ đã xác minh", source_status="verified")
    catalog = build_evidence_catalog(artifact)
    content = build_fallback_content(artifact, catalog).model_copy(deep=True)
    content.factual_claims[0].evidence_refs = ["web.99"]
    content.storytelling.quick.claim_ids = ["missing-claim"]
    content.deep_sections[0].claim_ids = ["missing-claim"]
    content.timeline[0].evidence_refs = ["missing.timeline"]
    content.keywords[0].evidence_refs = ["missing.keyword"]
    content.mindmap.central_label = "Tên do mô hình tự đặt"
    content.mindmap.branches[0].evidence_refs = ["missing.branch"]
    content.mindmap.branches[0].nodes[0].evidence_refs = ["missing.node"]
    assert content.self_check is not None
    content.self_check.evidence_refs = ["missing.quiz"]

    repaired = repair_generated_grounding(content, catalog)

    assert repaired.mindmap.central_label == artifact.name
    assert repaired.storytelling.quick.claim_ids[0] in {
        claim.id for claim in repaired.factual_claims
    }
    validate_generated_content(repaired, catalog)


def test_grounding_repair_replaces_an_unsupported_year_and_keeps_gate_strict() -> None:
    artifact = _artifact(source="Hồ sơ lưu trữ đã xác minh", source_status="verified")
    catalog = build_evidence_catalog(artifact)
    content = build_fallback_content(artifact, catalog).model_copy(deep=True)
    content.storytelling.one_minute.text += " Năm 1999 không có trong nguồn."
    content.narration.full_text = content.storytelling.one_minute.text

    with pytest.raises(EvidenceValidationError, match="unsupported year"):
        validate_generated_content(content, catalog)

    repaired = repair_generated_grounding(content, catalog)

    assert "1999" not in repaired.storytelling.one_minute.text
    assert "mốc thời gian chưa được nguồn xác nhận" in repaired.storytelling.one_minute.text
    assert repaired.narration.full_text == repaired.storytelling.one_minute.text
    validate_generated_content(repaired, catalog)


def test_evidence_gate_accepts_allowed_url_with_markdown_delimiters() -> None:
    artifact = _artifact(source=None, source_status="missing")
    catalog = build_evidence_catalog(artifact)
    content = build_fallback_content(artifact, catalog).model_copy(deep=True)
    content.web_evidence = [
        WebEvidence(
            ref="web.1",
            title="Nguồn kiểm chứng",
            url="https://example.org/heritage-source",
            evidence_text="Bản đồ thử nghiệm",
        )
    ]
    content.factual_claims[0].evidence_refs.append("web.1")
    content.storytelling.one_minute.text += (
        " (https://example.org/heritage-source)."
    )
    content.narration.full_text = content.storytelling.one_minute.text

    validate_generated_content(content, catalog)


def test_evidence_gate_accepts_year_from_verified_web_source_title() -> None:
    artifact = _artifact(source=None, source_status="missing")
    catalog = build_evidence_catalog(artifact)
    content = build_fallback_content(artifact, catalog).model_copy(deep=True)
    content.web_evidence = [
        WebEvidence(
            ref="web.1",
            title="Ấn Lương Tài Hầu, niên đại 1836",
            url="https://example.org/an-luong-tai-hau",
            evidence_text="Bảo tàng giới thiệu hiện vật Ấn Lương Tài Hầu.",
        )
    ]
    content.factual_claims[0].evidence_refs.append("web.1")
    content.storytelling.one_minute.text += " Nguồn tư liệu ghi niên đại 1836."
    content.narration.full_text = content.storytelling.one_minute.text

    validate_generated_content(content, catalog)


def test_evidence_gate_still_rejects_an_unknown_url() -> None:
    artifact = _artifact(source=None, source_status="missing")
    catalog = build_evidence_catalog(artifact)
    content = build_fallback_content(artifact, catalog).model_copy(deep=True)
    content.storytelling.one_minute.text += " https://malicious.example/unknown"
    content.narration.full_text = content.storytelling.one_minute.text

    with pytest.raises(EvidenceValidationError, match="unsupported URL"):
        validate_generated_content(content, catalog)


def test_related_youtube_video_must_match_attributed_web_source() -> None:
    artifact = _artifact(source="Nguồn lưu trữ đã xác minh", source_status="verified")
    catalog = build_evidence_catalog(artifact)
    youtube_url = "https://www.youtube.com/watch?v=AbCdEfGhI12"
    content = build_fallback_content(artifact, catalog).model_copy(deep=True)
    content.web_evidence = [
        WebEvidence(
            ref="web.1",
            title="Video tư liệu kiểm thử - YouTube",
            url=youtube_url,
            evidence_text="Video trình bày Bản đồ thử nghiệm.",
        )
    ]
    content.related_videos = [
        RelatedVideo(
            title="Video tư liệu kiểm thử",
            url=youtube_url,
            channel_name="Bảo tàng Kiểm thử",
            trust_level="official",
            trust_reason="Kênh chính thức của Bảo tàng Kiểm thử công bố tư liệu này.",
            scope="exact_artifact",
            relevance="Video trình bày trực tiếp hiện vật Bản đồ thử nghiệm.",
            evidence_refs=["web.1"],
        )
    ]

    validate_generated_content(content, catalog)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/results?search_query=ban+do",
        "https://www.youtube.com/playlist?list=PL1234567890",
        "https://www.youtube.com/watch?v=too-short",
        "https://youtube.com.evil.test/watch?v=AbCdEfGhI12",
        "http://www.youtube.com/watch?v=AbCdEfGhI12",
        "https://user@www.youtube.com/watch?v=AbCdEfGhI12",
        "https://www.youtube.com:8443/watch?v=AbCdEfGhI12",
    ],
)
def test_related_video_rejects_non_video_or_lookalike_youtube_url(url: str) -> None:
    artifact = _artifact(source="Nguồn lưu trữ đã xác minh", source_status="verified")
    catalog = build_evidence_catalog(artifact)
    content = build_fallback_content(artifact, catalog).model_copy(deep=True)
    content.web_evidence = [
        WebEvidence(
            ref="web.1",
            title="Liên kết không hợp lệ",
            url=url,
            evidence_text="Bản đồ thử nghiệm",
        )
    ]
    content.related_videos = [
        RelatedVideo(
            title="Liên kết không hợp lệ",
            url=url,
            channel_name="Đài Truyền hình Kiểm thử",
            trust_level="reputable_institution",
            trust_reason="Đài Truyền hình Kiểm thử là đơn vị báo chí có biên tập.",
            scope="broader_context",
            relevance="Nội dung liên quan đến Bản đồ thử nghiệm.",
            evidence_refs=["web.1"],
        )
    ]

    with pytest.raises(EvidenceValidationError, match="specific YouTube video"):
        validate_generated_content(content, catalog)


def test_grounding_repair_uses_attributed_youtube_url_and_title() -> None:
    artifact = _artifact(source="Nguồn lưu trữ đã xác minh", source_status="verified")
    catalog = build_evidence_catalog(artifact)
    youtube_url = "https://youtu.be/AbCdEfGhI12"
    content = build_fallback_content(artifact, catalog).model_copy(deep=True)
    content.web_evidence = [
        WebEvidence(
            ref="web.1",
            title="Tiêu đề YouTube đã xác minh",
            url=youtube_url,
            evidence_text="Video trình bày Bản đồ thử nghiệm.",
        )
    ]
    content.related_videos = [
        RelatedVideo(
            title="Tiêu đề do mô hình tự đặt",
            url="https://malicious.example/video",
            channel_name="Bảo tàng Kiểm thử",
            trust_level="official",
            trust_reason="Kênh chính thức của Bảo tàng Kiểm thử công bố tư liệu này.",
            scope="related_event",
            relevance="Video trình bày sự kiện liên quan đến Bản đồ thử nghiệm.",
            evidence_refs=["web.1"],
        )
    ]

    repaired = repair_generated_grounding(content, catalog)

    assert repaired.related_videos[0].title == "Tiêu đề YouTube đã xác minh"
    assert repaired.related_videos[0].url == youtube_url
    validate_generated_content(repaired, catalog)


def test_invalid_optional_video_is_dropped_without_losing_generated_content(
    tmp_path: Path,
) -> None:
    artifact = _artifact(source="Nguồn lưu trữ đã xác minh", source_status="verified")
    provider = ContentProvider(artifact)
    provider.content.related_videos = [
        RelatedVideo(
            title="Video không có nguồn YouTube tương ứng",
            url="https://www.youtube.com/watch?v=AbCdEfGhI12",
            channel_name="Đài Truyền hình Kiểm thử",
            trust_level="reputable_institution",
            trust_reason="Đài Truyền hình Kiểm thử là đơn vị báo chí có biên tập.",
            scope="broader_context",
            relevance="Nội dung được mô hình đề xuất nhưng chưa có nguồn video tương ứng.",
            evidence_refs=["web.1"],
        )
    ]

    response = _learning_service(tmp_path, artifact, provider).get("artifact-test")

    assert response.generation_status == "generated"
    assert response.content.related_videos == []


def test_editorial_structure_is_ordered_and_narration_matches_visible_story(
    tmp_path: Path,
) -> None:
    artifact = _artifact(source="Hồ sơ lưu trữ đã xác minh", source_status="verified")
    provider = ContentProvider(artifact)
    provider.content.deep_sections[0].title = "Tiêu đề tổng quan do mô hình trả về"
    provider.content.deep_sections.reverse()
    provider.content.narration.short_text = "Bản đọc ngắn không đồng bộ"
    provider.content.narration.full_text = "Bản đọc dài không đồng bộ"

    response = _learning_service(tmp_path, artifact, provider).get("artifact-test")

    assert response.generation_status == "generated"
    assert response.content.deep_sections[0].key == "overview"
    assert response.content.deep_sections[0].title == "Giới thiệu tổng quát"
    assert (
        response.content.narration.short_text
        == response.content.storytelling.quick.text
    )
    assert (
        response.content.narration.full_text
        == response.content.storytelling.one_minute.text
    )


def test_learning_prose_and_notices_use_reader_friendly_data_wording(
    tmp_path: Path,
) -> None:
    artifact = _artifact(source="Nguồn lưu trữ đã xác minh", source_status="verified")
    provider = ContentProvider(artifact)

    response = _learning_service(tmp_path, artifact, provider).get("artifact-test")
    content = response.content
    visible_prose = [
        response.notice,
        content.storytelling.quick.text,
        content.storytelling.one_minute.text,
        *(section.title for section in content.deep_sections),
        *(section.summary for section in content.deep_sections),
        *(section.body for section in content.deep_sections),
        *(entry.label for entry in content.timeline),
        *(keyword.explanation for keyword in content.keywords),
        *(branch.label for branch in content.mindmap.branches),
        *(node.note for branch in content.mindmap.branches for node in branch.nodes),
        content.self_check.question if content.self_check else "",
        content.self_check.explanation if content.self_check else "",
        content.narration.short_text,
        content.narration.full_text,
    ]

    assert all("hồ sơ" not in value.casefold() for value in visible_prose)


@pytest.mark.parametrize(
    "phrase",
    (
        "Hiện vật này giúp học sinh hiểu lịch sử.",
        "Với người học, tác phẩm mang lại một bài học sâu sắc.",
        "Người xem có thể nhận ra ý nghĩa của sự kiện.",
        "Từ góc độ giáo dục, đây là một tư liệu quan trọng.",
        "Khi học về hiện vật, chúng ta hiểu thêm quá khứ.",
        "Tác phẩm mang giá trị giáo dục sâu sắc.",
        "Đây là một nguồn học tập trực quan.",
        "Nội dung phù hợp cho việc dạy học lịch sử.",
        "Hiện vật có thể dùng để giảng dạy trong nhà trường.",
        "Khi người học theo dõi dòng thời gian, các mốc trở nên rõ ràng.",
        "Hình tượng hướng người xem đến một bài học về hòa bình.",
        "Tác phẩm là cầu nối giữa ký ức chiến tranh và người xem hôm nay.",
        "Cách trưng bày buộc người học đối diện với hậu quả chiến tranh.",
        "Bảo tàng tạo nên một không gian giáo dục lịch sử.",
        "Tư liệu này thường được dùng trong bài học.",
        "Đây là nguồn minh họa cho bài học này.",
    ),
)
def test_generated_prose_rejects_audience_directed_framing(phrase: str) -> None:
    artifact = _artifact(source="Nguồn lưu trữ đã xác minh", source_status="verified")
    catalog = build_evidence_catalog(artifact)
    content = build_fallback_content(artifact, catalog).model_copy(deep=True)
    content.storytelling.one_minute.text += f" {phrase}"

    with pytest.raises(EvidenceValidationError, match="audience-directed"):
        validate_generated_content(content, catalog)


def test_deep_sections_reject_meta_introductions() -> None:
    artifact = _artifact(source="Nguồn lưu trữ đã xác minh", source_status="verified")
    catalog = build_evidence_catalog(artifact)
    content = build_fallback_content(artifact, catalog).model_copy(deep=True)
    content.deep_sections[0].summary = "Phần này trình bày ý nghĩa của hiện vật."

    with pytest.raises(EvidenceValidationError, match="meta introduction"):
        validate_generated_content(content, catalog)


def test_documented_students_remain_valid_historical_actors() -> None:
    artifact = _artifact(source="Nguồn lưu trữ đã xác minh", source_status="verified")
    artifact = replace(
        artifact,
        historical_info=replace(
            artifact.historical_info,
            description="Học sinh tham gia phong trào phản đối chiến tranh vào năm 1975.",
        ),
    )
    catalog = build_evidence_catalog(artifact)
    content = build_fallback_content(artifact, catalog)

    validate_generated_content(content, catalog)


def test_material_section_rejects_physical_details_absent_from_its_evidence() -> None:
    artifact = _artifact(source="Nguồn lưu trữ đã xác minh", source_status="verified")
    artifact = replace(
        artifact,
        historical_info=replace(
            artifact.historical_info,
            description="Tượng được tạo từ mảnh bom và gắn với ký ức chiến tranh.",
        ),
    )
    catalog = build_evidence_catalog(artifact)
    content = build_fallback_content(artifact, catalog).model_copy(deep=True)
    description_claim_id = content.deep_sections[0].claim_ids[0]
    material = DeepSection(
        key="material",
        title="Chất liệu và cấu tạo",
        summary="Tên và mô tả tư liệu xác nhận tác phẩm được tạo từ mảnh bom.",
        body=(
            "Chi tiết được kiểm chứng cho biết tượng sử dụng mảnh bom. "
            "Dữ liệu hiện có không cung cấp chi tiết khác về quá trình tạo tác."
        ),
        claim_ids=[description_claim_id],
    )
    content.deep_sections.append(material)

    validate_generated_content(content, catalog)

    content.deep_sections[-1] = material.model_copy(
        update={
            "body": "Tượng sử dụng mảnh bom bằng thép và được chế tác bằng kỹ thuật hàn."
        }
    )
    with pytest.raises(EvidenceValidationError, match="unsupported physical detail"):
        validate_generated_content(content, catalog)


def test_timeline_validation_requires_chronological_dated_entries() -> None:
    artifact = _artifact(source="Hồ sơ lưu trữ đã xác minh", source_status="verified")
    artifact = replace(
        artifact,
        images=(replace(artifact.images[0], year=1968),),
    )
    catalog = build_evidence_catalog(artifact)
    content = build_fallback_content(artifact, catalog).model_copy(deep=True)

    assert [entry.year for entry in content.timeline] == [1968, 1975]
    content.timeline.reverse()

    with pytest.raises(EvidenceValidationError, match="not chronological"):
        validate_generated_content(content, catalog)


def test_mindmap_relations_are_grounded_and_generic_nodes_are_rejected() -> None:
    artifact = _artifact(source="Hồ sơ lưu trữ đã xác minh", source_status="verified")
    artifact = replace(
        artifact,
        historical_info=replace(artifact.historical_info, description="Lịch sử"),
    )
    catalog = build_evidence_catalog(artifact)
    content = build_fallback_content(artifact, catalog).model_copy(deep=True)

    assert all(branch.relation for branch in content.mindmap.branches)
    assert all(branch.evidence_refs for branch in content.mindmap.branches)
    first_branch = content.mindmap.branches[0]
    first_branch.nodes[0].label = "Lịch sử"
    first_branch.nodes[0].evidence_refs = ["history.description"]
    first_branch.evidence_refs = ["history.description", "artifact.category"]

    with pytest.raises(EvidenceValidationError, match="too generic"):
        validate_generated_content(content, catalog)


def test_quick_and_one_minute_story_cannot_be_identical() -> None:
    artifact = _artifact(source=None, source_status="missing")
    catalog = build_evidence_catalog(artifact)
    payload = build_fallback_content(artifact, catalog).model_dump(mode="json")
    payload["storytelling"]["one_minute"]["text"] = payload["storytelling"]["quick"]["text"]

    with pytest.raises(ValidationError, match="must be distinct"):
        GeneratedLearningContent.model_validate(payload)


def test_narration_is_server_selected_and_content_addressed(tmp_path: Path) -> None:
    artifact = _artifact(source=None, source_status="missing")
    repository = Repository(artifact)
    provider = SpeechProvider()
    service = NarrationService(
        lambda: repository,
        provider=provider,
        cache=AudioFileCache(tmp_path / "audio"),
    )

    first = service.create("artifact-test", "short")
    second = service.create("artifact-test", "short")

    assert first.status == "ready"
    assert first.cache_status == "miss"
    assert second.cache_status == "hit"
    assert first.asset_id == second.asset_id
    assert first.audio_url and first.audio_url.endswith(f"/{first.asset_id}/audio")
    assert "hồ sơ" not in first.notice.casefold()
    assert service.get_audio_path(first.asset_id or "") is not None
    assert provider.calls == 1

    next_provider = SpeechProvider()
    next_version = NarrationService(
        lambda: repository,
        provider=next_provider,
        cache=AudioFileCache(tmp_path / "audio"),
        config_version="2",
    ).create("artifact-test", "short")
    assert next_version.cache_status == "miss"
    assert next_version.asset_id != first.asset_id
    assert next_provider.calls == 1

    changed_instruction_provider = SpeechProvider()
    changed_instruction_provider.instructions = "Đọc bằng một chỉ dẫn tiếng Việt mới."
    changed_instruction = NarrationService(
        lambda: repository,
        provider=changed_instruction_provider,
        cache=AudioFileCache(tmp_path / "audio"),
    ).create("artifact-test", "short")
    assert changed_instruction.cache_status == "miss"
    assert changed_instruction.asset_id not in {first.asset_id, next_version.asset_id}
    assert changed_instruction_provider.calls == 1


def test_full_narration_uses_generated_one_minute_story(tmp_path: Path) -> None:
    artifact = _artifact(source="Hồ sơ lưu trữ đã xác minh", source_status="verified")
    repository = Repository(artifact)
    content_provider = ContentProvider(artifact)
    generated_story = (
        "Đây là câu chuyện một phút do mô hình nội dung tạo cho hiện vật và được "
        "dịch vụ thuyết minh sử dụng nguyên văn."
    )
    content_provider.content.storytelling.one_minute.text = generated_story
    learning_service = LearningService(
        lambda: repository,
        provider=content_provider,
        cache=SQLiteLearningContentCache(tmp_path / "learning.sqlite3"),
        prompt_version="prompt-v4",
        schema_version="schema-v4",
    )
    speech_provider = SpeechProvider()
    narration_service = NarrationService(
        lambda: repository,
        provider=speech_provider,
        cache=AudioFileCache(tmp_path / "audio"),
        learning_content_getter=learning_service.get,
    )

    response = narration_service.create("artifact-test", "full")

    assert response.status == "ready"
    assert response.transcript == generated_story
    assert content_provider.calls == 1
    assert speech_provider.calls == 1


def test_narration_without_provider_requests_browser_fallback(tmp_path: Path) -> None:
    artifact = _artifact(source=None, source_status="missing")
    repository = Repository(artifact)
    service = NarrationService(
        lambda: repository,
        provider=None,
        cache=AudioFileCache(tmp_path / "audio"),
    )

    response = service.create("artifact-test", "full")
    assert response.status == "fallback_required"
    assert response.cache_status == "bypass"
    assert response.transcript.startswith("Bản đồ thử nghiệm")


def test_duplicate_in_flight_narration_is_coalesced(tmp_path: Path) -> None:
    artifact = _artifact(source=None, source_status="missing")
    repository = Repository(artifact)
    provider = SpeechProvider()
    entered = threading.Event()
    release = threading.Event()
    original = provider.synthesize

    def slow_synthesize(text: str) -> bytes:
        entered.set()
        assert release.wait(5)
        return original(text)

    provider.synthesize = slow_synthesize  # type: ignore[method-assign]
    service = NarrationService(
        lambda: repository,
        provider=provider,
        cache=AudioFileCache(tmp_path / "audio"),
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(service.create, "artifact-test", "short")
        assert entered.wait(5)
        second = executor.submit(service.create, "artifact-test", "short")
        release.set()
        results = (first.result(5), second.result(5))

    assert {result.status for result in results} == {"ready"}
    assert results[0].asset_id == results[1].asset_id
    assert provider.calls == 1
