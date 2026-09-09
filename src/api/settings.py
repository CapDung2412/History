from __future__ import annotations

import math
import os
from dataclasses import dataclass

from dotenv import load_dotenv

from src.config import PROJECT_ROOT


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc


@dataclass(frozen=True, slots=True)
class APISettings:
    """Runtime and recognition policy.

    Defaults are deliberately conservative starting points. Quality and
    confidence thresholds must be calibrated using real phone photographs.
    """

    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: tuple[str, ...] = ("http://localhost:3000", "http://127.0.0.1:3000")

    max_upload_bytes: int = 12 * 1024 * 1024
    multipart_overhead_bytes: int = 64 * 1024
    max_json_body_bytes: int = 8 * 1024
    max_concurrent_recognitions: int = 2
    request_body_timeout_seconds: float = 30.0
    max_image_pixels: int = 25_000_000
    min_image_width: int = 320
    min_image_height: int = 320
    dark_mean_max: float = 45.0
    dark_p75_max: float = 70.0
    bright_mean_min: float = 225.0
    bright_p25_min: float = 210.0
    blur_laplacian_variance_min: float = 80.0
    glare_luminance_min: float = 245.0
    glare_chroma_max: float = 18.0
    glare_ratio_max: float = 0.18

    confidence_accept: float = 0.72
    confidence_candidate: float = 0.55
    confidence_margin: float = 0.08
    candidate_count: int = 3
    pinecone_overfetch: int = 50

    request_context_ttl_seconds: int = 60 * 60
    request_context_max_entries: int = 10_000
    recognition_rate_limit_per_minute: int = 30
    feedback_rate_limit_per_minute: int = 120
    rate_limit_max_clients: int = 10_000

    @classmethod
    def load(cls) -> "APISettings":
        load_dotenv(PROJECT_ROOT / ".env")
        origins = tuple(
            origin.strip().rstrip("/")
            for origin in os.getenv(
                "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
            ).split(",")
            if origin.strip()
        )
        settings = cls(
            host=os.getenv("API_HOST", "127.0.0.1"),
            port=_env_int("API_PORT", 8000),
            cors_origins=origins,
            max_upload_bytes=_env_int("MAX_UPLOAD_MB", 12) * 1024 * 1024,
            multipart_overhead_bytes=_env_int("MULTIPART_OVERHEAD_BYTES", 64 * 1024),
            max_json_body_bytes=_env_int("MAX_JSON_BODY_BYTES", 8 * 1024),
            max_concurrent_recognitions=_env_int("MAX_CONCURRENT_RECOGNITIONS", 2),
            request_body_timeout_seconds=_env_float("REQUEST_BODY_TIMEOUT_SECONDS", 30.0),
            max_image_pixels=_env_int("MAX_IMAGE_PIXELS", 25_000_000),
            min_image_width=_env_int("QUALITY_MIN_WIDTH", 320),
            min_image_height=_env_int("QUALITY_MIN_HEIGHT", 320),
            dark_mean_max=_env_float("QUALITY_DARK_MEAN_MAX", 45.0),
            dark_p75_max=_env_float("QUALITY_DARK_P75_MAX", 70.0),
            bright_mean_min=_env_float("QUALITY_BRIGHT_MEAN_MIN", 225.0),
            bright_p25_min=_env_float("QUALITY_BRIGHT_P25_MIN", 210.0),
            blur_laplacian_variance_min=_env_float("QUALITY_BLUR_LAPLACIAN_MIN", 80.0),
            glare_luminance_min=_env_float("QUALITY_GLARE_LUMINANCE_MIN", 245.0),
            glare_chroma_max=_env_float("QUALITY_GLARE_CHROMA_MAX", 18.0),
            glare_ratio_max=_env_float("QUALITY_GLARE_RATIO_MAX", 0.18),
            confidence_accept=_env_float("CONFIDENCE_ACCEPT", 0.72),
            confidence_candidate=_env_float("CONFIDENCE_CANDIDATE", 0.55),
            confidence_margin=_env_float("CONFIDENCE_MARGIN", 0.08),
            candidate_count=_env_int("CANDIDATE_COUNT", 3),
            pinecone_overfetch=_env_int("PINECONE_QUERY_OVERFETCH", 50),
            request_context_ttl_seconds=_env_int("REQUEST_CONTEXT_TTL_SECONDS", 3600),
            request_context_max_entries=_env_int("REQUEST_CONTEXT_MAX_ENTRIES", 10_000),
            recognition_rate_limit_per_minute=_env_int("RECOGNITION_RATE_LIMIT_PER_MINUTE", 30),
            feedback_rate_limit_per_minute=_env_int("FEEDBACK_RATE_LIMIT_PER_MINUTE", 120),
            rate_limit_max_clients=_env_int("RATE_LIMIT_MAX_CLIENTS", 10_000),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if not -1.0 <= self.confidence_candidate <= self.confidence_accept <= 1.0:
            raise ValueError("Confidence thresholds must satisfy -1 <= candidate <= accept <= 1")
        if not 0.0 <= self.confidence_margin <= 2.0:
            raise ValueError("CONFIDENCE_MARGIN must be between 0 and 2")
        if self.candidate_count < 1 or self.pinecone_overfetch < self.candidate_count:
            raise ValueError("PINECONE_QUERY_OVERFETCH must be >= CANDIDATE_COUNT >= 1")
        if self.max_upload_bytes < 1 or self.max_image_pixels < 1:
            raise ValueError("Upload limits must be positive")
        for name in (
            "multipart_overhead_bytes", "max_json_body_bytes", "max_concurrent_recognitions",
            "request_body_timeout_seconds", "request_context_ttl_seconds", "request_context_max_entries",
            "recognition_rate_limit_per_minute", "feedback_rate_limit_per_minute", "rate_limit_max_clients",
            "min_image_width", "min_image_height",
        ):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be positive and finite")
        if not 1 <= self.port <= 65535:
            raise ValueError("API_PORT must be between 1 and 65535")
        for name in ("dark_mean_max", "dark_p75_max", "bright_mean_min", "bright_p25_min", "glare_luminance_min", "glare_chroma_max"):
            if not 0 <= getattr(self, name) <= 255:
                raise ValueError(f"{name} must be between 0 and 255")
        if not 0 <= self.glare_ratio_max <= 1:
            raise ValueError("QUALITY_GLARE_RATIO_MAX must be between 0 and 1")
        if not math.isfinite(self.blur_laplacian_variance_min) or self.blur_laplacian_variance_min < 0:
            raise ValueError("QUALITY_BLUR_LAPLACIAN_MIN must be finite and non-negative")
