from __future__ import annotations

import io
import threading
import wave
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.ai.cache import AudioFileCache, SQLiteLearningContentCache
from src.ai.evidence import (
    EvidenceValidationError,
    build_evidence_catalog,
    build_fallback_content,
    ground_web_evidence,
    repair_generated_grounding,
    validate_generated_content,
)
from src.ai.providers import ProviderInvalidResponseError
from src.ai.schemas import DeepSection, GeneratedLearningContent, WebEvidence
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


class ContentProvider:
    model_name = "test-content-model"

    def __init__(self, artifact: ArtifactRecord, *, invalid: bool = False) -> None:
        catalog = build_evidence_catalog(artifact)
        self.content = build_fallback_content(artifact, catalog)
        if catalog.source_status != "verified":
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
        assert artifact_id == "artifact-test"
        assert normalized_input["source_status"] == self.source_status
        self.search_modes.append(use_web_search)
        if self.invalid:
            raise ProviderInvalidResponseError()
        return self.content


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


def test_verified_content_is_validated_and_cached(tmp_path: Path) -> None:
    artifact = _artifact(source="Hồ sơ lưu trữ đã xác minh", source_status="verified")
    provider = ContentProvider(artifact)
    service = _learning_service(tmp_path, artifact, provider)

    first = service.get("artifact-test")
    second = service.get("artifact-test")

    assert first.generation_status == "generated"
    assert first.cache_status == "miss"
    assert second.cache_status == "hit"
    assert provider.calls == 1
    assert provider.search_modes == [False]


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


def test_grounding_repair_does_not_hide_an_unsupported_year() -> None:
    artifact = _artifact(source="Hồ sơ lưu trữ đã xác minh", source_status="verified")
    catalog = build_evidence_catalog(artifact)
    content = build_fallback_content(artifact, catalog).model_copy(deep=True)
    content.storytelling.one_minute.text += " Năm 1999 không có trong nguồn."

    repaired = repair_generated_grounding(content, catalog)

    with pytest.raises(EvidenceValidationError, match="unsupported year"):
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


def test_evidence_gate_still_rejects_an_unknown_url() -> None:
    artifact = _artifact(source=None, source_status="missing")
    catalog = build_evidence_catalog(artifact)
    content = build_fallback_content(artifact, catalog).model_copy(deep=True)
    content.storytelling.one_minute.text += " https://malicious.example/unknown"
    content.narration.full_text = content.storytelling.one_minute.text

    with pytest.raises(EvidenceValidationError, match="unsupported URL"):
        validate_generated_content(content, catalog)


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
