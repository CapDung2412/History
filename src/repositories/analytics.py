from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import replace
from pathlib import Path
from typing import Protocol

from .base import RepositoryIntegrityError
from .helpers import require_public_id, require_request_id
from .models import FeedbackRecord, RecognitionRecord

RECOGNITION_STATUSES = {"accepted", "needs_confirmation", "rejected", "error"}


class AnalyticsStore(Protocol):
    def get_recognition(self, request_id: str) -> RecognitionRecord | None: ...

    def record_recognition(self, record: RecognitionRecord) -> None: ...

    def record_feedback(self, record: FeedbackRecord) -> None: ...


def validate_recognition(record: RecognitionRecord) -> RecognitionRecord:
    record = replace(record, request_id=require_request_id(record.request_id))
    if record.status not in RECOGNITION_STATUSES:
        raise ValueError(f"Unsupported recognition status: {record.status}")
    if len(set(record.candidate_ids)) != len(record.candidate_ids):
        raise ValueError("candidate_ids must not contain duplicates")
    for candidate_id in record.candidate_ids:
        require_public_id(candidate_id, "candidate_id")
    if record.resolved_item_id is not None:
        require_public_id(record.resolved_item_id, "resolved_item_id")
        if record.resolved_item_id not in record.candidate_ids:
            raise ValueError("resolved_item_id must be one of candidate_ids")
    if record.status == "accepted" and record.resolved_item_id is None:
        raise ValueError("accepted recognition requires resolved_item_id")
    if record.top1_score is not None and not -1.0 <= record.top1_score <= 1.0:
        raise ValueError("top1_score must be in [-1, 1]")
    if record.score_margin is not None and not 0.0 <= record.score_margin <= 2.0:
        raise ValueError("score_margin must be in [0, 2]")
    if record.duration_ms is not None and (
        not math.isfinite(record.duration_ms) or record.duration_ms < 0
    ):
        raise ValueError("duration_ms cannot be negative")
    if any(not math.isfinite(value) or value < 0 for value in record.component_timings_ms.values()):
        raise ValueError("component timings cannot be negative")
    return record


def resolve_feedback_selection(
    feedback: FeedbackRecord,
    *,
    candidate_ids: tuple[str, ...],
    resolved_item_id: str | None,
) -> str | None:
    require_request_id(feedback.request_id)
    if feedback.is_correct and feedback.no_match:
        raise ValueError("Correct feedback cannot also be marked no_match")
    if feedback.no_match:
        if feedback.selected_item_id is not None:
            raise ValueError("no_match feedback cannot include selected_item_id")
        return None

    selected = feedback.selected_item_id
    if feedback.is_correct:
        expected = resolved_item_id or (candidate_ids[0] if candidate_ids else None)
        if expected is None:
            raise ValueError("Correct feedback has no offered result")
        if selected is not None and selected != expected:
            raise ValueError("Correct feedback must refer to the recognized result")
        selected = expected
    if selected is None:
        raise ValueError("Feedback requires selected_item_id or no_match")
    require_public_id(selected, "selected_item_id")
    if selected not in candidate_ids:
        raise ValueError("selected_item_id was not offered for this request")
    return selected


class SqliteAnalyticsStore:
    """Local anonymous analytics fallback; it never stores uploaded image bytes."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS recognition_requests (
                    request_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    status TEXT NOT NULL CHECK (
                        status IN ('accepted', 'needs_confirmation', 'rejected', 'error')
                    ),
                    top1_score REAL CHECK (top1_score BETWEEN -1.0 AND 1.0),
                    score_margin REAL CHECK (score_margin BETWEEN 0.0 AND 2.0),
                    resolved_item_id TEXT,
                    candidate_ids TEXT NOT NULL,
                    quality_issues TEXT NOT NULL,
                    quality_metrics TEXT NOT NULL,
                    duration_ms REAL CHECK (duration_ms IS NULL OR duration_ms >= 0),
                    component_timings_ms TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS recognition_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL UNIQUE
                        REFERENCES recognition_requests(request_id) ON DELETE CASCADE,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    is_correct INTEGER NOT NULL CHECK (is_correct IN (0, 1)),
                    selected_item_id TEXT,
                    no_match INTEGER NOT NULL DEFAULT 0 CHECK (no_match IN (0, 1)),
                    CHECK (NOT (is_correct = 1 AND no_match = 1)),
                    CHECK (
                        (no_match = 1 AND selected_item_id IS NULL)
                        OR (no_match = 0 AND selected_item_id IS NOT NULL)
                    )
                );
                """
            )

    def record_recognition(self, record: RecognitionRecord) -> None:
        record = validate_recognition(record)
        values = (
            str(record.request_id),
            record.status,
            record.top1_score,
            record.score_margin,
            record.resolved_item_id,
            json.dumps(record.candidate_ids, ensure_ascii=False),
            json.dumps(record.quality_issues, ensure_ascii=False),
            json.dumps(record.quality_metrics, ensure_ascii=False, sort_keys=True),
            record.duration_ms,
            json.dumps(record.component_timings_ms, ensure_ascii=False, sort_keys=True),
        )
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO recognition_requests (
                        request_id, status, top1_score, score_margin, resolved_item_id,
                        candidate_ids, quality_issues, quality_metrics, duration_ms,
                        component_timings_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )
        except sqlite3.IntegrityError as exc:
            raise RepositoryIntegrityError("Recognition request already exists or is invalid") from exc

    def get_recognition(self, request_id: str) -> RecognitionRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM recognition_requests WHERE request_id = ?",
                (require_request_id(request_id),),
            ).fetchone()
        if row is None:
            return None
        return RecognitionRecord(
            request_id=row["request_id"],
            status=row["status"],
            candidate_ids=tuple(json.loads(row["candidate_ids"])),
            resolved_item_id=row["resolved_item_id"],
            top1_score=row["top1_score"],
            score_margin=row["score_margin"],
            quality_issues=tuple(json.loads(row["quality_issues"])),
            quality_metrics=json.loads(row["quality_metrics"]),
            duration_ms=row["duration_ms"],
            component_timings_ms=json.loads(row["component_timings_ms"]),
        )

    def record_feedback(self, record: FeedbackRecord) -> None:
        request_id = require_request_id(record.request_id)
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT candidate_ids, resolved_item_id FROM recognition_requests WHERE request_id = ?",
                    (request_id,),
                ).fetchone()
                if row is None:
                    raise RepositoryIntegrityError("Unknown recognition request")
                candidates = tuple(json.loads(row["candidate_ids"]))
                selected = resolve_feedback_selection(
                    record,
                    candidate_ids=candidates,
                    resolved_item_id=row["resolved_item_id"],
                )
                connection.execute(
                    """
                    INSERT INTO recognition_feedback (
                        request_id, is_correct, selected_item_id, no_match
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (request_id, int(record.is_correct), selected, int(record.no_match)),
                )
        except sqlite3.IntegrityError as exc:
            raise RepositoryIntegrityError("Feedback already exists or is invalid") from exc
