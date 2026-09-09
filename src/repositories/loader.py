from __future__ import annotations

from pathlib import Path
from typing import Any

from src.dataset.catalog import image_index, load_document, relative_posix

from .base import RepositoryIntegrityError
from .helpers import require_public_id, source_record
from .models import (
    ArtifactRecord,
    HistoricalInfoRecord,
    ImageRecord,
    LocationRecord,
)


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise RepositoryIntegrityError("Boolean value is not a valid year")
    return int(value)


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise RepositoryIntegrityError("Boolean value is not a valid coordinate")
    return float(value)


def load_artifacts(json_root: Path, image_root: Path) -> dict[str, ArtifactRecord]:
    """Load the canonical JSON dataset without changing or enriching its facts."""

    indexed_images = image_index(image_root)
    artifacts: dict[str, ArtifactRecord] = {}
    seen_image_ids: set[str] = set()

    for json_path in sorted(json_root.rglob("*.json")):
        document = load_document(json_path)
        dataset_name = str(document.get("dataset_name", "")).strip()
        dataset_version = str(document.get("version", "")).strip()
        for raw_item in document.get("locations", []):
            item_id = require_public_id(str(raw_item.get("id", "")))
            if item_id in artifacts:
                raise RepositoryIntegrityError(f"Duplicate artifact id: {item_id}")

            raw_location = raw_item.get("location") or {}
            location = LocationRecord(
                address=_optional_text(raw_location.get("address")),
                city=_optional_text(raw_location.get("city")),
                province=_optional_text(raw_location.get("province")),
                country=_optional_text(raw_location.get("country")),
                latitude=_optional_float(raw_location.get("latitude")),
                longitude=_optional_float(raw_location.get("longitude")),
            )

            raw_history = raw_item.get("historical_info") or {}
            raw_source = _optional_text(raw_history.get("source"))
            history = HistoricalInfoRecord(
                title=str(raw_history.get("title", "")).strip(),
                description=str(raw_history.get("description", "")).strip(),
                historical_period=_optional_text(raw_history.get("historical_period")),
                year=_optional_int(raw_history.get("year")),
                event=_optional_text(raw_history.get("event")),
                source=raw_source,
                source_status="available" if raw_source else "missing",
            )

            images: list[ImageRecord] = []
            for sort_order, raw_image in enumerate(raw_item.get("images", [])):
                image_id = str(raw_image.get("id", "")).strip()
                if not image_id or image_id in seen_image_ids:
                    raise RepositoryIntegrityError(f"Missing or duplicate image id: {image_id!r}")
                seen_image_ids.add(image_id)
                filename = str(raw_image.get("filename", "")).strip()
                matches = indexed_images.get(filename.casefold(), [])
                if len(matches) != 1:
                    raise RepositoryIntegrityError(
                        f"Expected exactly one local image for {filename!r}; found {len(matches)}"
                    )
                images.append(
                    ImageRecord(
                        id=image_id,
                        item_id=item_id,
                        filename=filename,
                        relative_path=relative_posix(matches[0], image_root),
                        drive_url=_optional_text(raw_image.get("drive_url")),
                        caption=str(raw_image.get("caption", "")).strip(),
                        year=_optional_int(raw_image.get("year")),
                        view=_optional_text(raw_image.get("view")),
                        sort_order=sort_order,
                    )
                )

            source = source_record(item_id, raw_source)
            artifacts[item_id] = ArtifactRecord(
                id=item_id,
                slug=require_public_id(str(raw_item.get("slug", "")), "slug"),
                name=str(raw_item.get("name", "")).strip(),
                category=str(raw_item.get("category", "")).strip(),
                tags=tuple(str(tag).strip() for tag in raw_item.get("tags", []) if str(tag).strip()),
                dataset_name=dataset_name,
                dataset_version=dataset_version,
                location=location,
                historical_info=history,
                images=tuple(images),
                sources=(source,) if source else (),
            )
    return artifacts
