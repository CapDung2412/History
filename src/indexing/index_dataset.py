from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from tqdm import tqdm

from src.clip.encoder import ClipEncoder
from src.config import Settings
from src.dataset.catalog import HeritageImage, image_index, iter_records, load_document, relative_posix
from src.dataset.validate_dataset import validate
from src.vector_store.pinecone_client import PineconeStore


def metadata(record: HeritageImage, settings: Settings, model: ClipEncoder) -> dict[str, Any]:
    info = record.location["historical_info"]
    place = record.location["location"]
    value: dict[str, Any] = {
        "item_id": record.location["id"], "image_id": record.image["id"],
        "title": info["title"], "description": info["description"][:6000],
        "category": record.location["category"], "period": info.get("historical_period") or "",
        "event": info.get("event") or "", "year": info.get("year") or 0,
        "source": info.get("source") or "",
        "location": ", ".join(str(v) for v in (place.get("address"), place.get("city"), place.get("country")) if v),
        "keywords": list(record.location.get("tags", [])), "caption": record.image.get("caption") or "",
        "view": record.image.get("view") or "", "image_path": relative_posix(record.image_path, settings.project_root),
        "embedding_type": "image", "model_name": f"{model.model_name}:{model.pretrained}",
        "dataset_version": record.version, "checksum": record.checksum,
    }
    return value


def selected_records(
    image_root: Path,
    json_root: Path,
    json_subdir: Path | None,
    skip_missing_images: bool,
) -> tuple[list[HeritageImage], list[tuple[Path, str]]]:
    """Collect records from one JSON subtree without silently misresolving images."""
    if json_subdir is None:
        return list(iter_records(image_root, json_root)), []

    selected_root = (json_root / json_subdir).resolve()
    resolved_json_root = json_root.resolve()
    try:
        selected_root.relative_to(resolved_json_root)
    except ValueError as exc:
        raise ValueError(f"JSON subdirectory escapes JSON_ROOT: {json_subdir}") from exc
    if not selected_root.is_dir():
        raise ValueError(f"JSON subdirectory does not exist: {selected_root}")

    images = image_index(image_root)
    records: list[HeritageImage] = []
    skipped: list[tuple[Path, str]] = []
    for json_path in sorted(selected_root.rglob("*.json")):
        document = load_document(json_path)
        for location in document.get("locations", []):
            for image in location.get("images", []):
                filename = str(image.get("filename", ""))
                matches = images.get(filename.casefold(), [])
                if not matches and skip_missing_images:
                    skipped.append((json_path, filename))
                    continue
                if len(matches) != 1:
                    raise ValueError(
                        f"Expected exactly one image for {filename!r}; found {len(matches)}"
                    )
                records.append(
                    HeritageImage(
                        json_path=json_path,
                        image_path=matches[0],
                        dataset_name=str(document.get("dataset_name", "")),
                        version=str(document.get("version", "")),
                        location=location,
                        image=image,
                    )
                )
    return records, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description="Encode and index the Di San Lens dataset")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--create-index", action="store_true")
    parser.add_argument(
        "--json-subdir",
        type=Path,
        help="Index only JSON files below this path relative to JSON_ROOT",
    )
    parser.add_argument(
        "--skip-missing-images",
        action="store_true",
        help="Skip declared image filenames that do not exist; ambiguous filenames still fail",
    )
    args = parser.parse_args()
    if args.skip_missing_images and args.json_subdir is None:
        parser.error("--skip-missing-images requires --json-subdir")
    settings = Settings.load(require_pinecone=not args.dry_run)
    report = validate(settings.image_root, settings.json_root, settings.project_root / "schemas/heritage-item.schema.json")
    errors = [item for item in report["issues"] if item["level"] == "error"]
    blocking_errors = [
        item for item in errors
        if not (args.skip_missing_images and item["code"] == "missing_image")
    ]
    if blocking_errors:
        raise RuntimeError("Dataset validation failed; run src.dataset.validate_dataset for details")
    records, skipped = selected_records(
        settings.image_root,
        settings.json_root,
        args.json_subdir,
        args.skip_missing_images,
    )
    print(f"Validated {len(records)} images")
    if skipped:
        print(f"Skipped {len(skipped)} missing image references")
    if args.dry_run:
        print("Dry run complete; model and Pinecone were not invoked.")
        return 0
    encoder = ClipEncoder(settings.clip_model_name, settings.clip_pretrained, settings.clip_device)
    store = PineconeStore(settings.pinecone_api_key or "", settings.pinecone_index_name, settings.pinecone_namespace, settings.pinecone_cloud, settings.pinecone_region)
    store.ensure_index(encoder.dimension, create=args.create_index)
    for start in tqdm(range(0, len(records), args.batch_size), desc="Indexing"):
        batch = records[start : start + args.batch_size]
        vectors = encoder.encode_images([record.image_path for record in batch], args.batch_size)
        payload = [{"id": record.vector_id, "values": vector.tolist(), "metadata": metadata(record, settings, encoder)} for record, vector in zip(batch, vectors)]
        store.upsert(payload)
    print(json.dumps({
        "indexed": len(records),
        "skipped_missing_images": len(skipped),
        "namespace": settings.pinecone_namespace,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
