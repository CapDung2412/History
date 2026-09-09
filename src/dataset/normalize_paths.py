from __future__ import annotations

import argparse
import json
import shutil
import unicodedata
from pathlib import Path

from src.config import PROJECT_ROOT

MAPPING = {
    "Hậu quả chất độc da cam": "agent-orange-consequences",
    "Máy bay, xe tăng và trực thăng": "aircraft-tanks-and-helicopters",
    "Thế giới ủng hộ Việt Nam kháng chiến chống Mỹ 1954 - 1975": "international-support-for-vietnam-1954-1975",
    "Thế giới ủng hộ Việt Nam": "international-support-for-vietnam",
    "Thời thanh xuân trên tuyến đường 1C huyền thoại": "youth-on-the-legendary-route-1c",
    "Thời thanh xuân trên tuyến đường 1C": "youth-on-route-1c",
    "Tội ác chiến tranh xâm lược": "war-crimes",
    "Các tổ chức quốc tế": "international-organizations",
    "Châu Á": "asia", "Châu Âu": "europe", "Châu Đại Dương": "oceania",
    "Châu Mỹ": "americas", "Châu Phi": "africa",
}


def ascii_slug(value: str) -> str:
    value = value.replace("Đ", "D").replace("đ", "d")
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()
    return "-".join(part for part in __import__("re").split(r"[^a-z0-9]+", value) if part)


def mapped(name: str) -> str:
    return MAPPING.get(name, ascii_slug(name))


def plan_tree(source: Path, target: Path) -> list[tuple[Path, Path]]:
    plan: list[tuple[Path, Path]] = []
    destinations: set[Path] = set()
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        parts = [mapped(part) for part in relative.parts[:-1]] + [relative.name]
        destination = target.joinpath(*parts)
        if destination in destinations or (destination.exists() and destination.resolve() != path.resolve()):
            raise ValueError(f"Destination collision: {destination}")
        destinations.add(destination)
        plan.append((path, destination))
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan or apply ASCII dataset paths")
    parser.add_argument("--image-source", type=Path, default=PROJECT_ROOT / "images")
    parser.add_argument("--json-source", type=Path, default=PROJECT_ROOT / "JSON")
    parser.add_argument("--target-root", type=Path, default=PROJECT_ROOT / "data")
    parser.add_argument("--apply", action="store_true", help="Copy into data/; source files are preserved")
    args = parser.parse_args()
    plans = plan_tree(args.image_source, args.target_root / "images") + plan_tree(args.json_source, args.target_root / "metadata")
    for source, target in plans:
        print(f"{source.relative_to(PROJECT_ROOT)} -> {target.relative_to(PROJECT_ROOT)}")
    if args.apply:
        for source, target in plans:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        manifest = {str(src.relative_to(PROJECT_ROOT)): str(dst.relative_to(PROJECT_ROOT)).replace("\\", "/") for src, dst in plans}
        path = args.target_root / "path-mapping.json"
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Copied {len(plans)} files; originals preserved. Manifest: {path}")
    else:
        print(f"Dry run: {len(plans)} files; pass --apply to copy them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
