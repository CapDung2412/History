from __future__ import annotations

import json
import socket
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .analytics import resolve_feedback_selection, validate_recognition
from .base import RepositoryError, RepositoryIntegrityError, RepositoryUnavailableError
from .content import build_story
from .helpers import require_public_id, require_request_id
from .models import (
    ArtifactRecord,
    ChallengeOptionRecord,
    ChallengeRecord,
    FeedbackRecord,
    HistoricalInfoRecord,
    ImageRecord,
    LocationRecord,
    RecognitionRecord,
    SourceRecord,
    StoryRecord,
)


class SupabaseTransport(Protocol):
    def select(
        self,
        table: str,
        *,
        columns: str = "*",
        filters: dict[str, str] | None = None,
        order: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[dict[str, Any]]: ...

    def insert(
        self,
        table: str,
        rows: list[dict[str, Any]],
        *,
        on_conflict: str | None = None,
    ) -> None: ...


class SupabaseRestClient:
    """Small backend-only PostgREST client with no SDK dependency."""

    def __init__(self, url: str, service_role_key: str, *, timeout_seconds: float = 10.0) -> None:
        if not url.startswith(("https://", "http://")):
            raise ValueError("SUPABASE_URL must be an HTTP(S) URL")
        if not service_role_key.strip():
            raise ValueError("SUPABASE_SERVICE_ROLE_KEY is empty")
        self._base_url = url.rstrip("/")
        self._service_role_key = service_role_key
        self._timeout_seconds = timeout_seconds

    def _request(
        self,
        method: str,
        table: str,
        *,
        query: dict[str, str] | None = None,
        payload: list[dict[str, Any]] | None = None,
        prefer: str | None = None,
    ) -> Any:
        params = f"?{urlencode(query or {}, safe=',.*()')}" if query else ""
        endpoint = f"{self._base_url}/rest/v1/{quote(table, safe='')}{params}"
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "apikey": self._service_role_key,
            "Authorization": f"Bearer {self._service_role_key}",
            "Accept": "application/json",
        }
        if body is not None:
            headers["Content-Type"] = "application/json; charset=utf-8"
        if prefer:
            headers["Prefer"] = prefer
        request = Request(endpoint, data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                raw = response.read()
        except HTTPError as exc:
            message = f"Supabase returned HTTP {exc.code} for table {table}"
            if exc.code in {401, 403, 404, 429} or exc.code >= 500:
                raise RepositoryUnavailableError(message) from exc
            if exc.code == 409:
                raise RepositoryIntegrityError(message) from exc
            raise RepositoryError(message) from exc
        except (URLError, TimeoutError, socket.timeout) as exc:
            raise RepositoryUnavailableError(f"Supabase is unavailable for table {table}") from exc
        if not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RepositoryError(f"Supabase returned invalid JSON for table {table}") from exc

    def select(
        self,
        table: str,
        *,
        columns: str = "*",
        filters: dict[str, str] | None = None,
        order: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[dict[str, Any]]:
        query = {"select": columns, **(filters or {})}
        if order:
            query["order"] = order
        if limit is not None:
            query["limit"] = str(limit)
        if offset is not None:
            query["offset"] = str(offset)
        value = self._request("GET", table, query=query)
        if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
            raise RepositoryError(f"Supabase response for {table} was not a list")
        return value

    def insert(
        self,
        table: str,
        rows: list[dict[str, Any]],
        *,
        on_conflict: str | None = None,
    ) -> None:
        if not rows:
            return
        query = {"on_conflict": on_conflict} if on_conflict else None
        prefer = "resolution=merge-duplicates,return=minimal" if on_conflict else "return=minimal"
        self._request("POST", table, query=query, payload=rows, prefer=prefer)


def _first(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    return rows[0] if rows else None


class SupabaseHeritageRepository:
    def __init__(
        self,
        url: str | None = None,
        service_role_key: str | None = None,
        *,
        transport: SupabaseTransport | None = None,
    ) -> None:
        if transport is not None:
            self._transport = transport
        elif url and service_role_key:
            self._transport = SupabaseRestClient(url, service_role_key)
        else:
            raise ValueError("Supabase URL and service role key are required")

    def _artifact_from_row(self, row: dict[str, Any]) -> ArtifactRecord:
        item_id = require_public_id(str(row["id"]))
        history_row = _first(
            self._transport.select(
                "heritage_stories", filters={"item_id": f"eq.{item_id}"}
            )
        )
        if history_row is None:
            raise RepositoryIntegrityError(f"Artifact {item_id} has no story")
        image_rows = self._transport.select(
            "heritage_images",
            filters={"item_id": f"eq.{item_id}"},
            order="sort_order.asc,id.asc",
        )
        source_rows = self._transport.select(
            "heritage_sources",
            filters={"item_id": f"eq.{item_id}"},
            order="id.asc",
        )
        tag_rows = self._transport.select(
            "heritage_item_tags",
            columns="tag_slug",
            filters={"item_id": f"eq.{item_id}"},
            order="tag_slug.asc",
        )
        images = tuple(
            ImageRecord(
                id=str(image["id"]),
                item_id=item_id,
                filename=str(image["filename"]),
                relative_path=str(image["relative_path"]),
                drive_url=image.get("drive_url"),
                caption=str(image["caption"]),
                year=image.get("image_year"),
                view=image.get("view_name"),
                sort_order=int(image["sort_order"]),
            )
            for image in image_rows
        )
        sources = tuple(
            SourceRecord(
                id=str(source["id"]),
                item_id=item_id,
                citation=str(source["citation"]),
                title=source.get("title"),
                url=source.get("url"),
            )
            for source in source_rows
        )
        source_text = history_row.get("source_text")
        history = HistoricalInfoRecord(
            title=str(history_row["title"]),
            description=str(history_row["description"]),
            historical_period=history_row.get("historical_period"),
            year=history_row.get("historical_year"),
            event=history_row.get("event_name"),
            source=source_text,
            source_status="available" if source_text or sources else "missing",
        )
        return ArtifactRecord(
            id=item_id,
            slug=str(row["slug"]),
            name=str(row["name"]),
            category=str(row["category"]),
            tags=tuple(str(tag["tag_slug"]) for tag in tag_rows),
            dataset_name=str(row["dataset_name"]),
            dataset_version=str(row["dataset_version"]),
            location=LocationRecord(
                address=row.get("address"),
                city=row.get("city"),
                province=row.get("province"),
                country=row.get("country"),
                latitude=row.get("latitude"),
                longitude=row.get("longitude"),
            ),
            historical_info=history,
            images=images,
            sources=sources,
            published=bool(row.get("published", False)),
        )

    def get_artifact(self, item_id: str) -> ArtifactRecord | None:
        item_id = require_public_id(item_id)
        row = _first(
            self._transport.select(
                "heritage_items",
                filters={"id": f"eq.{item_id}", "published": "eq.true"},
            )
        )
        return self._artifact_from_row(row) if row else None

    def list_artifacts(self) -> tuple[ArtifactRecord, ...]:
        rows: list[dict[str, Any]] = []
        while True:
            page = self._transport.select(
                "heritage_items", filters={"published": "eq.true"}, order="id.asc",
                limit=500, offset=len(rows),
            )
            if not page:
                break
            rows.extend(page)
        return tuple(self._artifact_from_row(row) for row in rows)

    def get_story(self, item_id: str) -> StoryRecord | None:
        artifact = self.get_artifact(item_id)
        return build_story(artifact) if artifact else None

    def get_images(self, item_id: str) -> tuple[ImageRecord, ...]:
        artifact = self.get_artifact(item_id)
        return artifact.images if artifact else ()

    def get_challenge(self, item_id: str) -> ChallengeRecord | None:
        item_id = require_public_id(item_id)
        if self.get_artifact(item_id) is None:
            return None
        challenge_row = _first(
            self._transport.select(
                "heritage_challenges",
                filters={"item_id": f"eq.{item_id}", "published": "eq.true"},
                order="id.asc",
            )
        )
        if challenge_row is None:
            return None
        challenge_id = str(challenge_row["id"])
        option_rows = self._transport.select(
            "heritage_challenge_options",
            filters={"challenge_id": f"eq.{challenge_id}"},
            order="sort_order.asc,id.asc",
        )
        return ChallengeRecord(
            id=challenge_id,
            item_id=item_id,
            type=str(challenge_row["question_type"]),
            question=str(challenge_row["question"]),
            options=tuple(
                ChallengeOptionRecord(
                    id=str(option["id"]),
                    label=str(option["label"]),
                    is_correct=bool(option["is_correct"]),
                    sort_order=int(option["sort_order"]),
                )
                for option in option_rows
            ),
            explanation=str(challenge_row["explanation"]),
            source_field=str(challenge_row["source_field"]),
        )

    def record_recognition(self, record: RecognitionRecord) -> None:
        record = validate_recognition(record)
        self._transport.insert(
            "recognition_requests",
            [
                {
                    "request_id": require_request_id(record.request_id),
                    "status": record.status,
                    "top1_score": record.top1_score,
                    "score_margin": record.score_margin,
                    "resolved_item_id": record.resolved_item_id,
                    "candidate_ids": list(record.candidate_ids),
                    "quality_issues": list(record.quality_issues),
                    "quality_metrics": record.quality_metrics,
                    "duration_ms": record.duration_ms,
                    "component_timings_ms": record.component_timings_ms,
                }
            ],
            on_conflict="request_id",
        )

    def record_feedback(self, record: FeedbackRecord) -> None:
        request_id = require_request_id(record.request_id)
        context = _first(
            self._transport.select(
                "recognition_requests",
                columns="candidate_ids,resolved_item_id",
                filters={"request_id": f"eq.{request_id}"},
            )
        )
        if context is None:
            raise RepositoryIntegrityError("Unknown recognition request")
        candidates = tuple(str(item) for item in context.get("candidate_ids") or [])
        selected = resolve_feedback_selection(
            record,
            candidate_ids=candidates,
            resolved_item_id=context.get("resolved_item_id"),
        )
        self._transport.insert(
            "recognition_feedback",
            [
                {
                    "request_id": request_id,
                    "is_correct": record.is_correct,
                    "selected_item_id": selected,
                    "no_match": record.no_match,
                }
            ],
        )
