from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from src.api.media import MediaAssetError, MediaService


def _service(tmp_path: Path) -> tuple[MediaService, Path]:
    image_root = tmp_path / "images"
    image_root.mkdir()
    source = image_root / "artifact.jpg"
    Image.new("RGB", (1600, 1200), (80, 110, 140)).save(source, quality=92)
    return MediaService(image_root, tmp_path / "cache"), source


def test_media_service_creates_and_reuses_bounded_webp_thumbnail(tmp_path: Path) -> None:
    service, source = _service(tmp_path)

    original = service.get("artifact.jpg")
    thumbnail = service.get("artifact.jpg", 640)
    cached = service.get("artifact.jpg", 640)

    assert original.path == source.resolve()
    assert original.media_type == "image/jpeg"
    assert thumbnail.path == cached.path
    assert thumbnail.media_type == "image/webp"
    assert thumbnail.etag == cached.etag
    assert thumbnail.path.is_relative_to((tmp_path / "cache").resolve())
    with Image.open(thumbnail.path) as image:
        assert image.size == (640, 480)


def test_media_service_rejects_unbounded_sizes_and_path_traversal(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)

    with pytest.raises(ValueError, match="Unsupported"):
        service.get("artifact.jpg", 777)
    with pytest.raises(MediaAssetError, match="Unsafe"):
        service.get("../artifact.jpg")
    with pytest.raises(MediaAssetError, match="not found"):
        service.get("missing.jpg")
