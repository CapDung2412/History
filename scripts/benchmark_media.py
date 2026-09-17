"""Measure original-versus-thumbnail payloads without calling AI or Pinecone."""
from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from pathlib import Path

from src.api.media import ALLOWED_THUMBNAIL_WIDTHS, MediaService
from src.config import PROJECT_ROOT
from src.dataset.catalog import HeritageImage, iter_records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-root", type=Path, default=PROJECT_ROOT / "images")
    parser.add_argument("--json-root", type=Path, default=PROJECT_ROOT / "JSON")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--sample-count", type=int, default=12)
    parser.add_argument(
        "--cache-root",
        type=Path,
        default=PROJECT_ROOT / "data" / "benchmark-thumbnail-cache",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "reports" / "media-performance.json",
    )
    args = parser.parse_args()
    if args.width not in ALLOWED_THUMBNAIL_WIDTHS:
        parser.error(f"--width must be one of {sorted(ALLOWED_THUMBNAIL_WIDTHS)}")
    if args.sample_count < 1:
        parser.error("--sample-count must be positive")

    image_root = args.image_root.resolve()
    json_root = args.json_root.resolve()
    grouped: dict[str, list[HeritageImage]] = defaultdict(list)
    for record in iter_records(image_root, json_root):
        grouped[str(record.location["id"])].append(record)
    if not grouped:
        raise RuntimeError("Dataset contains no image records")
    item_id, records = max(grouped.items(), key=lambda entry: len(entry[1]))
    sample = records[: args.sample_count]
    service = MediaService(image_root, args.cache_root)

    original_bytes = sum(record.image_path.stat().st_size for record in sample)
    started = time.perf_counter()
    thumbnails = [
        service.get(record.image_path.relative_to(image_root).as_posix(), args.width)
        for record in sample
    ]
    cold_ms = (time.perf_counter() - started) * 1_000
    thumbnail_bytes = sum(asset.path.stat().st_size for asset in thumbnails)

    started = time.perf_counter()
    warm = [
        service.get(record.image_path.relative_to(image_root).as_posix(), args.width)
        for record in sample
    ]
    warm_ms = (time.perf_counter() - started) * 1_000
    assert [asset.path for asset in thumbnails] == [asset.path for asset in warm]

    report = {
        "item_id": item_id,
        "sample_images": len(sample),
        "thumbnail_width": args.width,
        "original_total_bytes": original_bytes,
        "thumbnail_total_bytes": thumbnail_bytes,
        "payload_reduction_percent": round(
            (1 - thumbnail_bytes / original_bytes) * 100,
            2,
        ),
        "cold_generation_ms": round(cold_ms, 2),
        "warm_cache_lookup_ms": round(warm_ms, 2),
        "method": "Same dataset images; byte totals compare originals with cached WebP derivatives.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
