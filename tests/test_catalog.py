from __future__ import annotations

import json
from pathlib import Path

from src.dataset.catalog import iter_records, relative_posix


def test_record_has_stable_vector_id(tmp_path: Path) -> None:
    images = tmp_path / "images"
    metadata = tmp_path / "JSON"
    images.mkdir()
    metadata.mkdir()
    (images / "item_01.jpg").write_bytes(b"not decoded by catalog")
    document = {
        "dataset_name": "test", "version": "1",
        "locations": [{"id": "item", "images": [{"id": "item_01", "filename": "item_01.jpg"}]}],
    }
    (metadata / "item.json").write_text(json.dumps(document), encoding="utf-8")
    record = next(iter_records(images, metadata))
    assert record.vector_id == "item:item_01"


def test_relative_posix_rejects_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.jpg"
    try:
        relative_posix(outside, tmp_path)
    except ValueError:
        pass
    else:
        raise AssertionError("Expected path traversal to be rejected")
