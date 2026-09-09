"""Scan project text/build files without printing credential values."""
from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

from dotenv import dotenv_values

from src.config import PROJECT_ROOT


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--include-build", action="store_true")
    args = parser.parse_args()
    values = dotenv_values(PROJECT_ROOT / ".env")
    secrets = [
        value for key, value in values.items()
        if value and len(value) >= 16 and any(word in key for word in ("KEY", "TOKEN", "SECRET"))
        and not value.startswith(("replace-", "your-"))
    ]
    excluded = {".git", ".venv", ".tools", "node_modules", "__pycache__", ".pytest_cache", "images", "JSON", "data", "reports"}
    if not args.include_build:
        excluded.add(".next")
    suffixes = {".py", ".ps1", ".md", ".json", ".js", ".mjs", ".ts", ".tsx", ".html", ".sql", ".txt", ".css", ".map"}
    token_pattern = re.compile(r"(?:pcsk_|sb_secret_)[A-Za-z0-9_-]{24,}")
    matches = []
    checked = 0
    for parent, dirs, files in os.walk(PROJECT_ROOT):
        dirs[:] = [name for name in dirs if name not in excluded]
        for name in files:
            path = Path(parent) / name
            if name == ".env" or name.endswith(".local"):
                continue
            if path.suffix not in suffixes and name != ".env.example":
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except (UnicodeError, OSError):
                continue
            checked += 1
            if any(secret in content for secret in secrets) or token_pattern.search(content):
                matches.append(path.relative_to(PROJECT_ROOT).as_posix())
    print(f"Scanned {checked} project text files; potential credential files: {len(matches)}")
    for path in matches:
        print(path)
    return int(bool(matches))


if __name__ == "__main__":
    raise SystemExit(main())
