from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from tqdm import tqdm

from src.clip.encoder import ClipEncoder
from src.config import Settings
from src.dataset.catalog import HeritageImage, iter_records, relative_posix
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Encode and index the Di San Lens dataset")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--create-index", action="store_true")
    args = parser.parse_args()
    settings = Settings.load(require_pinecone=not args.dry_run)
    report = validate(settings.image_root, settings.json_root, settings.project_root / "schemas/heritage-item.schema.json")
    if report["summary"]["errors"]:
        raise RuntimeError("Dataset validation failed; run src.dataset.validate_dataset for details")
    records = list(iter_records(settings.image_root, settings.json_root))
    print(f"Validated {len(records)} images")
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
    print(json.dumps({"indexed": len(records), "namespace": settings.pinecone_namespace}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
