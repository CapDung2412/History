from __future__ import annotations

import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote
from uuid import UUID, uuid4

from fastapi import FastAPI, Path as APIPath, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.concurrency import run_in_threadpool

from src.ai import (
    ArtifactNotFoundError,
    LearningContentEnvelope,
    LearningService,
    NarrationRequest,
    NarrationResponse,
    NarrationService,
    build_ai_services,
)
from src.config import Settings
from src.repositories.base import (
    HeritageRepository,
    RepositoryError,
    RepositoryIntegrityError,
    RepositoryUnavailableError,
)
from src.repositories.models import FeedbackRecord, RecognitionRecord

from .confidence import RankedMatch, decide_confidence, deduplicate_matches
from .guards import RequestGuardMiddleware
from .media import MediaAsset, MediaAssetError, MediaService
from .quality import ImageValidationError, QualityResult, assess_quality, read_image
from .recognizer import ClipPineconeEngine, RecognitionEngine, RecognitionUnavailableError
from .request_context import RecognitionContext, RequestContextStore
from .schemas import (
    ArtifactResponse,
    ChallengeResponse,
    ErrorResponse,
    FeedbackRequest,
    FeedbackResponse,
    HealthResponse,
    RecognitionCandidate,
    RecognitionResponse,
    StoryResponse,
    WarmupResponse,
)
from .settings import APISettings
from .uploads import read_upload

LOGGER = logging.getLogger("disan_lens.api")
PUBLIC_ID_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


class APIProblem(Exception):
    def __init__(self, status_code: int, code: str, message: str, request_id: UUID | None = None) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.request_id = request_id


class RepositoryProvider:
    def __init__(self, core_settings: Settings, repository: HeritageRepository | None = None) -> None:
        self._core_settings = core_settings
        self._repository = repository
        self._lock = threading.Lock()

    @property
    def loaded(self) -> bool:
        return self._repository is not None

    def get(self) -> HeritageRepository:
        if self._repository is not None:
            return self._repository
        with self._lock:
            if self._repository is not None:
                return self._repository
            try:
                from src.repositories import build_repository

                analytics_value = os.getenv("ANALYTICS_SQLITE_PATH", "data/analytics.sqlite3")
                analytics_path = Path(analytics_value)
                if not analytics_path.is_absolute():
                    analytics_path = self._core_settings.project_root / analytics_path
                self._repository = build_repository(
                    json_root=self._core_settings.json_root,
                    image_root=self._core_settings.image_root,
                    supabase_url=os.getenv("SUPABASE_URL") or None,
                    service_role_key=os.getenv("SUPABASE_SERVICE_ROLE_KEY") or None,
                    analytics_path=analytics_path,
                )
            except Exception as exc:
                raise RepositoryUnavailableError("Content repository is unavailable") from exc
        return self._repository


def _safe_media_url(relative_path: object) -> str | None:
    if not relative_path:
        return None
    raw = str(relative_path).replace("\\", "/")
    parts = Path(raw).parts
    if not raw or ".." in parts or raw.startswith("/") or Path(raw).drive:
        return None
    return f"/media/{quote(raw, safe='/')}"


def _image_payload(image: dict[str, Any]) -> dict[str, Any]:
    payload = dict(image)
    payload["url"] = _safe_media_url(payload.get("relative_path"))
    return payload


def _artifact_payload(record: Any) -> dict[str, Any]:
    raw = record.to_dict()
    history = dict(raw.get("historical_info") or {})
    source = history.get("source")
    return {
        "item_id": raw["id"],
        "slug": raw.get("slug"),
        "name": raw["name"],
        "title": history.get("title") or raw["name"],
        "category": raw["category"],
        "tags": list(raw.get("tags") or []),
        "historical_period": history.get("historical_period"),
        "period": history.get("historical_period"),
        "year": history.get("year"),
        "description": history.get("description") or "",
        "event": history.get("event"),
        "source": source,
        # A citation being present is not equivalent to independent verification.
        "source_verified": bool(source) and history.get("source_status") == "verified",
        "location": raw.get("location"),
        "images": [_image_payload(dict(image)) for image in raw.get("images") or []],
    }


def _story_payload(record: Any) -> dict[str, Any]:
    raw = record.to_dict()
    quick = dict(raw.get("quick") or {})
    overview = dict(raw.get("overview") or {})
    deep = dict(raw.get("deep") or {})
    description = str(overview.get("description") or "")
    sources = list(deep.get("sources") or [])
    source = next(
        (
            str(value)
            for entry in sources
            if isinstance(entry, dict)
            for value in (entry.get("citation"), entry.get("title"), entry.get("url"))
            if value
        ),
        None,
    )
    primary = quick.get("primary_image")
    return {
        "item_id": raw["item_id"],
        "quick": {
            "title": quick.get("title") or quick.get("name") or "",
            "category": quick.get("category") or "",
            "period": quick.get("historical_period"),
            "year": quick.get("year"),
            "image": _image_payload(dict(primary)) if isinstance(primary, dict) else None,
        },
        "overview": {
            # Dataset currently contains one canonical description. Keep it
            # verbatim rather than inventing separate historical claims.
            "description": description or None,
            "event": overview.get("event"),
            "paragraphs": [],
        },
        "deep": {
            "description": str(deep.get("description") or description),
            "event": deep.get("event"),
            "people": [],
            "related_events": [deep["event"]] if deep.get("event") else [],
            "images": [
                _image_payload(dict(image))
                for image in deep.get("images") or []
                if isinstance(image, dict)
            ],
            "source": source,
            "source_verified": bool(source) and deep.get("source_status") == "verified",
        },
    }


def _challenge_payload(record: Any) -> dict[str, Any]:
    raw = record.to_dict()
    options = list(raw.get("options") or [])
    correct = next((str(option["id"]) for option in options if option.get("is_correct")), "")
    return {
        "id": raw["id"],
        "item_id": raw["item_id"],
        "type": raw["type"],
        "question": raw["question"],
        "options": [{"id": option["id"], "label": option["label"]} for option in options],
        "correct_option_id": correct,
        "explanation": raw["explanation"],
        "source_field": raw["source_field"],
    }


def _quality_payload(result: QualityResult, file_size: int) -> dict[str, Any]:
    sharpness = result.laplacian_variance
    return {
        "status": ("warning" if result.issues else "passed") if result.passed else "failed",
        "metrics": {
            "width": result.width,
            "height": result.height,
            "file_size_bytes": file_size,
            "pixel_count": result.pixel_count,
            "brightness": round(result.brightness_mean, 3),
            "blur_score": round(result.laplacian_variance, 3),
            "sharpness": round(sharpness, 3),
            "brightness_mean": round(result.brightness_mean, 3),
            "brightness_p25": round(result.brightness_p25, 3),
            "brightness_p75": round(result.brightness_p75, 3),
            "laplacian_variance": round(result.laplacian_variance, 3),
            "glare_ratio": round(result.glare_ratio, 6),
        },
        "issues": [
            {
                "code": issue.code,
                "message": issue.message,
                "guidance": issue.guidance,
                "severity": issue.severity,
            }
            for issue in result.issues
        ],
    }


def _candidate_payload(match: RankedMatch, artifact: Any) -> dict[str, Any]:
    raw = artifact.to_dict()
    history = dict(raw.get("historical_info") or {})
    images = list(raw.get("images") or [])
    matched_image_id = str(match.metadata.get("image_id") or "")
    image = next((entry for entry in images if entry.get("id") == matched_image_id), None)
    if image is None and images:
        image = images[0]
    return {
        "item_id": raw["id"],
        "location_id": raw["id"],
        "name": raw["name"],
        "title": history.get("title") or raw["name"],
        "category": raw["category"],
        "period": history.get("historical_period"),
        "historical_period": history.get("historical_period"),
        "year": history.get("year"),
        "score": match.score,
        "image_url": _safe_media_url(image.get("relative_path")) if image else None,
        "image_caption": image.get("caption") if image else None,
    }


def create_app(
    *,
    api_settings: APISettings | None = None,
    core_settings: Settings | None = None,
    repository: HeritageRepository | None = None,
    recognition_engine: RecognitionEngine | None = None,
    context_store: RequestContextStore | None = None,
    learning_service: LearningService | None = None,
    narration_service: NarrationService | None = None,
) -> FastAPI:
    api_config = api_settings or APISettings.load()
    api_config.validate()
    core_config = core_settings or Settings.load(require_pinecone=False)
    repository_provider = RepositoryProvider(core_config, repository)
    engine = recognition_engine or ClipPineconeEngine(core_config)
    contexts = context_store or RequestContextStore(
        api_config.request_context_ttl_seconds, api_config.request_context_max_entries
    )
    thumbnail_cache = Path(api_config.thumbnail_cache_dir)
    if not thumbnail_cache.is_absolute():
        thumbnail_cache = core_config.project_root / thumbnail_cache
    media_service = MediaService(core_config.image_root, thumbnail_cache)
    if learning_service is None or narration_service is None:
        default_learning, default_narration = build_ai_services(
            repository_provider.get,
            settings=api_config,
            project_root=core_config.project_root,
        )
        learning_service = learning_service or default_learning
        narration_service = narration_service or default_narration

    application = FastAPI(
        title="DiSan Lens API",
        version="1.0.0",
        description="Quality-gated CLIP/Pinecone recognition with canonical heritage content.",
    )
    application.add_middleware(RequestGuardMiddleware, settings=api_config)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(api_config.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Accept", "Content-Type"],
    )

    @application.middleware("http")
    async def declare_json_utf8(request: Request, call_next):
        response = await call_next(request)
        content_type = response.headers.get("content-type", "")
        if content_type.lower().split(";", 1)[0] == "application/json" and "charset=" not in content_type.lower():
            response.headers["content-type"] = f"{content_type}; charset=utf-8"
        return response

    @application.exception_handler(APIProblem)
    async def api_problem_handler(_request: Request, exc: APIProblem) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": {
                    "code": exc.code,
                    "message": exc.message,
                    "request_id": str(exc.request_id) if exc.request_id else None,
                }
            },
        )

    @application.exception_handler(RequestValidationError)
    async def validation_handler(_request: Request, _exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"detail": {"code": "invalid_request", "message": "Dữ liệu yêu cầu không hợp lệ."}},
        )

    @application.exception_handler(Exception)
    async def unexpected_handler(_request: Request, _exc: Exception) -> JSONResponse:
        # Deliberately avoid logging exception bodies from external SDKs; they can
        # include request metadata. No stack trace is returned to the client.
        LOGGER.error("Unhandled API error")
        return JSONResponse(
            status_code=500,
            content={"detail": {"code": "internal_error", "message": "Hệ thống đang tạm gián đoạn."}},
        )

    def media_response(asset: MediaAsset, request: Request) -> Response:
        headers = {
            "Cache-Control": asset.cache_control,
            "ETag": asset.etag,
            "X-Content-Type-Options": "nosniff",
        }
        if request.headers.get("if-none-match") == asset.etag:
            return Response(status_code=304, headers=headers)
        return FileResponse(asset.path, media_type=asset.media_type, headers=headers)

    @application.get("/media/{relative_path:path}", include_in_schema=False)
    async def get_media(
        relative_path: str,
        request: Request,
        width: Annotated[int | None, Query(ge=320, le=1280)] = None,
    ) -> Response:
        try:
            asset = await run_in_threadpool(media_service.get, relative_path, width)
        except ValueError as exc:
            raise APIProblem(
                400,
                "invalid_thumbnail_width",
                "Kích thước ảnh xem trước không được hỗ trợ.",
            ) from exc
        except MediaAssetError as exc:
            raise APIProblem(404, "image_not_found", "Không tìm thấy ảnh hiện vật.") from exc
        return media_response(asset, request)

    @application.get("/api/v1/health", response_model=HealthResponse, tags=["system"])
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", version="1.0.0")

    @application.get("/api/v1/health/ready", response_model=HealthResponse, tags=["system"])
    async def readiness() -> HealthResponse:
        repository_ready = True
        try:
            await run_in_threadpool(repository_provider.get)
        except RepositoryError:
            repository_ready = False
        configured = bool(core_config.pinecone_api_key)
        ready = repository_ready and configured and engine.loaded
        return HealthResponse(
            status="ready" if ready else "not_ready",
            version="1.0.0",
            repository_ready=repository_ready,
            model_loaded=engine.loaded,
            pinecone_configured=configured,
            index_verified_at_load=engine.loaded,
        )

    @application.post(
        "/api/v1/warmup",
        response_model=WarmupResponse,
        responses={503: {"model": ErrorResponse}},
        tags=["system"],
    )
    async def warmup() -> WarmupResponse:
        started = time.perf_counter()
        try:
            model_name, dimension = await run_in_threadpool(engine.warmup)
        except RecognitionUnavailableError as exc:
            raise APIProblem(503, "recognition_unavailable", "Hệ thống nhận diện chưa sẵn sàng.") from exc
        return WarmupResponse(
            status="ready",
            model_name=model_name,
            embedding_dimension=dimension,
            elapsed_ms=round((time.perf_counter() - started) * 1000, 3),
        )

    @application.post(
        "/api/v1/recognitions",
        response_model=RecognitionResponse,
        responses={400: {"model": ErrorResponse}, 413: {"model": ErrorResponse}, 429: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
        tags=["recognition"],
        openapi_extra={"requestBody": {"required": True, "content": {"multipart/form-data": {"schema": {
            "type": "object", "required": ["file"], "properties": {"file": {"type": "string", "format": "binary"}}
        }}}}},
    )
    async def recognize(request: Request) -> RecognitionResponse:
        request_id = uuid4()

        total_started = time.perf_counter()
        quality_started = total_started
        try:
            payload = await read_upload(request, api_config)
            image = await run_in_threadpool(read_image, payload, api_config)
            try:
                quality = await run_in_threadpool(assess_quality, image, api_config)
            except BaseException:
                image.close()
                raise
        except ImageValidationError as exc:
            raise APIProblem(exc.status_code, exc.code, exc.message, request_id) from exc
        quality_ms = (time.perf_counter() - quality_started) * 1000
        quality_body = _quality_payload(quality, len(payload))
        del payload

        if not quality.passed:
            image.close()
            total_ms = (time.perf_counter() - total_started) * 1000
            response = RecognitionResponse(
                request_id=request_id,
                quality=quality_body,
                recognition_status="rejected",
                confidence_label="Chưa đủ dữ liệu",
                top_score=None,
                score_margin=None,
                candidates=[],
                selected_item=None,
                timings_ms={"quality": quality_ms, "total": total_ms},
            )
            context = RecognitionContext(
                request_id, "rejected", (), None, time.monotonic()
            )
            contexts.put(context)
            await _record_recognition(repository_provider, response)
            return response

        try:
            matches, engine_timings = await run_in_threadpool(
                engine.query, image, api_config.pinecone_overfetch
            )
        except RecognitionUnavailableError as exc:
            raise APIProblem(503, "recognition_unavailable", "Hệ thống nhận diện chưa sẵn sàng.", request_id) from exc
        finally:
            image.close()

        lookup_started = time.perf_counter()
        try:
            repository_instance = await run_in_threadpool(repository_provider.get)
            unique = deduplicate_matches(matches, limit=api_config.pinecone_overfetch)
            enriched: list[tuple[RankedMatch, Any]] = []
            for match in unique:
                if re.fullmatch(PUBLIC_ID_PATTERN, match.item_id) is None:
                    continue
                try:
                    artifact = await run_in_threadpool(repository_instance.get_artifact, match.item_id)
                except ValueError:
                    continue
                if artifact is not None and getattr(artifact, "published", True):
                    enriched.append((match, artifact))
                if len(enriched) == api_config.candidate_count:
                    break
        except RepositoryError as exc:
            raise APIProblem(503, "content_unavailable", "Kho nội dung đang tạm gián đoạn.", request_id) from exc
        content_ms = (time.perf_counter() - lookup_started) * 1000

        ranked = [entry[0] for entry in enriched]
        decision = decide_confidence(ranked, api_config)
        # A rejected result must not expose low-scoring guesses as answers.
        candidate_bodies = (
            [_candidate_payload(match, artifact) for match, artifact in enriched]
            if decision.status != "rejected"
            else []
        )
        selected = candidate_bodies[0] if decision.status == "accepted" and candidate_bodies else None
        total_ms = (time.perf_counter() - total_started) * 1000
        response = RecognitionResponse(
            request_id=request_id,
            quality=quality_body,
            recognition_status=decision.status,
            confidence_label=decision.label,
            top_score=decision.top_score,
            score_margin=decision.margin,
            candidates=candidate_bodies,
            selected_item=selected,
            timings_ms={
                "quality": round(quality_ms, 3),
                "embedding": round(engine_timings.get("clip", 0.0), 3),
                "vector_search": round(engine_timings.get("pinecone", 0.0), 3),
                "content_lookup": round(content_ms, 3),
                "total": round(total_ms, 3),
            },
        )
        candidate_ids = tuple(candidate.item_id for candidate in response.candidates)
        resolved = selected["item_id"] if selected else None
        contexts.put(
            RecognitionContext(
                request_id, decision.status, candidate_ids, resolved, time.monotonic()
            )
        )
        await _record_recognition(repository_provider, response)
        return response

    @application.get(
        "/api/v1/artifacts/{item_id}",
        response_model=ArtifactResponse,
        responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
        tags=["content"],
    )
    async def get_artifact(
        item_id: Annotated[str, APIPath(pattern=PUBLIC_ID_PATTERN)]
    ) -> ArtifactResponse:
        try:
            repo = await run_in_threadpool(repository_provider.get)
            artifact = await run_in_threadpool(repo.get_artifact, item_id)
        except (RepositoryError, ValueError) as exc:
            if isinstance(exc, ValueError):
                raise APIProblem(404, "artifact_not_found", "Không tìm thấy hiện vật.") from exc
            raise APIProblem(503, "content_unavailable", "Kho nội dung đang tạm gián đoạn.") from exc
        if artifact is None or not getattr(artifact, "published", True):
            raise APIProblem(404, "artifact_not_found", "Không tìm thấy hiện vật.")
        return ArtifactResponse.model_validate(_artifact_payload(artifact))

    @application.get(
        "/api/v1/artifacts/{item_id}/story",
        response_model=StoryResponse,
        responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
        tags=["content"],
    )
    async def get_story(
        item_id: Annotated[str, APIPath(pattern=PUBLIC_ID_PATTERN)]
    ) -> StoryResponse:
        try:
            repo = await run_in_threadpool(repository_provider.get)
            story = await run_in_threadpool(repo.get_story, item_id)
        except (RepositoryError, ValueError) as exc:
            if isinstance(exc, ValueError):
                raise APIProblem(404, "artifact_not_found", "Không tìm thấy hiện vật.") from exc
            raise APIProblem(503, "content_unavailable", "Kho nội dung đang tạm gián đoạn.") from exc
        if story is None:
            raise APIProblem(404, "artifact_not_found", "Không tìm thấy hiện vật.")
        return StoryResponse.model_validate(_story_payload(story))

    @application.post(
        "/api/v1/artifacts/{item_id}/learning-content",
        response_model=LearningContentEnvelope,
        responses={404: {"model": ErrorResponse}, 429: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
        tags=["learning"],
    )
    async def get_learning_content(
        item_id: Annotated[str, APIPath(pattern=PUBLIC_ID_PATTERN)]
    ) -> LearningContentEnvelope:
        try:
            return await run_in_threadpool(learning_service.get, item_id)
        except ArtifactNotFoundError as exc:
            raise APIProblem(404, "artifact_not_found", "Không tìm thấy hiện vật.") from exc
        except RepositoryError as exc:
            raise APIProblem(503, "content_unavailable", "Kho nội dung đang tạm gián đoạn.") from exc

    @application.post(
        "/api/v1/artifacts/{item_id}/narrations",
        response_model=NarrationResponse,
        responses={404: {"model": ErrorResponse}, 429: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
        tags=["learning"],
    )
    async def create_narration(
        item_id: Annotated[str, APIPath(pattern=PUBLIC_ID_PATTERN)],
        request_body: NarrationRequest,
    ) -> NarrationResponse:
        try:
            return await run_in_threadpool(
                narration_service.create,
                item_id,
                request_body.variant,
            )
        except ArtifactNotFoundError as exc:
            raise APIProblem(404, "artifact_not_found", "Không tìm thấy hiện vật.") from exc
        except RepositoryError as exc:
            raise APIProblem(503, "content_unavailable", "Kho nội dung đang tạm gián đoạn.") from exc

    @application.get(
        "/api/v1/narrations/{asset_id}/audio",
        response_class=FileResponse,
        responses={404: {"model": ErrorResponse}},
        tags=["learning"],
    )
    async def get_narration_audio(
        asset_id: Annotated[str, APIPath(pattern=r"^[0-9a-f]{64}$")],
        request: Request,
    ) -> Response:
        audio_path = await run_in_threadpool(narration_service.get_audio_path, asset_id)
        if audio_path is None:
            raise APIProblem(404, "audio_not_found", "Không tìm thấy bản thuyết minh.")
        etag = f'"{asset_id}"'
        headers = {
            "Cache-Control": "public, max-age=31536000, immutable",
            "ETag": etag,
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "inline",
        }
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers=headers)
        return FileResponse(audio_path, media_type="audio/wav", headers=headers)

    @application.get(
        "/api/v1/artifacts/{item_id}/challenge",
        response_model=ChallengeResponse | None,
        responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
        tags=["content"],
    )
    async def get_challenge(
        item_id: Annotated[str, APIPath(pattern=PUBLIC_ID_PATTERN)]
    ) -> ChallengeResponse | None:
        try:
            repo = await run_in_threadpool(repository_provider.get)
            artifact = await run_in_threadpool(repo.get_artifact, item_id)
            if artifact is None or not getattr(artifact, "published", True):
                raise APIProblem(404, "artifact_not_found", "Không tìm thấy hiện vật.")
            challenge = await run_in_threadpool(repo.get_challenge, item_id)
        except APIProblem:
            raise
        except (RepositoryError, ValueError) as exc:
            if isinstance(exc, ValueError):
                raise APIProblem(404, "artifact_not_found", "Không tìm thấy hiện vật.") from exc
            raise APIProblem(503, "content_unavailable", "Kho nội dung đang tạm gián đoạn.") from exc
        return ChallengeResponse.model_validate(_challenge_payload(challenge)) if challenge else None

    @application.get(
        "/api/v1/artifacts/{item_id}/images/{image_id}",
        response_class=FileResponse,
        responses={404: {"model": ErrorResponse}},
        tags=["content"],
    )
    async def get_artifact_image(
        item_id: Annotated[str, APIPath(pattern=PUBLIC_ID_PATTERN)],
        image_id: Annotated[str, APIPath(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")],
        request: Request,
        width: Annotated[int | None, Query(ge=320, le=1280)] = None,
    ) -> Response:
        try:
            repo = await run_in_threadpool(repository_provider.get)
            images = await run_in_threadpool(repo.get_images, item_id)
        except (RepositoryError, ValueError) as exc:
            raise APIProblem(404, "image_not_found", "Không tìm thấy ảnh hiện vật.") from exc
        image_record = next((value for value in images if value.id == image_id), None)
        if image_record is None:
            raise APIProblem(404, "image_not_found", "Không tìm thấy ảnh hiện vật.")
        try:
            asset = await run_in_threadpool(media_service.get, image_record.relative_path, width)
        except ValueError as exc:
            raise APIProblem(400, "invalid_thumbnail_width", "Kích thước ảnh xem trước không được hỗ trợ.") from exc
        except MediaAssetError as exc:
            raise APIProblem(404, "image_not_found", "Không tìm thấy ảnh hiện vật.") from exc
        return media_response(asset, request)

    @application.post(
        "/api/v1/recognitions/{request_id}/feedback",
        response_model=FeedbackResponse,
        status_code=201,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
        tags=["recognition"],
    )
    async def record_feedback(request_id: UUID, feedback: FeedbackRequest) -> FeedbackResponse:
        context = contexts.get(request_id)
        if context is None:
            raise APIProblem(404, "recognition_not_found", "Phiên nhận diện đã hết hạn hoặc không tồn tại.", request_id)
        if context.feedback_recorded or context.feedback_pending:
            raise APIProblem(409, "feedback_already_recorded", "Phản hồi đã được ghi nhận.", request_id)
        if feedback.is_correct and feedback.none_of_the_above:
            raise APIProblem(422, "invalid_feedback", "Phản hồi không hợp lệ.", request_id)
        selected = feedback.selected_item_id
        if feedback.is_correct and selected is None:
            selected = context.resolved_item_id or (context.candidate_ids[0] if context.candidate_ids else None)
        if feedback.is_correct and selected is None:
            raise APIProblem(422, "invalid_feedback", "Không có kết quả nào để xác nhận.", request_id)
        expected = context.resolved_item_id or (context.candidate_ids[0] if context.candidate_ids else None)
        if feedback.is_correct and selected != expected:
            raise APIProblem(422, "invalid_feedback", "Phản hồi đúng phải xác nhận kết quả đầu tiên được đề xuất.", request_id)
        if selected is not None and selected not in context.candidate_ids:
            raise APIProblem(422, "invalid_feedback", "Kết quả đã chọn không thuộc danh sách được đề xuất.", request_id)
        if not contexts.claim_feedback(request_id):
            raise APIProblem(409, "feedback_already_recorded", "Phản hồi đã được ghi nhận hoặc đang xử lý.", request_id)
        try:
            repo = await run_in_threadpool(repository_provider.get)
            await run_in_threadpool(
                repo.record_feedback,
                FeedbackRecord(
                    request_id=str(request_id),
                    is_correct=feedback.is_correct,
                    selected_item_id=selected,
                    no_match=feedback.none_of_the_above,
                ),
            )
        except RepositoryIntegrityError as exc:
            contexts.release_feedback(request_id)
            raise APIProblem(409, "feedback_already_recorded", "Phản hồi đã được ghi nhận.", request_id) from exc
        except ValueError as exc:
            contexts.release_feedback(request_id)
            raise APIProblem(422, "invalid_feedback", "Phản hồi không hợp lệ.", request_id) from exc
        except RepositoryError as exc:
            contexts.release_feedback(request_id)
            raise APIProblem(503, "feedback_unavailable", "Chưa thể lưu phản hồi lúc này.", request_id) from exc
        except BaseException:
            contexts.release_feedback(request_id)
            raise
        contexts.mark_feedback_recorded(request_id)
        return FeedbackResponse(status="recorded", request_id=request_id)

    return application


async def _record_recognition(provider: RepositoryProvider, response: RecognitionResponse) -> None:
    try:
        repository = await run_in_threadpool(provider.get)
        metrics = response.quality.metrics.model_dump()
        await run_in_threadpool(
            repository.record_recognition,
            RecognitionRecord(
                request_id=str(response.request_id),
                status=response.recognition_status,
                candidate_ids=tuple(candidate.item_id for candidate in response.candidates),
                resolved_item_id=(
                    response.selected_item.item_id if response.selected_item is not None else None
                ),
                top1_score=response.top_score,
                score_margin=response.score_margin,
                quality_issues=tuple(issue.code for issue in response.quality.issues),
                quality_metrics=metrics,
                duration_ms=response.timings_ms.get("total"),
                component_timings_ms=response.timings_ms,
            ),
        )
    except Exception:
        # Anonymous analytics is useful but must not make recognition fail. The
        # client still receives its request ID; feedback may be unavailable.
        LOGGER.warning("Anonymous recognition analytics could not be recorded")


app = create_app()
