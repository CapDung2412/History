from __future__ import annotations

import asyncio
import threading
import time
from collections import OrderedDict, deque

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .settings import APISettings


class FixedWindowRateLimiter:
    """Bounded, process-local sliding window; IPs are never persisted."""

    def __init__(self, requests_per_minute: int, max_clients: int = 10_000) -> None:
        self.limit = requests_per_minute
        self.max_clients = max_clients
        self._events: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            while self._events:
                oldest = next(iter(self._events))
                if now - self._events[oldest][-1] < 60:
                    break
                self._events.popitem(last=False)
            events = self._events.get(key)
            if events is None:
                if len(self._events) >= self.max_clients:
                    return False
                events = deque()
                self._events[key] = events
            while events and now - events[0] >= 60:
                events.popleft()
            if len(events) >= self.limit:
                return False
            events.append(now)
            self._events.move_to_end(key)
            return True


class RequestGuardMiddleware:
    """Reject oversized/busy requests before multipart parsing or CLIP loading."""

    def __init__(self, app: ASGIApp, settings: APISettings) -> None:
        self.app = app
        self.settings = settings
        self._inference_slots = threading.BoundedSemaphore(settings.max_concurrent_recognitions)
        self._recognition_limiter = FixedWindowRateLimiter(
            settings.recognition_rate_limit_per_minute, settings.rate_limit_max_clients
        )
        self._feedback_limiter = FixedWindowRateLimiter(
            settings.feedback_rate_limit_per_minute, settings.rate_limit_max_clients
        )
        self._ai_limiter = FixedWindowRateLimiter(
            settings.ai_content_rate_limit_per_minute, settings.rate_limit_max_clients
        )
        self._tts_limiter = FixedWindowRateLimiter(
            settings.tts_rate_limit_per_minute, settings.rate_limit_max_clients
        )
        self._ai_slots = threading.BoundedSemaphore(settings.max_concurrent_ai_generations)
        self._tts_slots = threading.BoundedSemaphore(settings.max_concurrent_tts_generations)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST":
            await self.app(scope, receive, send)
            return
        path = scope["path"].rstrip("/")
        inference = path in {"/api/v1/recognitions", "/api/v1/warmup"}
        feedback = path.startswith("/api/v1/recognitions/") and path.endswith("/feedback")
        learning = path.startswith("/api/v1/artifacts/") and path.endswith("/learning-content")
        narration = path.startswith("/api/v1/artifacts/") and path.endswith("/narrations")
        if not inference and not feedback and not learning and not narration:
            await self.app(scope, receive, send)
            return

        async def reject(status: int, code: str, message: str) -> None:
            response = JSONResponse(
                status_code=status,
                content={"detail": {"code": code, "message": message}},
                headers={"Retry-After": "10"} if status == 429 else None,
            )
            await response(scope, receive, send)

        limit = (
            self.settings.max_upload_bytes + self.settings.multipart_overhead_bytes
            if path == "/api/v1/recognitions"
            else self.settings.max_json_body_bytes
        )
        content_lengths = [value for name, value in scope["headers"] if name.lower() == b"content-length"]
        if content_lengths:
            try:
                size = int(content_lengths[0])
                if len(content_lengths) != 1 or size < 0:
                    raise ValueError
            except ValueError:
                await reject(400, "invalid_request", "Dữ liệu yêu cầu không hợp lệ.")
                return
            if size > limit:
                await reject(413, "file_too_large", "Dung lượng yêu cầu vượt quá giới hạn.")
                return

        client = scope.get("client")
        client_key = client[0] if client else "unknown"
        if inference:
            limiter = self._recognition_limiter
        elif feedback:
            limiter = self._feedback_limiter
        elif learning:
            limiter = self._ai_limiter
        else:
            limiter = self._tts_limiter
        if not limiter.allow(client_key):
            await reject(429, "rate_limit_exceeded", "Có nhiều yêu cầu liên tiếp. Em hãy thử lại sau.")
            return
        semaphore = (
            self._inference_slots
            if inference
            else self._ai_slots
            if learning
            else self._tts_slots
            if narration
            else None
        )
        acquired = semaphore is not None and semaphore.acquire(blocking=False)
        if semaphore is not None and not acquired:
            code = "recognition_busy" if inference else "generation_busy"
            message = (
                "Hệ thống đang nhận diện ảnh khác. Em hãy thử lại sau."
                if inference
                else "Hệ thống đang chuẩn bị nội dung khác. Em hãy thử lại sau."
            )
            await reject(429, code, message)
            return

        received = 0
        deadline = time.monotonic() + self.settings.request_body_timeout_seconds

        async def limited_receive() -> Message:
            nonlocal received
            try:
                message = await asyncio.wait_for(receive(), timeout=max(0.001, deadline - time.monotonic()))
            except TimeoutError as exc:
                raise HTTPException(408, detail={"code": "upload_timeout", "message": "Tải ảnh quá lâu. Em hãy thử lại."}) from exc
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise HTTPException(413, detail={"code": "file_too_large", "message": "Dung lượng yêu cầu vượt quá giới hạn."})
            return message

        try:
            await self.app(scope, limited_receive, send)
        finally:
            if acquired and semaphore is not None:
                semaphore.release()
