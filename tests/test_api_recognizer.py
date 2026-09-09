from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from src.api.recognizer import ClipPineconeEngine
from src.config import Settings


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        project_root=tmp_path,
        image_root=tmp_path,
        json_root=tmp_path,
        clip_model_name="test-model",
        clip_pretrained="test-weights",
        clip_device="cpu",
        pinecone_api_key="placeholder",
        pinecone_index_name="existing-index",
        pinecone_namespace="existing-namespace",
        pinecone_cloud="aws",
        pinecone_region="test-region",
    )


def test_engine_reuses_model_filters_query_and_never_creates_index(monkeypatch, tmp_path: Path) -> None:
    calls: dict[str, object] = {"encoder_count": 0, "store_count": 0}

    class FakeEncoder:
        model_name = "test-model"
        pretrained = "test-weights"
        dimension = 512

        def __init__(self, *_args):
            calls["encoder_count"] = int(calls["encoder_count"]) + 1

        def encode_pil(self, _image):
            return np.zeros(512, dtype=np.float32)

    class FakeStore:
        def __init__(self, *_args):
            calls["store_count"] = int(calls["store_count"]) + 1

        def ensure_index(self, dimension, create=False):
            calls["ensure"] = (dimension, create)

        def query(self, vector, top_k, model_name=None):
            calls["query"] = (len(vector), top_k, model_name)
            return []

    monkeypatch.setattr("src.api.recognizer.ClipEncoder", FakeEncoder)
    monkeypatch.setattr("src.api.recognizer.PineconeStore", FakeStore)
    engine = ClipPineconeEngine(_settings(tmp_path))

    assert engine.warmup() == ("test-model:test-weights", 512)
    engine.query(Image.new("RGB", (400, 400)), 50)
    engine.warmup()

    assert calls["ensure"] == (512, False)
    assert calls["query"] == (512, 50, "test-model:test-weights")
    assert calls["encoder_count"] == 1
    assert calls["store_count"] == 1
