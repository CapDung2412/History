from __future__ import annotations

import hashlib
import mimetypes
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError


ALLOWED_THUMBNAIL_WIDTHS = frozenset({320, 640, 960, 1280})


class MediaAssetError(Exception):
    """Raised when a public media path cannot be served safely."""


@dataclass(frozen=True, slots=True)
class MediaAsset:
    path: Path
    media_type: str
    cache_control: str
    etag: str


class MediaService:
    """Resolve dataset images and create bounded, cached WebP derivatives."""

    def __init__(self, image_root: Path, cache_root: Path) -> None:
        self.image_root = image_root.resolve()
        self.cache_root = cache_root.resolve()
        self._write_lock = threading.Lock()

    def get(self, relative_path: str, width: int | None = None) -> MediaAsset:
        source = self._resolve_source(relative_path)
        stat = source.stat()
        source_tag = self._source_tag(relative_path, stat.st_mtime_ns, stat.st_size)

        if width is None:
            media_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
            return MediaAsset(
                path=source,
                media_type=media_type,
                cache_control="public, max-age=3600, stale-while-revalidate=86400",
                etag=f'"{source_tag}"',
            )
        if width not in ALLOWED_THUMBNAIL_WIDTHS:
            raise ValueError("Unsupported thumbnail width")

        derivative_tag = hashlib.sha256(
            f"webp-v2:{source_tag}:{width}".encode("utf-8")
        ).hexdigest()
        target = self.cache_root / derivative_tag[:2] / f"{derivative_tag}.webp"
        if not target.is_file():
            self._create_thumbnail(source, target, width)
        return MediaAsset(
            path=target,
            media_type="image/webp",
            cache_control="public, max-age=86400, stale-while-revalidate=604800",
            etag=f'"{derivative_tag}"',
        )

    def _resolve_source(self, relative_path: str) -> Path:
        raw = str(relative_path).replace("\\", "/").strip("/")
        candidate = Path(raw)
        if not raw or candidate.is_absolute() or candidate.drive or ".." in candidate.parts:
            raise MediaAssetError("Unsafe media path")
        target = (self.image_root / candidate).resolve()
        if not target.is_relative_to(self.image_root) or not target.is_file():
            raise MediaAssetError("Media not found")
        return target

    @staticmethod
    def _source_tag(relative_path: str, modified_ns: int, size: int) -> str:
        normalized_path = relative_path.replace("\\", "/")
        return hashlib.sha256(
            f"{normalized_path}:{modified_ns}:{size}".encode("utf-8")
        ).hexdigest()

    def _create_thumbnail(self, source: Path, target: Path, width: int) -> None:
        with self._write_lock:
            if target.is_file():
                return
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
            try:
                with Image.open(source) as opened:
                    image = ImageOps.exif_transpose(opened)
                    if image.width <= 0 or image.height <= 0:
                        raise MediaAssetError("Invalid image dimensions")
                    target_height = max(1, round(image.height * min(width, image.width) / image.width))
                    image.thumbnail((width, target_height), Image.Resampling.LANCZOS)
                    if image.mode not in {"RGB", "RGBA"}:
                        image = image.convert("RGB")
                    # Method 2 keeps first-view generation responsive while
                    # preserving a large network reduction for museum photos.
                    image.save(temporary, format="WEBP", quality=80, method=2)
                os.replace(temporary, target)
            except (OSError, UnidentifiedImageError) as exc:
                raise MediaAssetError("Thumbnail could not be generated") from exc
            finally:
                temporary.unlink(missing_ok=True)
