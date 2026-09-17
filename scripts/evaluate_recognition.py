"""Evaluate the live recognition API without calling OpenAI services.

The known-image portion is a deterministic closed-set retrieval benchmark:
one local reference image is sampled from each of several distinct artifacts.
The negative portion checks rejection of unusable captures and simple
out-of-domain synthetic images. Results are written as JSON for auditability.
"""
from __future__ import annotations

import argparse
import io
import json
import random
import statistics
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageFilter

from src.config import PROJECT_ROOT, Settings
from src.repositories.loader import load_artifacts


def _post_with_rate_limit_retry(
    client: httpx.Client,
    filename: str,
    payload: bytes,
    *,
    max_wait_seconds: float = 180.0,
) -> tuple[httpx.Response, float]:
    deadline = time.monotonic() + max_wait_seconds
    transient_retries = 0
    while True:
        started = time.perf_counter()
        response = client.post(
            "/api/v1/recognitions",
            files={"file": (filename, payload)},
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        if response.status_code in {502, 503, 504} and transient_retries < 2:
            transient_retries += 1
            if time.monotonic() >= deadline:
                return response, elapsed_ms
            time.sleep(2.0)
            continue
        if response.status_code != 429:
            return response, elapsed_ms
        if time.monotonic() >= deadline:
            return response, elapsed_ms
        retry_after = response.headers.get("Retry-After", "10")
        try:
            wait_seconds = max(1.0, min(float(retry_after), 15.0))
        except ValueError:
            wait_seconds = 10.0
        time.sleep(wait_seconds)


def _encode(image: Image.Image, image_format: str = "JPEG") -> bytes:
    output = io.BytesIO()
    image.save(output, format=image_format, quality=88)
    return output.getvalue()


def _negative_image(kind: str, source_path: Path, seed: int) -> tuple[str, bytes]:
    with Image.open(source_path) as opened:
        source = opened.convert("RGB")
        if kind == "too_dark":
            image = source.point(lambda value: int(value * 0.025))
        elif kind == "too_bright":
            white = Image.new("RGB", source.size, "white")
            image = Image.blend(source, white, 0.975)
        elif kind == "blurry":
            image = source.filter(ImageFilter.GaussianBlur(radius=28))
        elif kind == "too_small":
            image = source.copy()
            image.thumbnail((180, 180), Image.Resampling.LANCZOS)
        elif kind == "out_of_domain":
            width, height = 640, 480
            pixels = random.Random(seed).randbytes(width * height * 3)
            image = Image.frombytes("RGB", (width, height), pixels)
        else:
            raise ValueError(f"Unsupported negative kind: {kind}")
        try:
            return f"negative-{kind}-{seed}.jpg", _encode(image)
        finally:
            image.close()
            source.close()


def _percent(numerator: int, denominator: int) -> float:
    return round(100.0 * numerator / denominator, 2) if denominator else 0.0


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return round(ordered[index], 3)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--known-count", type=int, default=100)
    parser.add_argument("--negative-count", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20260917)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "reports" / "recognition-evaluation.json",
    )
    args = parser.parse_args()
    if args.known_count < 1 or args.negative_count < 1:
        parser.error("sample counts must be positive")

    settings = Settings.load()
    artifacts = load_artifacts(settings.json_root, settings.image_root)
    eligible = [artifact for artifact in artifacts.values() if artifact.images]
    if args.known_count > len(eligible):
        parser.error(f"known-count exceeds {len(eligible)} artifacts with images")

    rng = random.Random(args.seed)
    rng.shuffle(eligible)
    selected = eligible[: args.known_count]
    known_cases: list[tuple[str, str, Path, str]] = []
    for artifact in selected:
        image = rng.choice(artifact.images)
        known_cases.append(
            (
                artifact.id,
                image.relative_path,
                settings.image_root / Path(image.relative_path),
                artifact.category,
            )
        )

    results: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    issue_counts: Counter[str] = Counter()
    top1_correct = 0
    top3_correct = 0
    errors: list[dict[str, Any]] = []

    with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=180.0) as client:
        health = client.get("/api/v1/health")
        health.raise_for_status()

        for index, (expected_id, relative_path, image_path, category) in enumerate(
            known_cases, start=1
        ):
            response, elapsed_ms = _post_with_rate_limit_retry(
                client, image_path.name, image_path.read_bytes()
            )
            if response.status_code != 200:
                errors.append(
                    {
                        "case": "known",
                        "expected_item_id": expected_id,
                        "relative_path": relative_path,
                        "status_code": response.status_code,
                    }
                )
                continue
            body = response.json()
            candidate_ids = [candidate["item_id"] for candidate in body.get("candidates", [])]
            is_top1 = bool(candidate_ids) and candidate_ids[0] == expected_id
            is_top3 = expected_id in candidate_ids[:3]
            top1_correct += int(is_top1)
            top3_correct += int(is_top3)
            status_counts[body["recognition_status"]] += 1
            issues = [issue["code"] for issue in body["quality"].get("issues", [])]
            issue_counts.update(issues)
            results.append(
                {
                    "case": "known",
                    "expected_item_id": expected_id,
                    "category": category,
                    "relative_path": relative_path,
                    "recognition_status": body["recognition_status"],
                    "candidate_ids": candidate_ids,
                    "top1_correct": is_top1,
                    "top3_correct": is_top3,
                    "top_score": body.get("top_score"),
                    "quality_issues": issues,
                    "roundtrip_ms": round(elapsed_ms, 3),
                    "server_total_ms": body.get("timings_ms", {}).get("total"),
                }
            )
            if index % 10 == 0:
                print(f"Known images: {index}/{args.known_count}", flush=True)

        negative_kinds = (
            "too_dark",
            "too_bright",
            "blurry",
            "too_small",
            "out_of_domain",
        )
        rejected_negatives = 0
        rejected_by_kind: Counter[str] = Counter()
        for index in range(args.negative_count):
            kind = negative_kinds[index % len(negative_kinds)]
            source_path = known_cases[index % len(known_cases)][2]
            filename, payload = _negative_image(kind, source_path, args.seed + index)
            response, elapsed_ms = _post_with_rate_limit_retry(client, filename, payload)
            if response.status_code != 200:
                errors.append(
                    {
                        "case": "negative",
                        "negative_kind": kind,
                        "status_code": response.status_code,
                    }
                )
                continue
            body = response.json()
            rejected = body["recognition_status"] == "rejected"
            rejected_negatives += int(rejected)
            rejected_by_kind[kind] += int(rejected)
            status_counts[body["recognition_status"]] += 1
            issues = [issue["code"] for issue in body["quality"].get("issues", [])]
            issue_counts.update(issues)
            results.append(
                {
                    "case": "negative",
                    "negative_kind": kind,
                    "recognition_status": body["recognition_status"],
                    "rejected_correctly": rejected,
                    "top_score": body.get("top_score"),
                    "quality_issues": issues,
                    "roundtrip_ms": round(elapsed_ms, 3),
                    "server_total_ms": body.get("timings_ms", {}).get("total"),
                }
            )
            if (index + 1) % 5 == 0:
                print(f"Negative images: {index + 1}/{args.negative_count}", flush=True)

    roundtrip_values = [float(row["roundtrip_ms"]) for row in results]
    server_values = [
        float(row["server_total_ms"])
        for row in results
        if row.get("server_total_ms") is not None
    ]
    summary = {
        "total_attempts": args.known_count + args.negative_count,
        "successful_responses": len(results),
        "request_errors": len(errors),
        "known_images": args.known_count,
        "top1_correct": top1_correct,
        "top1_accuracy_percent": _percent(top1_correct, args.known_count),
        "top3_correct": top3_correct,
        "top3_accuracy_percent": _percent(top3_correct, args.known_count),
        "negative_images": args.negative_count,
        "correct_rejections": rejected_negatives,
        "correct_rejection_percent": _percent(rejected_negatives, args.negative_count),
        "average_roundtrip_ms": round(statistics.fmean(roundtrip_values), 3),
        "median_roundtrip_ms": round(statistics.median(roundtrip_values), 3),
        "p95_roundtrip_ms": _percentile(roundtrip_values, 0.95),
        "average_server_total_ms": round(statistics.fmean(server_values), 3),
        "recognition_status_counts": dict(sorted(status_counts.items())),
        "quality_issue_counts": dict(sorted(issue_counts.items())),
        "correct_rejections_by_kind": dict(sorted(rejected_by_kind.items())),
    }
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url,
        "seed": args.seed,
        "openai_calls": 0,
        "methodology": {
            "known": "Closed-set retrieval: one existing reference image from each sampled artifact.",
            "negative": "Synthetic unusable captures (dark, bright, blurred, small) and random out-of-domain noise.",
            "limitation": "This does not measure generalization to new phone photographs; a separate holdout set is required.",
        },
        "summary": summary,
        "errors": errors,
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    print(f"Report: {args.output}", flush=True)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
