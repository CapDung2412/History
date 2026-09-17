from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.check_secrets import (
    STATIC_PATTERNS,
    main,
    render_finding,
    scan_history,
    scan_staged,
    scan_text,
    scan_worktree,
)


def _keys() -> tuple[str, str, str]:
    return (
        "sk-proj-" + "A1b2" * 10,
        "sk-svcacct-" + "C3d4" * 10,
        "sk-" + "E5f6" * 10,
    )


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def test_openai_variants_are_classified_and_rendered_redacted() -> None:
    project, service, legacy = _keys()
    text = f'one="{project}"\ntwo="{service}"\nthree="{legacy}"\n'

    findings = scan_text(
        text,
        scope="source",
        path=f"unsafe-{project}.txt",
        patterns=STATIC_PATTERNS,
    )

    assert {finding.kind for finding in findings} == {
        "openai_project_key",
        "openai_service_account_key",
        "openai_legacy_key",
    }
    rendered = "\n".join(render_finding(item, STATIC_PATTERNS) for item in findings)
    assert project not in rendered
    assert service not in rendered
    assert legacy not in rendered
    assert "sk-proj-***" in rendered


def test_assignment_detects_short_key_but_ordinary_next_filename_is_safe() -> None:
    assignment = scan_text(
        "CHATGPT_API_KEY='" + "sk-short" + "DevelopmentKey123456'",
        scope="source",
        path="settings.py",
        patterns=STATIC_PATTERNS,
    )
    false_positive = scan_text(
        "after-task-async-storage-external.js",
        scope="build",
        path="manifest.json",
        patterns=STATIC_PATTERNS,
    )

    assert [finding.kind for finding in assignment] == ["openai_api_key_assignment"]
    assert false_positive == []


def test_build_is_opt_in_and_default_does_not_scan_dotenv(tmp_path: Path) -> None:
    project, _, _ = _keys()
    (tmp_path / ".env").write_text(f"OPENAI_API_KEY={project}", encoding="utf-8")
    build = tmp_path / "frontend" / ".next"
    build.mkdir(parents=True)
    (build / "chunk.js").write_text(project, encoding="utf-8")
    (tmp_path / "safe.py").write_text("print('safe')", encoding="utf-8")

    default_findings, default_counts = scan_worktree(tmp_path, STATIC_PATTERNS)
    build_findings, build_counts = scan_worktree(
        tmp_path, STATIC_PATTERNS, include_build=True
    )

    assert default_findings == []
    assert default_counts == {"source": 1, "build": 0}
    assert len(build_findings) == 1
    assert build_findings[0].scope == "build"
    assert build_counts == {"source": 1, "build": 1}


def test_staged_and_history_scans_never_emit_secret_value(
    tmp_path: Path, capsys
) -> None:
    project, _, _ = _keys()
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.name", "Secret Scanner Test")
    _git(tmp_path, "config", "user.email", "scanner@example.invalid")
    tracked = tmp_path / "config.txt"
    tracked.write_text(project, encoding="utf-8")
    _git(tmp_path, "add", "config.txt")

    staged, staged_count = scan_staged(tmp_path, STATIC_PATTERNS)
    assert staged_count == 1
    assert [finding.kind for finding in staged] == ["openai_project_key"]

    assert main(["--root", str(tmp_path), "--staged"]) == 1
    output = capsys.readouterr().out
    assert project not in output
    assert "staged:" in output
    assert "sk-proj-***" in output

    _git(tmp_path, "commit", "-m", "fixture")
    tracked.write_text("safe now", encoding="utf-8")
    _git(tmp_path, "add", "config.txt")
    _git(tmp_path, "commit", "-m", "remove fixture")

    history, history_count = scan_history(tmp_path, STATIC_PATTERNS)
    assert history_count >= 2
    assert any(finding.kind == "openai_project_key" for finding in history)
    assert all(project not in render_finding(item, STATIC_PATTERNS) for item in history)


def test_staged_env_is_reported_without_reading_blob(tmp_path: Path) -> None:
    _git(tmp_path, "init")
    env_path = tmp_path / ".env.production"
    env_path.write_bytes(b"\x00\x01\x02")
    _git(tmp_path, "add", ".env.production")

    findings, scanned = scan_staged(tmp_path, STATIC_PATTERNS)

    assert scanned == 0
    assert len(findings) == 1
    assert findings[0].kind == "sensitive_env_file"
    assert findings[0].masked == "<sensitive-env-file>"
