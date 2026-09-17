from __future__ import annotations

import os
import re
import sqlite3
import tempfile
import wave
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from pydantic import ValidationError

from .schemas import GeneratedLearningContent

CACHE_KEY_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class LearningCacheRecord:
    cache_key: str
    artifact_id: str
    input_hash: str
    prompt_version: str
    schema_version: str
    model: str
    locale: str
    content: GeneratedLearningContent


class SQLiteLearningContentCache:
    """Durable validated-response cache; it never stores prompts or API keys."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS generated_learning_content (
                    cache_key TEXT PRIMARY KEY,
                    artifact_id TEXT NOT NULL,
                    input_hash TEXT NOT NULL,
                    prompt_version TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    model TEXT NOT NULL,
                    locale TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    CHECK (length(cache_key) = 64),
                    CHECK (length(input_hash) = 64)
                );
                CREATE INDEX IF NOT EXISTS generated_learning_artifact_idx
                    ON generated_learning_content(artifact_id, created_at DESC);
                """
            )

    def get(self, cache_key: str) -> LearningCacheRecord | None:
        _require_cache_key(cache_key)
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT * FROM generated_learning_content WHERE cache_key = ?",
                    (cache_key,),
                ).fetchone()
        except sqlite3.DatabaseError:
            # Cache failure must not take canonical artifact content offline.
            return None
        if row is None:
            return None
        try:
            content = GeneratedLearningContent.model_validate_json(row["payload_json"])
        except (ValidationError, ValueError, TypeError):
            return None
        return LearningCacheRecord(
            cache_key=row["cache_key"],
            artifact_id=row["artifact_id"],
            input_hash=row["input_hash"],
            prompt_version=row["prompt_version"],
            schema_version=row["schema_version"],
            model=row["model"],
            locale=row["locale"],
            content=content,
        )

    def put(self, record: LearningCacheRecord) -> None:
        _require_cache_key(record.cache_key)
        _require_cache_key(record.input_hash)
        payload = record.content.model_dump_json()
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO generated_learning_content (
                        cache_key, artifact_id, input_hash, prompt_version,
                        schema_version, model, locale, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(cache_key) DO UPDATE SET
                        artifact_id = excluded.artifact_id,
                        input_hash = excluded.input_hash,
                        prompt_version = excluded.prompt_version,
                        schema_version = excluded.schema_version,
                        model = excluded.model,
                        locale = excluded.locale,
                        payload_json = excluded.payload_json,
                        created_at = CURRENT_TIMESTAMP
                    """,
                    (
                        record.cache_key,
                        record.artifact_id,
                        record.input_hash,
                        record.prompt_version,
                        record.schema_version,
                        record.model,
                        record.locale,
                        payload,
                    ),
                )
        except sqlite3.DatabaseError:
            # A generated response remains usable even if optional caching is
            # temporarily unavailable.
            return


class AudioFileCache:
    """Content-addressed WAV cache with confined, atomic filesystem writes."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def get_path(self, cache_key: str) -> Path | None:
        target = self._target(cache_key)
        if not target.is_file():
            return None
        try:
            with wave.open(str(target), "rb") as reader:
                _validate_wav_reader(reader)
        except (OSError, EOFError, ValueError, wave.Error):
            return None
        return target

    def put(self, cache_key: str, audio: bytes) -> Path:
        _validate_wav(audio)
        target = self._target(cache_key)
        if target.is_file():
            return target
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=f".{cache_key}.",
                suffix=".tmp",
                dir=self.root,
                delete=False,
            ) as temporary:
                temporary_name = temporary.name
                temporary.write(audio)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_name, target)
            temporary_name = None
            return target
        finally:
            if temporary_name is not None:
                try:
                    Path(temporary_name).unlink(missing_ok=True)
                except OSError:
                    pass

    def _target(self, cache_key: str) -> Path:
        _require_cache_key(cache_key)
        target = (self.root / f"{cache_key}.wav").resolve()
        if not target.is_relative_to(self.root):
            raise ValueError("Audio cache path escapes its configured root")
        return target


def _require_cache_key(value: str) -> str:
    if not CACHE_KEY_PATTERN.fullmatch(value):
        raise ValueError("Cache key must be a lowercase SHA-256 digest")
    return value


def _validate_wav(audio: bytes) -> None:
    if len(audio) < 44 or not audio.startswith(b"RIFF") or audio[8:12] != b"WAVE":
        raise ValueError("Audio provider did not return a WAV file")
    with wave.open(BytesIO(audio), "rb") as reader:
        _validate_wav_reader(reader)


def _validate_wav_reader(reader: wave.Wave_read) -> None:
    if reader.getnchannels() < 1 or reader.getsampwidth() < 1 or reader.getframerate() < 1:
        raise ValueError("WAV parameters are invalid")
    if reader.getnframes() < 1:
        raise ValueError("WAV contains no audio frames")
