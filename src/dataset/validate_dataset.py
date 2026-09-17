from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from PIL import Image, ImageOps, UnidentifiedImageError

from src.config import PROJECT_ROOT, Settings
from src.dataset.catalog import IMAGE_SUFFIXES, image_index, load_document
from src.text import contains_mojibake


def issue(level: str, code: str, message: str, path: Path | None = None) -> dict[str, str]:
    value = {"level": level, "code": code, "message": message}
    if path is not None:
        value["path"] = str(path)
    return value


def validate(image_root: Path, json_root: Path, schema_path: Path) -> dict[str, Any]:
    problems: list[dict[str, str]] = []
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema_validator = Draft202012Validator(schema)
    images = image_index(image_root)
    image_paths = [path for paths in images.values() for path in paths]
    referenced: Counter[str] = Counter()
    location_ids: Counter[str] = Counter()
    image_ids: Counter[str] = Counter()
    slugs: Counter[str] = Counter()
    formats: Counter[str] = Counter()
    modes: Counter[str] = Counter()
    json_files = sorted(json_root.rglob("*.json"))

    for filename, paths in images.items():
        if len(paths) > 1:
            problems.append(issue("error", "duplicate_filename", f"{filename} occurs {len(paths)} times"))
    for path in image_paths:
        try:
            with Image.open(path) as source:
                ImageOps.exif_transpose(source)
                source.verify()
            with Image.open(path) as source:
                formats[source.format or path.suffix.lower()] += 1
                modes[source.mode] += 1
                if min(source.size) < 224:
                    problems.append(issue("warning", "small_image", f"Image is {source.width}x{source.height}", path))
        except (OSError, UnidentifiedImageError) as exc:
            problems.append(issue("error", "unreadable_image", str(exc), path))

    valid_json = 0
    for path in json_files:
        try:
            raw_text = path.read_text(encoding="utf-8")
            if raw_text != unicodedata.normalize("NFC", raw_text):
                problems.append(
                    issue("warning", "non_nfc_text", "JSON text is not normalized to Unicode NFC", path)
                )
            if contains_mojibake(raw_text):
                problems.append(
                    issue("error", "mojibake_text", "JSON contains likely broken UTF-8 text", path)
                )
            document = load_document(path)
            valid_json += 1
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            problems.append(issue("error", "invalid_json", str(exc), path))
            continue
        for error in schema_validator.iter_errors(document):
            location = "/".join(str(part) for part in error.absolute_path)
            problems.append(issue("error", "schema", f"{location}: {error.message}", path))
        for location in document.get("locations", []):
            location_ids[str(location.get("id", ""))] += 1
            slugs[str(location.get("slug", ""))] += 1
            if not location.get("historical_info", {}).get("source"):
                problems.append(issue("warning", "missing_source", "historical_info.source is empty", path))
            for image in location.get("images", []):
                filename = str(image.get("filename", ""))
                image_ids[str(image.get("id", ""))] += 1
                referenced[filename.casefold()] += 1
                if "/" in filename or "\\" in filename or ".." in Path(filename).parts:
                    problems.append(issue("error", "unsafe_image_path", f"Unsafe filename: {filename}", path))
                count = len(images.get(filename.casefold(), []))
                if count == 0:
                    problems.append(issue("error", "missing_image", f"Image not found: {filename}", path))
                elif count > 1:
                    problems.append(issue("error", "ambiguous_image", f"Image resolves {count} times: {filename}", path))

    for label, counter in (("location_id", location_ids), ("image_id", image_ids), ("slug", slugs)):
        for value, count in counter.items():
            if value and count > 1:
                problems.append(issue("error", f"duplicate_{label}", f"{value} occurs {count} times"))
    for path in image_paths:
        if referenced[path.name.casefold()] == 0:
            problems.append(issue("error", "unreferenced_image", "No JSON references this image", path))

    levels = Counter(item["level"] for item in problems)
    return {
        "summary": {
            "images": len(image_paths), "json_files": len(json_files), "valid_json": valid_json,
            "declared_images": sum(referenced.values()), "formats": dict(formats), "modes": dict(modes),
            "errors": levels["error"], "warnings": levels["warning"],
        },
        "issues": problems,
    }


def main() -> int:
    # Windows PowerShell may expose a legacy code page even when the project and
    # dataset are UTF-8. Keep Vietnamese paths/messages printable in that case.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    settings = Settings.load()
    parser = argparse.ArgumentParser(description="Validate the Di San Lens dataset")
    parser.add_argument("--images", type=Path, default=settings.image_root)
    parser.add_argument("--json", type=Path, default=settings.json_root)
    parser.add_argument("--schema", type=Path, default=PROJECT_ROOT / "schemas/heritage-item.schema.json")
    parser.add_argument("--report", type=Path, default=PROJECT_ROOT / "reports/dataset-validation.json")
    args = parser.parse_args()
    report = validate(args.images, args.json, args.schema)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = report["summary"]
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    for item in report["issues"]:
        print(f"[{item['level'].upper()}] {item['code']}: {item['message']} {item.get('path', '')}")
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
