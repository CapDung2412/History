"""Find credential-shaped values without ever printing the matched value.

The default scan is pattern-only and deliberately does not open ``.env``.
Use ``--compare-local-env`` explicitly when an operator wants to compare
configured local secrets with source/build files. Git's staged snapshot and
historical blobs are optional because history scans can take considerably
longer on a large repository.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from dotenv import dotenv_values

from src.config import PROJECT_ROOT


@dataclass(frozen=True)
class SecretPattern:
    kind: str
    regex: re.Pattern[str]
    masked: str


@dataclass(frozen=True)
class Finding:
    scope: str
    path: str
    line: int
    column: int
    kind: str
    masked: str
    revision: str | None = None


STATIC_PATTERNS: tuple[SecretPattern, ...] = (
    # The assignment form also catches short test/development keys while the
    # standalone forms use conservative lengths to avoid matching filenames.
    SecretPattern(
        "openai_api_key_assignment",
        re.compile(
            r"\b(?:OPENAI_API_KEY|CHATGPT_API_KEY)\b\s*[:=]\s*[\"']?"
            r"sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{16,}",
            re.IGNORECASE,
        ),
        "OPENAI_OR_CHATGPT_API_KEY=sk-***",
    ),
    SecretPattern(
        "openai_project_key",
        re.compile(
            r"(?<![A-Za-z0-9_-])sk-proj-[A-Za-z0-9_-]{24,}"
            r"(?![A-Za-z0-9_-])"
        ),
        "sk-proj-***",
    ),
    SecretPattern(
        "openai_service_account_key",
        re.compile(
            r"(?<![A-Za-z0-9_-])sk-svcacct-[A-Za-z0-9_-]{24,}"
            r"(?![A-Za-z0-9_-])"
        ),
        "sk-svcacct-***",
    ),
    SecretPattern(
        "openai_legacy_key",
        re.compile(r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9]{32,}(?![A-Za-z0-9_-])"),
        "sk-***",
    ),
    SecretPattern(
        "pinecone_key",
        re.compile(r"(?<![A-Za-z0-9_-])pcsk_[A-Za-z0-9_-]{24,}(?![A-Za-z0-9_-])"),
        "pcsk_***",
    ),
    SecretPattern(
        "supabase_secret_key",
        re.compile(
            r"(?<![A-Za-z0-9_-])sb_secret_[A-Za-z0-9_-]{24,}"
            r"(?![A-Za-z0-9_-])"
        ),
        "sb_secret_***",
    ),
    SecretPattern(
        "private_key",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        "-----BEGIN *** PRIVATE KEY-----",
    ),
)

EXCLUDED_DIRS = {
    ".git",
    ".venv",
    ".tools",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "coverage",
    "images",
    "data",
    "reports",
}
BUILD_DIRS = {".next", "build", "dist", "out"}
TEXT_SUFFIXES = {
    ".bat", ".cfg", ".cjs", ".cmd", ".conf", ".css", ".html", ".ini",
    ".js", ".json", ".lock", ".map", ".md", ".mjs", ".properties",
    ".ps1", ".py", ".sh", ".sql", ".toml", ".ts", ".tsx", ".txt",
    ".xml", ".yaml", ".yml",
}
TEXT_NAMES = {
    ".env.example", ".gitignore", ".npmrc", ".pypirc",
    "Dockerfile", "Makefile", "Procfile",
}


class GitScanError(RuntimeError):
    """Raised with a safe message that never contains scanned content."""


def is_sensitive_env_path(path: Path) -> bool:
    name = path.name.lower()
    return (
        name == ".env"
        or (name.startswith(".env.") and name != ".env.example")
        or name.endswith(".local")
    )


def is_text_candidate(path: Path) -> bool:
    return path.name in TEXT_NAMES or path.suffix.lower() in TEXT_SUFFIXES


def configured_secret_patterns(root: Path) -> tuple[SecretPattern, ...]:
    """Load local configured secrets only after explicit operator opt-in."""
    env_path = root / ".env"
    if not env_path.is_file():
        return ()
    patterns: list[SecretPattern] = []
    seen: set[str] = set()
    for key, value in dotenv_values(env_path).items():
        normalized_key = (key or "").upper()
        if (
            not value
            or value in seen
            or len(value) < 16
            or not any(word in normalized_key for word in ("KEY", "TOKEN", "SECRET"))
            or value.startswith(("replace-", "your-"))
        ):
            continue
        seen.add(value)
        patterns.append(
            SecretPattern(
                "configured_secret",
                re.compile(re.escape(value)),
                f"<{normalized_key or 'CONFIGURED_SECRET'}:***>",
            )
        )
    return tuple(patterns)


def scan_text(
    text: str,
    *,
    scope: str,
    path: str,
    patterns: Sequence[SecretPattern],
    revision: str | None = None,
) -> list[Finding]:
    findings: list[Finding] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        candidates: list[tuple[int, int, int, SecretPattern]] = []
        for priority, pattern in enumerate(patterns):
            for match in pattern.regex.finditer(line):
                candidates.append((match.start(), match.end(), priority, pattern))

        # Prefer the first/more-specific pattern and suppress overlapping
        # matches, e.g. an assignment and its embedded OpenAI token.
        accepted: list[tuple[int, int]] = []
        for start, end, priority, pattern in sorted(
            candidates, key=lambda item: (item[0], item[2], -(item[1] - item[0]))
        ):
            if any(start < used_end and end > used_start for used_start, used_end in accepted):
                continue
            accepted.append((start, end))
            findings.append(
                Finding(
                    scope=scope,
                    path=path,
                    line=line_number,
                    column=start + 1,
                    kind=pattern.kind,
                    masked=pattern.masked,
                    revision=revision,
                )
            )
    return findings


def decode_text(data: bytes) -> str | None:
    # NUL is a reliable signal for generated/binary files here. Replacement
    # decoding still finds ASCII credentials in otherwise non-UTF-8 text.
    if b"\0" in data[:8192]:
        return None
    return data.decode("utf-8", errors="replace")


def scan_worktree(
    root: Path,
    patterns: Sequence[SecretPattern],
    *,
    include_build: bool = False,
) -> tuple[list[Finding], dict[str, int]]:
    findings: list[Finding] = []
    counts = {"source": 0, "build": 0}
    excluded = set(EXCLUDED_DIRS)
    if not include_build:
        excluded.update(BUILD_DIRS)

    for parent, dirs, files in os.walk(root):
        dirs[:] = [name for name in dirs if name not in excluded]
        for name in files:
            path = Path(parent) / name
            relative = path.relative_to(root)
            if is_sensitive_env_path(relative) or not is_text_candidate(relative):
                continue
            try:
                text = decode_text(path.read_bytes())
            except OSError:
                continue
            if text is None:
                continue
            scope = "build" if any(part in BUILD_DIRS for part in relative.parts) else "source"
            counts[scope] += 1
            findings.extend(
                scan_text(text, scope=scope, path=relative.as_posix(), patterns=patterns)
            )
    return findings, counts


def run_git(root: Path, *arguments: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise GitScanError("Git is unavailable; staged/history scan was not run.") from exc
    if result.returncode != 0:
        raise GitScanError("Git could not read the requested snapshot.")
    return result.stdout


def scan_staged(
    root: Path, patterns: Sequence[SecretPattern]
) -> tuple[list[Finding], int]:
    names = run_git(
        root, "-c", "core.quotepath=false", "diff", "--cached", "--name-only",
        "--diff-filter=ACMR", "-z",
    )
    findings: list[Finding] = []
    scanned = 0
    for raw_name in names.split(b"\0"):
        if not raw_name:
            continue
        name = raw_name.decode("utf-8", errors="replace")
        relative = Path(name)
        if is_sensitive_env_path(relative):
            findings.append(
                Finding("staged", name, 1, 1, "sensitive_env_file", "<sensitive-env-file>")
            )
            continue
        if not is_text_candidate(relative):
            continue
        data = run_git(root, "show", f":{name}")
        text = decode_text(data)
        if text is None:
            continue
        scanned += 1
        findings.extend(scan_text(text, scope="staged", path=name, patterns=patterns))
    return findings, scanned


def _history_path_allowed(path: Path) -> bool:
    if any(part in EXCLUDED_DIRS or part in BUILD_DIRS for part in path.parts[:-1]):
        return False
    return is_sensitive_env_path(path) or is_text_candidate(path)


def scan_history(
    root: Path, patterns: Sequence[SecretPattern]
) -> tuple[list[Finding], int]:
    # Scan user-facing Git history, excluding editor/agent checkpoint refs that
    # may contain transient test fixtures but can never be pushed normally.
    objects = run_git(
        root,
        "-c",
        "core.quotepath=false",
        "rev-list",
        "--objects",
        "--branches",
        "--tags",
        "--remotes",
    )
    findings: list[Finding] = []
    scanned = 0
    seen: set[str] = set()
    for raw_line in objects.splitlines():
        raw_oid, separator, raw_path = raw_line.partition(b" ")
        if not separator or not raw_path:
            continue
        oid = raw_oid.decode("ascii", errors="ignore")
        if not oid or oid in seen:
            continue
        seen.add(oid)
        name = raw_path.decode("utf-8", errors="replace")
        relative = Path(name)
        if not _history_path_allowed(relative):
            continue
        revision = f"blob:{oid[:12]}"
        if is_sensitive_env_path(relative):
            findings.append(
                Finding(
                    "history", name, 1, 1, "sensitive_env_file",
                    "<sensitive-env-file>", revision,
                )
            )
            continue
        try:
            data = run_git(root, "cat-file", "blob", oid)
        except GitScanError:
            # A suffix-shaped tree/submodule is not a text blob.
            continue
        text = decode_text(data)
        if text is None:
            continue
        scanned += 1
        findings.extend(
            scan_text(
                text, scope="history", path=name, patterns=patterns, revision=revision
            )
        )
    return findings, scanned


def redact_text(value: str, patterns: Sequence[SecretPattern]) -> str:
    # Paths can legally place a credential next to ``-`` or ``_``. Those
    # characters are also valid inside several token formats, so the stricter
    # standalone matchers intentionally do not catch every filename context.
    # Apply path-safe prefix redaction first; findings still retain their more
    # specific classification and no candidate value is printed.
    redacted = re.sub(
        r"sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{16,}",
        "sk-***",
        value,
        flags=re.IGNORECASE,
    )
    redacted = re.sub(
        r"(?:pcsk_|sb_secret_)[A-Za-z0-9_-]{16,}",
        "secret-***",
        redacted,
        flags=re.IGNORECASE,
    )
    for pattern in patterns:
        redacted = pattern.regex.sub(pattern.masked, redacted)
    return redacted


def unique_findings(findings: Iterable[Finding]) -> list[Finding]:
    return sorted(
        set(findings),
        key=lambda finding: (
            finding.scope, finding.path, finding.revision or "", finding.line,
            finding.column, finding.kind,
        ),
    )


def render_finding(finding: Finding, patterns: Sequence[SecretPattern]) -> str:
    safe_path = redact_text(finding.path, patterns)
    revision = f"@{finding.revision}" if finding.revision else ""
    return (
        f"{finding.scope}{revision}: {safe_path}:{finding.line}:{finding.column} "
        f"[{finding.kind}] {finding.masked}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument(
        "--include-build", action="store_true",
        help="Also scan generated build directories such as frontend/.next.",
    )
    parser.add_argument(
        "--staged", action="store_true",
        help="Also scan the exact blobs currently staged in Git.",
    )
    parser.add_argument(
        "--history", action="store_true",
        help="Also scan text blobs reachable from Git history (potentially slow).",
    )
    parser.add_argument(
        "--compare-local-env", action="store_true",
        help="Explicitly compare local .env secret values without printing them.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    patterns: tuple[SecretPattern, ...] = STATIC_PATTERNS
    if args.compare_local_env:
        patterns += configured_secret_patterns(root)

    findings, counts = scan_worktree(root, patterns, include_build=args.include_build)
    try:
        if args.staged:
            staged_findings, staged_count = scan_staged(root, patterns)
            findings.extend(staged_findings)
            counts["staged"] = staged_count
        if args.history:
            history_findings, history_count = scan_history(root, patterns)
            findings.extend(history_findings)
            counts["history"] = history_count
    except GitScanError as exc:
        print(f"Secret scan error: {exc}")
        return 2

    findings = unique_findings(findings)
    scopes = ", ".join(f"{scope}={count}" for scope, count in counts.items())
    print(f"Scanned text files/blobs ({scopes}); potential credential locations: {len(findings)}")
    for finding in findings:
        print(render_finding(finding, patterns))
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
