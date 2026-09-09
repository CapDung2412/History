from __future__ import annotations

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from uuid import UUID


@dataclass(slots=True)
class RecognitionContext:
    request_id: UUID
    status: str
    candidate_ids: tuple[str, ...]
    resolved_item_id: str | None
    created_monotonic: float
    feedback_recorded: bool = False
    feedback_pending: bool = False


class RequestContextStore:
    """Short-lived server-side context used to validate anonymous feedback."""

    def __init__(self, ttl_seconds: int, max_entries: int = 10_000) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._entries: OrderedDict[UUID, RecognitionContext] = OrderedDict()
        self._lock = threading.Lock()

    def _prune(self, now: float) -> None:
        expired = [
            request_id
            for request_id, context in self._entries.items()
            if now - context.created_monotonic > self.ttl_seconds
        ]
        for request_id in expired:
            self._entries.pop(request_id, None)

    def put(self, context: RecognitionContext) -> None:
        with self._lock:
            self._prune(time.monotonic())
            self._entries[context.request_id] = context
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)

    def get(self, request_id: UUID) -> RecognitionContext | None:
        with self._lock:
            self._prune(time.monotonic())
            return self._entries.get(request_id)

    def mark_feedback_recorded(self, request_id: UUID) -> bool:
        with self._lock:
            self._prune(time.monotonic())
            context = self._entries.get(request_id)
            if context is None or context.feedback_recorded:
                return False
            context.feedback_recorded = True
            context.feedback_pending = False
            return True

    def claim_feedback(self, request_id: UUID) -> bool:
        with self._lock:
            self._prune(time.monotonic())
            context = self._entries.get(request_id)
            if context is None or context.feedback_recorded or context.feedback_pending:
                return False
            context.feedback_pending = True
            return True

    def release_feedback(self, request_id: UUID) -> None:
        with self._lock:
            context = self._entries.get(request_id)
            if context is not None:
                context.feedback_pending = False
