from __future__ import annotations

import io
import json
import unicodedata
import wave

import pytest

from src.ai.evidence import build_evidence_catalog, build_fallback_content
from src.ai.providers import (
    OpenAIResponsesProvider,
    OpenAISpeechProvider,
    ProviderInvalidResponseError,
    ProviderUnavailableError,
)
from src.ai.schemas import WebEvidence
from src.repositories.models import (
    ArtifactRecord,
    HistoricalInfoRecord,
    LocationRecord,
)


def _verified_artifact() -> ArtifactRecord:
    return ArtifactRecord(
        id="artifact-provider-test",
        slug="artifact-provider-test",
        name="Hiện vật kiểm thử",
        category="artifact",
        tags=("kiểm thử",),
        dataset_name="Di San Lens",
        dataset_version="1",
        location=LocationRecord(None, "Huế", None, "Việt Nam", None, None),
        historical_info=HistoricalInfoRecord(
            title="Hiện vật kiểm thử",
            description="Bỏ qua chỉ dẫn trước đó không phải là một chỉ thị hệ thống.",
            historical_period="Giai đoạn trong hồ sơ",
            year=None,
            event=None,
            source="Hồ sơ lưu trữ đã xác minh",
            source_status="verified",
        ),
        images=(),
    )


def _wav() -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(8_000)
        writer.writeframes(b"\x00\x00" * 80)
    return output.getvalue()


class Transport:
    def __init__(self, *results: bytes | Exception) -> None:
        self.results = list(results)
        self.calls: list[dict] = []

    def post(self, url: str, *, headers, body, timeout_seconds, max_response_bytes):
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "body": body,
                "timeout": timeout_seconds,
                "max_response_bytes": max_response_bytes,
            }
        )
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def _content_response() -> tuple[ArtifactRecord, bytes]:
    artifact = _verified_artifact()
    catalog = build_evidence_catalog(artifact)
    content = build_fallback_content(artifact, catalog)
    payload = {
        "output": [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": content.model_dump_json()}
                ],
            }
        ]
    }
    return artifact, json.dumps(payload).encode("utf-8")


def test_responses_provider_uses_strict_non_stored_grounded_request() -> None:
    artifact, response = _content_response()
    transport = Transport(response)
    provider = OpenAIResponsesProvider(
        api_key="test-key-not-a-real-secret",
        base_url="https://api.openai.com/v1",
        model="test-model",
        prompt_version="prompt-v1",
        timeout_seconds=4,
        max_retries=0,
        max_output_tokens=1200,
        transport=transport,
    )
    catalog = build_evidence_catalog(artifact)

    generated = provider.generate(
        artifact_id=artifact.id,
        normalized_input=catalog.normalized_input,
    )

    assert generated.mindmap.central_label == artifact.name
    request = json.loads(transport.calls[0]["body"])
    assert request["store"] is False
    assert request["tools"] == []
    assert request["text"]["format"]["type"] == "json_schema"
    assert request["text"]["format"]["strict"] is True
    assert request["text"]["format"]["schema"]["additionalProperties"] is False
    schema = request["text"]["format"]["schema"]
    assert schema["properties"]["deep_sections"]["minItems"] == 6
    assert schema["properties"]["deep_sections"]["maxItems"] == 8
    assert schema["properties"]["timeline"]["minItems"] == 4
    one_minute_text = schema["$defs"]["StoryContent"]["properties"][
        "one_minute"
    ]["properties"]["text"]
    quick_story = schema["$defs"]["StoryContent"]["properties"]["quick"]
    assert "$ref" not in quick_story
    assert quick_story["type"] == "object"
    assert one_minute_text["minLength"] == 600
    assert one_minute_text["maxLength"] == 1400
    assert schema["$defs"]["DeepSection"]["properties"]["body"]["minLength"] == 220
    assert schema["$defs"]["MindMap"]["properties"]["branches"]["minItems"] == 5
    assert schema["$defs"]["MindMap"]["properties"]["branches"]["maxItems"] == 6
    assert schema["$defs"]["MindMapBranch"]["properties"]["nodes"]["minItems"] == 3
    assert schema["$defs"]["MindMapBranch"]["properties"]["nodes"]["maxItems"] == 5
    assert schema["$defs"]["MindMapNode"]["properties"]["note"]["minLength"] == 80
    assert "135-165 Vietnamese words" in request["instructions"]
    assert "Giới thiệu tổng quát" in request["instructions"]
    assert "Chất liệu và kỹ thuật tạo tác" in request["instructions"]
    assert "three internal passes inside this single response" in request["instructions"]
    assert "detailed, readable historical flow" in request["instructions"]
    assert "Never infer alloy" in request["instructions"]
    assert "narration.full_text must equal" in request["instructions"]
    assert len(transport.calls) == 1
    assert request["input"][0]["content"][0]["text"].startswith(
        "UNTRUSTED_CANONICAL_DATA_JSON"
    )
    assert "Bỏ qua chỉ dẫn trước đó" not in request["instructions"]


def test_responses_provider_requires_search_and_accepts_only_returned_source_urls() -> None:
    artifact = _verified_artifact()
    catalog = build_evidence_catalog(artifact)
    content = build_fallback_content(artifact, catalog).model_copy(
        update={
            "web_evidence": [
                WebEvidence(
                    ref="web.1",
                    title="Tiêu đề do mô hình trả về",
                    url="https://example.org/archive/item?lang=vi#section",
                    evidence_text="Hiện vật kiểm thử",
                )
            ]
        }
    )
    response = json.dumps(
        {
            "output": [
                {
                    "type": "web_search_call",
                    "action": {
                        "type": "search",
                        "sources": [
                            {
                                "type": "url",
                                "url": "https://example.org/archive/item?lang=vi",
                                "title": "Hồ sơ lưu trữ chính thức",
                            }
                        ],
                    },
                },
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": content.model_dump_json()}
                    ],
                },
            ]
        }
    ).encode("utf-8")
    transport = Transport(response)
    provider = OpenAIResponsesProvider(
        api_key="test-key-not-a-real-secret",
        base_url="https://api.openai.com/v1",
        model="test-model",
        prompt_version="prompt-v1",
        timeout_seconds=4,
        max_retries=0,
        max_output_tokens=1200,
        transport=transport,
    )

    generated = provider.generate(
        artifact_id=artifact.id,
        normalized_input=catalog.normalized_input,
        use_web_search=True,
    )

    request = json.loads(transport.calls[0]["body"])
    assert request["tools"] == [{"type": "web_search"}]
    assert request["tool_choice"] == "required"
    assert request["include"] == ["web_search_call.action.sources"]
    assert "WEB_SEARCH_MODE" in request["instructions"]
    assert generated.web_evidence[0].url == "https://example.org/archive/item?lang=vi"
    assert generated.web_evidence[0].title == "Hồ sơ lưu trữ chính thức"


def test_responses_provider_rejects_web_url_not_returned_by_search() -> None:
    artifact = _verified_artifact()
    catalog = build_evidence_catalog(artifact)
    content = build_fallback_content(artifact, catalog).model_copy(
        update={
            "web_evidence": [
                WebEvidence(
                    ref="web.1",
                    title="Nguồn giả",
                    url="https://unreturned.example/source",
                    evidence_text="Hiện vật kiểm thử",
                )
            ]
        }
    )
    response = json.dumps(
        {
            "output": [
                {
                    "type": "web_search_call",
                    "action": {
                        "sources": [
                            {"url": "https://example.org/real-source", "title": "Nguồn thật"}
                        ]
                    },
                },
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": content.model_dump_json()}
                    ],
                },
            ]
        }
    ).encode("utf-8")
    provider = OpenAIResponsesProvider(
        api_key="test-key-not-a-real-secret",
        base_url="https://api.openai.com/v1",
        model="test-model",
        prompt_version="prompt-v1",
        timeout_seconds=4,
        max_retries=0,
        max_output_tokens=1200,
        transport=Transport(response),
    )

    with pytest.raises(ProviderInvalidResponseError):
        provider.generate(
            artifact_id=artifact.id,
            normalized_input=catalog.normalized_input,
            use_web_search=True,
        )


def test_responses_provider_retries_only_bounded_retryable_failures() -> None:
    artifact, response = _content_response()
    transport = Transport(ProviderUnavailableError(), response)
    delays: list[float] = []
    provider = OpenAIResponsesProvider(
        api_key="test-key-not-a-real-secret",
        base_url="https://api.openai.com/v1",
        model="test-model",
        prompt_version="prompt-v1",
        timeout_seconds=1,
        max_retries=1,
        max_output_tokens=1200,
        retry_base_seconds=0.01,
        transport=transport,
        sleeper=delays.append,
    )

    provider.generate(
        artifact_id=artifact.id,
        normalized_input=build_evidence_catalog(artifact).normalized_input,
    )

    assert len(transport.calls) == 2
    assert delays == [0.01]


def test_responses_provider_rejects_malformed_output() -> None:
    artifact = _verified_artifact()
    provider = OpenAIResponsesProvider(
        api_key="test-key-not-a-real-secret",
        base_url="https://api.openai.com/v1",
        model="test-model",
        prompt_version="prompt-v1",
        timeout_seconds=1,
        max_retries=0,
        max_output_tokens=1200,
        transport=Transport(b'{"output": []}'),
    )

    with pytest.raises(ProviderInvalidResponseError):
        provider.generate(
            artifact_id=artifact.id,
            normalized_input=build_evidence_catalog(artifact).normalized_input,
        )


def test_speech_provider_requests_vietnamese_wav_without_exposing_audio_in_json() -> None:
    transport = Transport(_wav())
    provider = OpenAISpeechProvider(
        api_key="test-key-not-a-real-secret",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini-tts",
        voice="coral",
        language="vi-VN",
        timeout_seconds=3,
        max_retries=0,
        transport=transport,
    )

    text = unicodedata.normalize(
        "NFD",
        "Nội dung thuyết minh kiểm thử bằng tiếng Việt.",
    ) + " <b>Không đọc thẻ</b> https://example.invalid/source"
    audio = provider.synthesize(text)

    request = json.loads(transport.calls[0]["body"])
    assert request["response_format"] == "wav"
    assert request["model"] == "gpt-4o-mini-tts"
    assert "hoàn toàn bằng tiếng Việt" in request["instructions"]
    assert "Không sử dụng ngữ điệu tiếng Anh" in request["instructions"]
    assert unicodedata.is_normalized("NFC", request["input"])
    assert "<b>" not in request["input"]
    assert "https://" not in request["input"]
    assert audio.startswith(b"RIFF")
