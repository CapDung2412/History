from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Protocol

from PIL import Image

from src.clip.encoder import ClipEncoder
from src.config import Settings
from src.vector_store.pinecone_client import PineconeStore


class RecognitionUnavailableError(RuntimeError):
    """CLIP or the configured vector store is unavailable."""


class RecognitionEngine(Protocol):
    @property
    def loaded(self) -> bool: ...

    def warmup(self) -> tuple[str, int]: ...

    def query(self, image: Image.Image, top_k: int) -> tuple[list[dict[str, Any]], dict[str, float]]: ...


@dataclass(slots=True)
class _Runtime:
    encoder: ClipEncoder
    store: PineconeStore


class ClipPineconeEngine:
    """Lazy, process-local CLIP/Pinecone runtime.

    It only verifies an existing index with ``create=False``. It never creates,
    deletes, upserts, or reindexes vectors.
    """

    def __init__(self, core_settings: Settings | None = None) -> None:
        self._settings = core_settings
        self._runtime: _Runtime | None = None
        self._load_lock = threading.Lock()
        self._inference_lock = threading.Lock()

    @property
    def loaded(self) -> bool:
        return self._runtime is not None

    def _get_runtime(self) -> _Runtime:
        if self._runtime is not None:
            return self._runtime
        with self._load_lock:
            if self._runtime is not None:
                return self._runtime
            try:
                settings = self._settings or Settings.load(require_pinecone=True)
                encoder = ClipEncoder(
                    settings.clip_model_name,
                    settings.clip_pretrained,
                    settings.clip_device,
                )
                store = PineconeStore(
                    settings.pinecone_api_key or "",
                    settings.pinecone_index_name,
                    settings.pinecone_namespace,
                    settings.pinecone_cloud,
                    settings.pinecone_region,
                )
                # Explicit false is a safety invariant: API startup must never
                # create or mutate the user's existing Pinecone index.
                store.ensure_index(encoder.dimension, create=False)
                self._runtime = _Runtime(encoder=encoder, store=store)
            except Exception as exc:
                raise RecognitionUnavailableError("Recognition service is unavailable") from exc
        return self._runtime

    def warmup(self) -> tuple[str, int]:
        runtime = self._get_runtime()
        return (
            f"{runtime.encoder.model_name}:{runtime.encoder.pretrained}",
            runtime.encoder.dimension,
        )

    def query(self, image: Image.Image, top_k: int) -> tuple[list[dict[str, Any]], dict[str, float]]:
        runtime = self._get_runtime()
        try:
            encode_started = time.perf_counter()
            # Conservative serialization protects model implementations that are
            # not safe for concurrent inference on the same instance/device.
            with self._inference_lock:
                vector = runtime.encoder.encode_pil(image)
            encode_ms = (time.perf_counter() - encode_started) * 1000

            query_started = time.perf_counter()
            matches = runtime.store.query(
                vector,
                top_k,
                model_name=f"{runtime.encoder.model_name}:{runtime.encoder.pretrained}",
            )
            query_ms = (time.perf_counter() - query_started) * 1000
            return matches, {"clip": encode_ms, "pinecone": query_ms}
        except RecognitionUnavailableError:
            raise
        except Exception as exc:
            raise RecognitionUnavailableError("Recognition service is unavailable") from exc
