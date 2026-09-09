from __future__ import annotations

import io
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from uuid import uuid4

import numpy as np
from PIL import Image

from src.api.guards import FixedWindowRateLimiter
from src.api.request_context import RecognitionContext, RequestContextStore
from src.api.settings import APISettings
from test_api import _client, _match, _query_png


def test_upload_above_default_spool_threshold_never_rolls_to_disk(monkeypatch, tmp_path) -> None:
    import starlette.formparsers

    rolled = []
    real_spool = starlette.formparsers.SpooledTemporaryFile

    def tracked_spool(*args, **kwargs):
        result = real_spool(*args, **kwargs)
        real_rollover = result.rollover

        def rollover():
            rolled.append(True)
            real_rollover()

        result.rollover = rollover
        return result

    monkeypatch.setattr(starlette.formparsers, "SpooledTemporaryFile", tracked_spool)
    values = np.random.default_rng(20).integers(35, 210, size=(800, 800, 3), dtype=np.uint8)
    output = io.BytesIO()
    Image.fromarray(values).save(output, "PNG")
    payload = output.getvalue()
    assert len(payload) > 1024 * 1024
    client, _, engine = _client(tmp_path, [_match("artifact-a", 0.8), _match("artifact-b", 0.7)])
    response = client.post("/api/v1/recognitions", files={"file": ("large.png", payload, "image/png")})
    assert response.status_code == 200
    assert engine.query_calls == 1
    assert not rolled


def test_declared_oversize_rejected_before_parser(monkeypatch, tmp_path) -> None:
    import src.api.uploads

    async def forbidden_parse(_self):
        raise AssertionError("Oversized request reached parser")

    monkeypatch.setattr(src.api.uploads.MultiPartParser, "parse", forbidden_parse)
    settings = replace(APISettings(), max_upload_bytes=100, multipart_overhead_bytes=100)
    client, _, engine = _client(tmp_path, [], settings)
    response = client.post("/api/v1/recognitions", content=b"x" * 201)
    assert response.status_code == 413
    assert engine.query_calls == 0


def test_chunked_body_cannot_bypass_limit(tmp_path) -> None:
    settings = replace(APISettings(), max_upload_bytes=100, multipart_overhead_bytes=100)
    client, _, engine = _client(tmp_path, [], settings)
    body = (
        b'--sample\r\nContent-Disposition: form-data; name="file"; filename="x.jpg"\r\n'
        b'Content-Type: image/jpeg\r\n\r\n' + b"x" * 500 + b"\r\n--sample--\r\n"
    )
    response = client.post(
        "/api/v1/recognitions", content=iter([body[:100], body[100:]]),
        headers={"Content-Type": "multipart/form-data; boundary=sample"},
    )
    assert response.status_code == 413
    assert engine.query_calls == 0


def test_multipart_requires_one_file_and_rejects_extra_fields(tmp_path) -> None:
    client, _, engine = _client(tmp_path, [])
    for files in (
        [("file", ("a.png", _query_png())), ("file", ("b.png", _query_png()))],
        [("other", ("a.png", _query_png()))],
        [("file", ("a.png", _query_png())), ("name", (None, "unrequested"))],
    ):
        assert client.post("/api/v1/recognitions", files=files).status_code in {400, 422}
    assert engine.query_calls == 0


def test_busy_recognizer_does_not_queue_unbounded_images(tmp_path) -> None:
    client, _, engine = _client(tmp_path, [], replace(APISettings(), max_concurrent_recognitions=1))
    entered, release = threading.Event(), threading.Event()

    def slow_query(_image, _top_k):
        entered.set()
        assert release.wait(10)
        return [], {}

    engine.query = slow_query
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(
            client.post, "/api/v1/recognitions", files={"file": ("a.png", _query_png())}
        )
        try:
            assert entered.wait(10)
            busy = client.post("/api/v1/recognitions", files={"file": ("b.png", _query_png())})
            assert busy.status_code == 429
            assert busy.json()["detail"]["code"] == "recognition_busy"
        finally:
            release.set()
        assert pending.result(10).status_code == 200


def test_feedback_rate_limited_before_lookup(tmp_path) -> None:
    client, _, _ = _client(tmp_path, [], replace(APISettings(), feedback_rate_limit_per_minute=1))
    path = f"/api/v1/recognitions/{uuid4()}/feedback"
    assert client.post(path, json={"is_correct": True}).status_code == 404
    assert client.post(path, json={"is_correct": True}).status_code == 429


def test_simultaneous_feedback_recorded_once(tmp_path) -> None:
    client, repository, _ = _client(tmp_path, [_match("artifact-a", 0.9), _match("artifact-b", 0.6)])
    result = client.post("/api/v1/recognitions", files={"file": ("a.png", _query_png())}).json()
    path = f"/api/v1/recognitions/{result['request_id']}/feedback"
    entered, release = threading.Event(), threading.Event()
    original = repository.record_feedback

    def slow_write(record):
        entered.set()
        assert release.wait(10)
        original(record)

    repository.record_feedback = slow_write
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(client.post, path, json={"is_correct": True})
        try:
            assert entered.wait(10)
            assert client.post(path, json={"is_correct": True}).status_code == 409
        finally:
            release.set()
        assert pending.result(10).status_code == 201
    assert len(repository.feedback) == 1


def test_limiter_and_context_memory_are_bounded_and_expire(monkeypatch) -> None:
    clock = [100.0]
    monkeypatch.setattr("src.api.guards.time.monotonic", lambda: clock[0])
    limiter = FixedWindowRateLimiter(2, max_clients=2)
    assert limiter.allow("a")
    assert limiter.allow("a")
    assert not limiter.allow("a")
    assert limiter.allow("b")
    assert not limiter.allow("c")
    clock[0] += 61
    assert limiter.allow("c")
    assert len(limiter._events) == 1

    store = RequestContextStore(ttl_seconds=10, max_entries=2)
    ids = [uuid4() for _ in range(3)]
    for request_id in ids:
        store.put(RecognitionContext(request_id, "rejected", (), None, clock[0]))
    assert store.get(ids[0]) is None
    assert store.get(ids[1]) is not None
    clock[0] += 11
    assert store.get(ids[2]) is None
