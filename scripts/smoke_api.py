"""Opt-in smoke check against a running API and its real CLIP/Pinecone services.

Never creates an index or uploads vectors. The API records anonymous request
metrics; --feedback additionally records one anonymous feedback event.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--expect-item", help="Expected canonical location.id for a known image")
    parser.add_argument("--feedback", action="store_true", help="Record feedback for the returned Top-1")
    args = parser.parse_args()
    if not args.image.is_file():
        parser.error("--image must identify an existing image")

    with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=180) as client:
        client.get("/api/v1/health").raise_for_status()
        warmup = client.post("/api/v1/warmup")
        warmup.raise_for_status()
        with args.image.open("rb") as image:
            response = client.post("/api/v1/recognitions", files={"file": (args.image.name, image)})
        response.raise_for_status()
        result = response.json()
        candidates = result["candidates"]
        ids = [candidate["item_id"] for candidate in candidates]
        assert len(ids) == len(set(ids)), "Duplicate items in candidate list"
        assert len(ids) <= 3, "API returned more than Top-3"
        assert result["recognition_status"] in {"accepted", "needs_confirmation", "rejected"}
        if args.expect_item:
            assert ids and ids[0] == args.expect_item, "Expected item was not ranked first"
        content_checks = []
        if ids:
            for suffix in ("", "/story", "/challenge"):
                content = client.get(f"/api/v1/artifacts/{ids[0]}{suffix}")
                content.raise_for_status()
                content_checks.append(suffix or "/artifact")
            image_url = candidates[0].get("image_url")
            if image_url:
                media = client.get(image_url)
                media.raise_for_status()
                assert media.headers.get("content-type", "").startswith("image/")
        if args.feedback and ids:
            feedback = client.post(
                f"/api/v1/recognitions/{result['request_id']}/feedback",
                json={"is_correct": True, "selected_item_id": ids[0]},
            )
            feedback.raise_for_status()
        print(json.dumps({
            "quality": result["quality"]["status"],
            "recognition_status": result["recognition_status"],
            "candidate_ids": ids,
            "top_score": result["top_score"],
            "score_margin": result["score_margin"],
            "timings_ms": result["timings_ms"],
            "content_checks": content_checks,
            "feedback_recorded": bool(args.feedback and ids),
        }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
