from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from src.repositories.base import HeritageRepository
from src.repositories.models import ArtifactRecord
from src.text import clean_speech_text

from .cache import (
    AudioFileCache,
    LearningCacheRecord,
    SQLiteLearningContentCache,
)
from .curated_videos import CuratedVideoEntry, curated_videos_for
from .evidence import (
    EvidenceCatalog,
    EvidenceValidationError,
    build_evidence_catalog,
    build_fallback_content,
    extend_catalog_with_curated_videos,
    extend_catalog_with_web_evidence,
    ground_web_evidence,
    normalize_generated_editorial_structure,
    repair_generated_grounding,
    validate_generated_content,
)
from .providers import (
    CONTENT_INSTRUCTIONS,
    TRUSTED_VIDEO_SEARCH_INSTRUCTIONS,
    WEB_SEARCH_INSTRUCTIONS,
    ContentProvider,
    OpenAIResponsesProvider,
    OpenAISpeechProvider,
    ProviderError,
    ProviderInvalidResponseError,
    SpeechProvider,
)
from .schemas import (
    GeneratedLearningContent,
    LearningContentEnvelope,
    NarrationResponse,
    RelatedVideoDiscovery,
)
from .singleflight import SingleFlight


class ArtifactNotFoundError(LookupError):
    """The requested public artifact does not exist."""


RepositoryGetter = Callable[[], HeritageRepository]
LearningContentGetter = Callable[[str], LearningContentEnvelope]


class LearningCache(Protocol):
    def get(self, cache_key: str) -> LearningCacheRecord | None: ...

    def put(self, record: LearningCacheRecord) -> None: ...


class AudioCache(Protocol):
    def get_path(self, cache_key: str) -> Path | None: ...

    def put(self, cache_key: str, audio: bytes) -> Path: ...


class _DisabledLearningCache:
    def get(self, _cache_key: str) -> None:
        return None

    def put(self, _record: LearningCacheRecord) -> None:
        return None


class _DisabledAudioCache:
    def get_path(self, _cache_key: str) -> None:
        return None

    def put(self, _cache_key: str, _audio: bytes) -> Path:
        raise OSError("Audio cache is unavailable")


class LearningService:
    """Generate optional learning material without replacing canonical JSON.

    Canonical facts stay grounded in JSON. Provider web search supplies
    attributable context and optional related videos; every returned URL is
    checked against actual tool results and remains visibly marked as web data.
    """

    def __init__(
        self,
        repository_getter: RepositoryGetter,
        *,
        provider: ContentProvider | None,
        cache: LearningCache,
        prompt_version: str,
        schema_version: str,
        locale: str = "vi-VN",
    ) -> None:
        self._repository_getter = repository_getter
        self._provider = provider
        self._cache = cache
        self._prompt_version = prompt_version
        self._schema_version = schema_version
        self._locale = locale
        self._singleflight: SingleFlight[tuple[GeneratedLearningContent, str]] = SingleFlight()

    def get(self, artifact_id: str) -> LearningContentEnvelope:
        artifact = self._artifact(artifact_id)
        catalog = build_evidence_catalog(artifact)
        fallback = build_fallback_content(artifact, catalog)

        if not _has_core_learning_evidence(catalog):
            return self._fallback_envelope(
                catalog,
                fallback,
                generation_status="fallback_insufficient_data",
                notice="Dữ liệu hiện có chưa đủ nguồn để tạo nội dung mở rộng.",
            )
        if self._provider is None:
            if catalog.source_status == "missing":
                status = "fallback_missing_source"
                notice = (
                    "Dữ liệu chưa có đủ nguồn kiểm chứng và dịch vụ AI chưa được cấu hình. "
                    "Hệ thống vẫn trả lời bằng nội dung xác định từ JSON."
                )
            elif catalog.source_status == "available_unverified":
                status = "fallback_needs_verification"
                notice = (
                    "Nguồn tư liệu chưa được xác minh và dịch vụ AI chưa được cấu hình. "
                    "Hệ thống vẫn trả lời bằng nội dung xác định từ JSON."
                )
            else:
                status = "fallback_disabled"
                notice = (
                    "Dịch vụ tạo nội dung chưa được cấu hình. Nội dung hiện tại được "
                    "sắp xếp trực tiếp từ dữ liệu JSON."
                )
            return self._fallback_envelope(
                catalog,
                fallback,
                generation_status=status,
                notice=notice,
            )

        model = self._provider.model_name
        # Related-video recommendations require current, attributable pages.
        # Keep this in the same single generation call so no extra AI request
        # or YouTube API key is needed.
        use_web_search = True
        cache_key = _learning_cache_key(
            catalog,
            prompt_version=self._prompt_version,
            schema_version=self._schema_version,
            model=model,
            locale=self._locale,
            use_web_search=use_web_search,
        )
        cached = self._valid_cached_content(cache_key, catalog)
        if cached is not None:
            cached = _add_curated_related_videos(cached, catalog)
            reference_catalog = _reference_catalog(catalog, cached)
            return LearningContentEnvelope(
                artifact_id=artifact.id,
                data_status=catalog.data_status,
                source_status=catalog.source_status,
                generation_status="generated",
                cache_status="hit",
                prompt_version=self._prompt_version,
                schema_version=self._schema_version,
                model=model,
                content=cached,
                references=reference_catalog.public_references(),
                notice=_generated_notice(use_web_search, cached=True),
            )

        try:
            generated, cache_status = self._singleflight.run(
                cache_key,
                lambda: self._generate(
                    cache_key,
                    artifact,
                    catalog,
                    use_web_search=use_web_search,
                ),
            )
        except ProviderInvalidResponseError as exc:
            return self._fallback_envelope(
                catalog,
                fallback,
                generation_status="fallback_invalid_output",
                cache_status="miss",
                model=model,
                notice=(
                    "Kết quả OpenAI chưa hoàn tất kiểm tra định dạng hoặc nguồn "
                    f"({exc.code}). Hệ thống vẫn trả lời bằng nội dung xác định từ JSON."
                ),
            )
        except EvidenceValidationError as exc:
            return self._fallback_envelope(
                catalog,
                fallback,
                generation_status="fallback_invalid_output",
                cache_status="miss",
                model=model,
                notice=(
                    "OpenAI đã trả nội dung nhưng dữ kiện chưa vượt qua kiểm tra tham chiếu "
                    f"nguồn ({_evidence_error_code(exc)}). Hệ thống vẫn trả lời bằng nội dung "
                    "xác định từ JSON."
                ),
            )
        except ProviderError:
            return self._fallback_envelope(
                catalog,
                fallback,
                generation_status="fallback_unavailable",
                cache_status="miss",
                model=model,
                notice=(
                    "Dịch vụ AI hoặc tìm kiếm web đang tạm gián đoạn. Hệ thống vẫn "
                    "trả lời bằng nội dung xác định từ JSON."
                ),
            )

        generated = _add_curated_related_videos(generated, catalog)
        reference_catalog = _reference_catalog(catalog, generated)
        return LearningContentEnvelope(
            artifact_id=artifact.id,
            data_status=catalog.data_status,
            source_status=catalog.source_status,
            generation_status="generated",
            cache_status=cache_status,
            prompt_version=self._prompt_version,
            schema_version=self._schema_version,
            model=model,
            content=generated,
            references=reference_catalog.public_references(),
            notice=_generated_notice(use_web_search, cached=False),
        )

    def _artifact(self, artifact_id: str) -> ArtifactRecord:
        artifact = self._repository_getter().get_artifact(artifact_id)
        if artifact is None or not artifact.published:
            raise ArtifactNotFoundError(artifact_id)
        return artifact

    def _valid_cached_content(
        self,
        cache_key: str,
        catalog: EvidenceCatalog,
    ) -> GeneratedLearningContent | None:
        record = self._cache.get(cache_key)
        if record is None:
            return None
        if (
            record.artifact_id != catalog.artifact_id
            or record.input_hash != catalog.input_hash
            or record.prompt_version != self._prompt_version
            or record.schema_version != self._schema_version
            or record.locale != self._locale
            or self._provider is None
            or record.model != self._provider.model_name
            or not record.content.web_evidence
        ):
            return None
        try:
            validate_generated_content(
                record.content,
                _catalog_for_content(catalog, record.content),
            )
        except EvidenceValidationError:
            return None
        return record.content

    def _generate(
        self,
        cache_key: str,
        artifact: ArtifactRecord,
        catalog: EvidenceCatalog,
        *,
        use_web_search: bool,
    ) -> tuple[GeneratedLearningContent, str]:
        # A concurrent leader may have filled the cache before this action ran.
        cached = self._valid_cached_content(cache_key, catalog)
        if cached is not None:
            return _add_curated_related_videos(cached, catalog), "hit"
        assert self._provider is not None
        generated = self._provider.generate(
            artifact_id=artifact.id,
            normalized_input=catalog.normalized_input,
            use_web_search=use_web_search,
        )
        generated = normalize_generated_editorial_structure(generated)
        if use_web_search and not generated.web_evidence:
            raise EvidenceValidationError("Web search produced no attributable source")
        generated = repair_generated_grounding(generated, catalog)
        if not generated.related_videos:
            generated = _add_curated_related_videos(generated, catalog)
        if not generated.related_videos:
            generated = self._add_trusted_related_videos(artifact, catalog, generated)
        generated = ground_web_evidence(generated)
        validate_generated_content(
            generated,
            _catalog_for_content(catalog, generated),
        )
        self._cache.put(
            LearningCacheRecord(
                cache_key=cache_key,
                artifact_id=artifact.id,
                input_hash=catalog.input_hash,
                prompt_version=self._prompt_version,
                schema_version=self._schema_version,
                model=self._provider.model_name,
                locale=self._locale,
                content=generated,
            )
        )
        return generated, "miss"

    def _add_trusted_related_videos(
        self,
        artifact: ArtifactRecord,
        catalog: EvidenceCatalog,
        content: GeneratedLearningContent,
    ) -> GeneratedLearningContent:
        """Try one focused search; failure never discards valid historical content."""

        if self._provider is None:
            return content
        discover = getattr(self._provider, "discover_related_videos", None)
        if not callable(discover):
            return content
        try:
            discovery = discover(
                artifact_id=artifact.id,
                normalized_input=catalog.normalized_input,
            )
            merged = _merge_related_video_discovery(content, discovery)
            merged = repair_generated_grounding(merged, catalog)
            validate_generated_content(merged, catalog)
            return merged
        except (ProviderError, EvidenceValidationError, ValueError, TypeError):
            return content

    def _fallback_envelope(
        self,
        catalog: EvidenceCatalog,
        content,
        *,
        generation_status: str,
        notice: str,
        cache_status: str = "bypass",
        model: str | None = None,
    ) -> LearningContentEnvelope:
        content = _add_curated_related_videos(content, catalog)
        reference_catalog = _reference_catalog(catalog, content)
        return LearningContentEnvelope.model_validate(
            {
                "artifact_id": catalog.artifact_id,
                "data_status": catalog.data_status,
                "source_status": catalog.source_status,
                "generation_status": generation_status,
                "cache_status": cache_status,
                "prompt_version": self._prompt_version,
                "schema_version": self._schema_version,
                "model": model,
                "content": content,
                "references": reference_catalog.public_references(),
                "notice": notice,
            }
        )


class NarrationService:
    """Create and cache Vietnamese WAV narration from canonical artifact data."""

    def __init__(
        self,
        repository_getter: RepositoryGetter,
        *,
        provider: SpeechProvider | None,
        cache: AudioCache,
        learning_content_getter: LearningContentGetter | None = None,
        audio_url_prefix: str = "/api/v1/narrations",
        config_version: str = "1",
    ) -> None:
        self._repository_getter = repository_getter
        self._provider = provider
        self._cache = cache
        self._learning_content_getter = learning_content_getter
        self._audio_url_prefix = audio_url_prefix.rstrip("/")
        self._config_version = config_version
        self._singleflight: SingleFlight[Path] = SingleFlight()

    def create(self, artifact_id: str, variant: str) -> NarrationResponse:
        if variant not in {"short", "full"}:
            raise ValueError("Unsupported narration variant")
        artifact = self._artifact(artifact_id)
        catalog = build_evidence_catalog(artifact)
        content = build_fallback_content(artifact, catalog)
        if self._learning_content_getter is not None:
            learning = self._learning_content_getter(artifact.id)
            if learning.generation_status == "generated":
                content = learning.content
        # Read the visible story directly so narration can never drift from the
        # text shown to learners, even if a stale cache contains copied
        # narration fields from an older schema version.
        transcript = clean_speech_text(
            content.storytelling.quick.text
            if variant == "short"
            else content.storytelling.one_minute.text
        )

        if self._provider is None:
            return self._fallback_response(
                artifact.id,
                variant,
                transcript,
                "Giọng đọc AI chưa được cấu hình; trình duyệt sẽ dùng giọng đọc có sẵn trên thiết bị.",
            )

        asset_id = _audio_cache_key(
            transcript,
            model=self._provider.model_name,
            voice=self._provider.voice_name,
            language=self._provider.language,
            instructions=self._provider.instructions,
            config_version=self._config_version,
        )
        cached = self._cache.get_path(asset_id)
        if cached is not None:
            return self._ready_response(
                artifact.id, variant, transcript, asset_id, cache_status="hit"
            )
        try:
            self._singleflight.run(
                asset_id,
                lambda: self._synthesize_and_cache(asset_id, transcript),
            )
        except (ProviderError, OSError, ValueError):
            return self._fallback_response(
                artifact.id,
                variant,
                transcript,
                "Dịch vụ giọng đọc AI đang tạm gián đoạn; trình duyệt sẽ dùng giọng đọc của thiết bị.",
                cache_status="miss",
            )
        return self._ready_response(
            artifact.id, variant, transcript, asset_id, cache_status="miss"
        )

    def get_audio_path(self, asset_id: str) -> Path | None:
        try:
            return self._cache.get_path(asset_id)
        except ValueError:
            return None

    def _artifact(self, artifact_id: str) -> ArtifactRecord:
        artifact = self._repository_getter().get_artifact(artifact_id)
        if artifact is None or not artifact.published:
            raise ArtifactNotFoundError(artifact_id)
        return artifact

    def _synthesize_and_cache(self, asset_id: str, transcript: str) -> Path:
        cached = self._cache.get_path(asset_id)
        if cached is not None:
            return cached
        assert self._provider is not None
        audio = self._provider.synthesize(transcript)
        return self._cache.put(asset_id, audio)

    def _ready_response(
        self,
        artifact_id: str,
        variant: str,
        transcript: str,
        asset_id: str,
        *,
        cache_status: str,
    ) -> NarrationResponse:
        return NarrationResponse.model_validate(
            {
                "artifact_id": artifact_id,
                "variant": variant,
                "status": "ready",
                "cache_status": cache_status,
                "transcript": transcript,
                "asset_id": asset_id,
                "audio_url": f"{self._audio_url_prefix}/{asset_id}/audio",
                "mime_type": "audio/wav",
                "notice": "Giọng đọc AI. Hãy kiểm tra thông tin quan trọng với nguồn tư liệu.",
            }
        )

    @staticmethod
    def _fallback_response(
        artifact_id: str,
        variant: str,
        transcript: str,
        notice: str,
        *,
        cache_status: str = "bypass",
    ) -> NarrationResponse:
        return NarrationResponse.model_validate(
            {
                "artifact_id": artifact_id,
                "variant": variant,
                "status": "fallback_required",
                "cache_status": cache_status,
                "transcript": transcript,
                "asset_id": None,
                "audio_url": None,
                "mime_type": None,
                "notice": notice,
            }
        )


def build_ai_services(
    repository_getter: RepositoryGetter,
    *,
    settings,
    project_root: Path,
) -> tuple[LearningService, NarrationService]:
    """Build optional providers and project-confined caches from API settings."""

    learning_cache_path = _project_path(project_root, settings.ai_cache_sqlite_path)
    audio_cache_path = _project_path(project_root, settings.tts_cache_dir)
    learning_cache_available = True
    audio_cache_available = True
    try:
        learning_cache: LearningCache = SQLiteLearningContentCache(learning_cache_path)
    except (OSError, sqlite3.DatabaseError):
        learning_cache = _DisabledLearningCache()
        learning_cache_available = False
    try:
        audio_cache: AudioCache = AudioFileCache(audio_cache_path)
    except OSError:
        audio_cache = _DisabledAudioCache()
        audio_cache_available = False

    content_provider: ContentProvider | None = None
    speech_provider: SpeechProvider | None = None
    if settings.openai_api_key:
        if settings.openai_content_model and learning_cache_available:
            content_provider = OpenAIResponsesProvider(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
                model=settings.openai_content_model,
                prompt_version=settings.ai_prompt_version,
                timeout_seconds=settings.openai_timeout_seconds,
                max_retries=settings.openai_max_retries,
                max_output_tokens=settings.openai_max_output_tokens,
            )
        if audio_cache_available:
            speech_provider = OpenAISpeechProvider(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
                model=settings.openai_tts_model,
                voice=settings.openai_tts_voice,
                language=settings.tts_language,
                timeout_seconds=settings.openai_timeout_seconds,
                max_retries=settings.openai_max_retries,
            )

    learning_service = LearningService(
        repository_getter,
        provider=content_provider,
        cache=learning_cache,
        prompt_version=settings.ai_prompt_version,
        schema_version=settings.ai_schema_version,
        locale=settings.tts_language,
    )
    narration_service = NarrationService(
        repository_getter,
        provider=speech_provider,
        cache=audio_cache,
        learning_content_getter=learning_service.get,
        config_version=settings.tts_config_version,
    )
    return learning_service, narration_service


def _project_path(project_root: Path, configured: str) -> Path:
    root = project_root.resolve()
    path = Path(configured)
    target = path.resolve() if path.is_absolute() else (root / path).resolve()
    if not target.is_relative_to(root):
        raise ValueError("AI cache paths must stay inside the project root")
    return target


def _selected_curated_videos(
    catalog: EvidenceCatalog,
) -> tuple[CuratedVideoEntry, ...]:
    def value(ref: str) -> str | None:
        evidence = catalog.values.get(ref)
        return evidence.value if evidence is not None else None

    return curated_videos_for(
        catalog.artifact_id,
        location_address=value("location.address"),
        description=value("history.description"),
    )


def _add_curated_related_videos(
    content: GeneratedLearningContent,
    catalog: EvidenceCatalog,
) -> GeneratedLearningContent:
    """Overlay reviewed links only when dynamic generation returned none."""

    if content.related_videos:
        return content
    curated = _selected_curated_videos(catalog)
    if not curated:
        return content
    return content.model_copy(
        update={"related_videos": [entry.as_related_video() for entry in curated[:3]]}
    )


def _catalog_for_content(
    catalog: EvidenceCatalog,
    content: GeneratedLearningContent,
) -> EvidenceCatalog:
    curated_refs = {
        ref
        for video in content.related_videos
        for ref in video.evidence_refs
        if ref.startswith("curated.video.")
    }
    if not curated_refs:
        return catalog
    selected = [
        entry
        for entry in _selected_curated_videos(catalog)
        if entry.ref in curated_refs
    ]
    return extend_catalog_with_curated_videos(catalog, selected)


def _reference_catalog(
    catalog: EvidenceCatalog,
    content: GeneratedLearningContent,
) -> EvidenceCatalog:
    return extend_catalog_with_web_evidence(
        _catalog_for_content(catalog, content),
        content.web_evidence,
    )


def _merge_related_video_discovery(
    content: GeneratedLearningContent,
    discovery: RelatedVideoDiscovery,
) -> GeneratedLearningContent:
    """Renumber focused-search refs before merging them into full content."""

    if content.related_videos or not discovery.related_videos:
        return content
    evidence_by_ref = {evidence.ref: evidence for evidence in discovery.web_evidence}
    used_refs = {evidence.ref for evidence in content.web_evidence}
    available_refs = [
        f"web.{index}"
        for index in range(1, 100)
        if f"web.{index}" not in used_refs
    ]
    capacity = max(0, 12 - len(content.web_evidence))
    appended_evidence = []
    appended_videos = []
    remapped: dict[str, str] = {}
    for video in discovery.related_videos[: min(4, capacity)]:
        if len(video.evidence_refs) != 1:
            continue
        old_ref = video.evidence_refs[0]
        evidence = evidence_by_ref.get(old_ref)
        if evidence is None:
            continue
        new_ref = remapped.get(old_ref)
        if new_ref is None:
            if not available_refs:
                break
            new_ref = available_refs.pop(0)
            remapped[old_ref] = new_ref
            appended_evidence.append(evidence.model_copy(update={"ref": new_ref}))
        appended_videos.append(
            video.model_copy(update={"evidence_refs": [new_ref]})
        )
    if not appended_videos:
        return content
    return content.model_copy(
        update={
            "related_videos": appended_videos,
            "web_evidence": [*content.web_evidence, *appended_evidence],
        }
    )


def _learning_cache_key(
    catalog: EvidenceCatalog,
    *,
    prompt_version: str,
    schema_version: str,
    model: str,
    locale: str,
    use_web_search: bool,
) -> str:
    return _sha256_json(
        {
            "artifact_id": catalog.artifact_id,
            "input_hash": catalog.input_hash,
            "prompt_version": prompt_version,
            "prompt_fingerprint": hashlib.sha256(
                (
                    CONTENT_INSTRUCTIONS
                    + (WEB_SEARCH_INSTRUCTIONS if use_web_search else "")
                    + TRUSTED_VIDEO_SEARCH_INSTRUCTIONS
                ).encode("utf-8")
            ).hexdigest(),
            "schema_version": schema_version,
            "schema_fingerprint": _sha256_json(
                GeneratedLearningContent.openai_json_schema()
            ),
            "model": model,
            "locale": locale,
            "use_web_search": use_web_search,
        }
    )


def _has_core_learning_evidence(catalog: EvidenceCatalog) -> bool:
    return {
        "artifact.name",
        "artifact.category",
        "history.description",
    }.issubset(catalog.values)


def _generated_notice(use_web_search: bool, *, cached: bool) -> str:
    cache_text = " từ bộ nhớ đệm" if cached else ""
    if use_web_search:
        return (
            f"Nội dung AI{cache_text} kết hợp dữ liệu JSON với các trang do công cụ tìm kiếm "
            "web của OpenAI trả về. Các nguồn web được dẫn link nhưng chưa thay thế bước "
            "kiểm chứng biên tập."
        )
    return (
        f"Nội dung AI có cấu trúc{cache_text}, chỉ dùng dữ kiện và tham chiếu nguồn "
        "trong dữ liệu hiện vật."
    )


_EVIDENCE_ERROR_CODES = {
    "Duplicate factual claim id": "duplicate_claim_id",
    "Factual claim is not an excerpt of its cited evidence": "claim_not_grounded",
    "Timeline contains a year absent from explicit year fields": "timeline_year_not_grounded",
    "Timeline entries are not chronological": "timeline_not_chronological",
    "Keyword is absent from its cited evidence": "keyword_not_grounded",
    "Mindmap center must use the canonical artifact name": "mindmap_center_not_canonical",
    "Duplicate mindmap id": "duplicate_mindmap_id",
    "Mindmap branch evidence must be represented by its nodes": "mindmap_branch_refs_invalid",
    "Mindmap label is absent from its cited evidence": "mindmap_label_not_grounded",
    "Mindmap node label is too generic": "mindmap_label_too_generic",
    "Correct self-check option is absent from its cited evidence": "quiz_answer_not_grounded",
    "Generated text contains an unsupported year": "unsupported_year",
    "Generated text contains an unsupported URL": "unsupported_url",
    "Web evidence must be cited by generated content": "unused_web_evidence",
    "Web evidence ref collides with existing evidence": "web_ref_collision",
    "Web evidence contains an invalid URL": "invalid_web_url",
    "Generated content references unknown evidence": "unknown_evidence_ref",
    "Narrative references an unknown factual claim": "unknown_claim_ref",
    "Material section contains an unsupported physical detail": "material_detail_not_grounded",
    "Generated text uses audience-directed educational framing": "audience_directed_framing",
    "Deep section uses a meta introduction": "section_meta_introduction",
    "Related video URL is not a specific YouTube video": "youtube_video_url_invalid",
    "Duplicate related YouTube video": "youtube_video_duplicate",
    "Related video URL is not backed by cited web evidence": "youtube_video_unattributed",
    "Web search produced no attributable source": "no_cited_web_source",
}


def _evidence_error_code(exc: EvidenceValidationError) -> str:
    """Return only a fixed diagnostic code; never surface generated text."""

    return _EVIDENCE_ERROR_CODES.get(str(exc), "evidence_validation_failed")


def _audio_cache_key(
    text: str,
    *,
    model: str,
    voice: str,
    language: str,
    instructions: str,
    config_version: str,
) -> str:
    return _sha256_json(
        {
            "text": text,
            "model": model,
            "voice": voice,
            "language": language,
            "instructions": instructions,
            "format": "wav",
            "config_version": config_version,
        }
    )


def _sha256_json(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
