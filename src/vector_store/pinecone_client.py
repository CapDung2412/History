from __future__ import annotations

import math
import os
import time
from typing import Any, Sequence

from pinecone import Pinecone, ServerlessSpec


class PineconeStore:
    def __init__(self, api_key: str, index_name: str, namespace: str, cloud: str, region: str) -> None:
        timeout = float(os.getenv("PINECONE_TIMEOUT_SECONDS", "30"))
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("PINECONE_TIMEOUT_SECONDS must be a positive finite number")
        # Pinecone 9 propagates this client timeout to control/data-plane calls.
        self.client = Pinecone(api_key=api_key, timeout=timeout)
        self.index_name = index_name
        self.namespace = namespace
        self.cloud = cloud
        self.region = region
        self._index: Any | None = None

    def ensure_index(self, dimension: int, create: bool = False) -> None:
        if not self.client.has_index(self.index_name):
            if not create:
                raise RuntimeError(f"Pinecone index {self.index_name!r} does not exist; pass --create-index")
            self.client.create_index(
                name=self.index_name, vector_type="dense", dimension=dimension, metric="cosine",
                spec=ServerlessSpec(cloud=self.cloud, region=self.region), deletion_protection="disabled",
            )
            while not self.client.describe_index(self.index_name).status["ready"]:
                time.sleep(2)
        description = self.client.describe_index(self.index_name)
        if int(description.dimension) != dimension or str(description.metric) != "cosine":
            raise RuntimeError(
                f"Incompatible index: dimension={description.dimension}, metric={description.metric}; "
                f"expected dimension={dimension}, metric=cosine"
            )

    @property
    def index(self):
        if self._index is None:
            description = self.client.describe_index(self.index_name)
            self._index = self.client.Index(host=description.host)
        return self._index

    def upsert(self, vectors: Sequence[dict[str, Any]], retries: int = 4) -> None:
        for attempt in range(retries):
            try:
                self.index.upsert(vectors=list(vectors), namespace=self.namespace)
                return
            except Exception:
                if attempt == retries - 1:
                    raise
                time.sleep(2**attempt)

    def query(
        self, vector: Sequence[float], top_k: int, score_filter: float | None = None,
        model_name: str | None = None,
    ) -> list[dict[str, Any]]:
        query_filter: dict[str, Any] = {"embedding_type": {"$eq": "image"}}
        if model_name:
            query_filter = {"$and": [query_filter, {"model_name": {"$eq": model_name}}]}
        response = self.index.query(
            namespace=self.namespace, vector=[float(value) for value in vector], top_k=top_k,
            include_metadata=True, filter=query_filter,
        )
        matches = []
        for match in response.matches:
            score = float(match.score)
            if score_filter is None or score >= score_filter:
                matches.append({"id": match.id, "score": score, "metadata": dict(match.metadata or {})})
        return matches
