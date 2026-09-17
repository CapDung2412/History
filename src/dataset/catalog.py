from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from src.text import normalize_unicode_tree

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}


@dataclass(frozen=True)
class HeritageImage:
    json_path: Path
    image_path: Path
    dataset_name: str
    version: str
    location: dict[str, Any]
    image: dict[str, Any]

    @property
    def vector_id(self) -> str:
        return f"{self.location['id']}:{self.image['id']}"

    @property
    def checksum(self) -> str:
        digest = hashlib.sha256()
        digest.update(self.image_path.read_bytes())
        digest.update(json.dumps(self.location, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        return digest.hexdigest()


def image_index(image_root: Path) -> dict[str, list[Path]]:
    result: dict[str, list[Path]] = {}
    for path in image_root.rglob("*"):
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
            result.setdefault(path.name.casefold(), []).append(path)
    return result


def load_document(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return normalize_unicode_tree(value)


def iter_records(image_root: Path, json_root: Path) -> Iterator[HeritageImage]:
    images = image_index(image_root)
    for json_path in sorted(json_root.rglob("*.json")):
        document = load_document(json_path)
        for location in document.get("locations", []):
            for image in location.get("images", []):
                matches = images.get(str(image.get("filename", "")).casefold(), [])
                if len(matches) != 1:
                    raise ValueError(
                        f"Expected exactly one image for {image.get('filename')!r}; found {len(matches)}"
                    )
                yield HeritageImage(
                    json_path=json_path,
                    image_path=matches[0],
                    dataset_name=str(document.get("dataset_name", "")),
                    version=str(document.get("version", "")),
                    location=location,
                    image=image,
                )


def relative_posix(path: Path, root: Path) -> str:
    resolved = path.resolve()
    base = root.resolve()
    try:
        return resolved.relative_to(base).as_posix()
    except ValueError as exc:
        raise ValueError(f"Path escapes dataset root: {path}") from exc
