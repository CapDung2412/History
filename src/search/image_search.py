from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.clip.encoder import ClipEncoder
from src.config import Settings
from src.vector_store.pinecone_client import PineconeStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Search Di San Lens using a query image")
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--min-score", type=float)
    args = parser.parse_args()
    if not args.image.is_file():
        parser.error(f"Image does not exist: {args.image}")
    settings = Settings.load(require_pinecone=True)
    encoder = ClipEncoder(settings.clip_model_name, settings.clip_pretrained, settings.clip_device)
    store = PineconeStore(settings.pinecone_api_key or "", settings.pinecone_index_name, settings.pinecone_namespace, settings.pinecone_cloud, settings.pinecone_region)
    store.ensure_index(encoder.dimension)
    # Retrieve extra candidates, then keep the best view for each heritage item.
    matches = store.query(
        encoder.encode_image(args.image),
        min(100, max(50, args.top_k * 10)),
        args.min_score,
        model_name=f"{encoder.model_name}:{encoder.pretrained}",
    )
    grouped: dict[str, dict] = {}
    for match in matches:
        item_id = str(match["metadata"].get("item_id", match["id"]))
        if item_id not in grouped:
            grouped[item_id] = match
    print(json.dumps(list(grouped.values())[: args.top_k], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
