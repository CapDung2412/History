from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.vector_store.pinecone_client import PineconeStore


@patch("src.vector_store.pinecone_client.Pinecone")
def test_query_filters_image_embeddings(client_class: MagicMock) -> None:
    client = client_class.return_value
    client.describe_index.return_value.host = "test-host"
    index = client.Index.return_value
    index.query.return_value.matches = []
    store = PineconeStore("key", "index", "namespace", "aws", "us-east-1")
    store.query([0.0, 1.0], top_k=5)
    index.query.assert_called_once_with(
        namespace="namespace", vector=[0.0, 1.0], top_k=5,
        include_metadata=True, filter={"embedding_type": {"$eq": "image"}},
    )


@patch("src.vector_store.pinecone_client.Pinecone")
def test_query_converts_numpy_values_to_json_safe_floats(client_class: MagicMock) -> None:
    client = client_class.return_value
    client.describe_index.return_value.host = "test-host"
    index = client.Index.return_value
    index.query.return_value.matches = []
    store = PineconeStore("key", "index", "namespace", "aws", "us-east-1")

    store.query(np.asarray([0.25, 0.75], dtype=np.float32), top_k=3)

    sent_vector = index.query.call_args.kwargs["vector"]
    assert sent_vector == [0.25, 0.75]
    assert all(type(value) is float for value in sent_vector)


@patch("src.vector_store.pinecone_client.Pinecone")
def test_timeout_is_configured_without_changing_index(client_class: MagicMock, monkeypatch) -> None:
    monkeypatch.setenv("PINECONE_TIMEOUT_SECONDS", "12")
    PineconeStore("key", "index", "namespace", "aws", "us-east-1")
    client_class.assert_called_once_with(api_key="key", timeout=12.0)
    client_class.return_value.create_index.assert_not_called()
    monkeypatch.setenv("PINECONE_TIMEOUT_SECONDS", "nan")
    with pytest.raises(ValueError, match="positive finite"):
        PineconeStore("key", "index", "namespace", "aws", "us-east-1")
