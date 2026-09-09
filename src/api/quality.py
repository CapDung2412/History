from __future__ import annotations

import io
import warnings
from dataclasses import dataclass
from typing import Literal

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from .settings import APISettings


class ImageValidationError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class QualityIssue:
    code: str
    message: str
    guidance: str
    severity: Literal["warning", "error"] = "error"


@dataclass(frozen=True, slots=True)
class QualityResult:
    width: int
    height: int
    pixel_count: int
    brightness_mean: float
    brightness_p25: float
    brightness_p75: float
    laplacian_variance: float
    glare_ratio: float
    issues: tuple[QualityIssue, ...]

    @property
    def passed(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)


def read_image(data: bytes, settings: APISettings) -> Image.Image:
    """Decode a supported image fully in memory without retaining EXIF metadata."""

    if not data:
        raise ImageValidationError("empty_file", "Tệp ảnh đang trống.")
    if len(data) > settings.max_upload_bytes:
        limit_mb = settings.max_upload_bytes / (1024 * 1024)
        raise ImageValidationError(
            "file_too_large", f"Ảnh vượt quá giới hạn {limit_mb:g} MB.", status_code=413
        )

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in {"JPEG", "PNG", "WEBP"}:
                    raise ImageValidationError(
                        "unsupported_format", "Chỉ hỗ trợ ảnh JPG, PNG hoặc WEBP."
                    )
                width, height = source.size
                if width * height > settings.max_image_pixels:
                    raise ImageValidationError(
                        "too_many_pixels", "Ảnh có độ phân giải quá lớn.", status_code=413
                    )
                source.load()
                # EXIF orientation is applied, then EXIF is discarded by producing a
                # fresh RGB image. No uploaded bytes are persisted.
                with ImageOps.exif_transpose(source) as oriented:
                    clean = oriented.convert("RGB")
                    # Pillow convert/copy preserve .info, including GPS EXIF.
                    # A new pixel-only image removes every metadata channel.
                    output = Image.new("RGB", clean.size)
                    output.paste(clean)
                    clean.close()
                    return output
    except ImageValidationError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ImageValidationError(
            "too_many_pixels", "Ảnh có độ phân giải quá lớn.", status_code=413
        ) from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImageValidationError(
            "invalid_image", "Tệp không phải là ảnh hợp lệ hoặc đã bị hỏng."
        ) from exc


def _laplacian_variance(gray: np.ndarray) -> float:
    if min(gray.shape) < 3:
        return 0.0
    center = gray[1:-1, 1:-1]
    laplacian = (
        gray[:-2, 1:-1]
        + gray[2:, 1:-1]
        + gray[1:-1, :-2]
        + gray[1:-1, 2:]
        - 4.0 * center
    )
    return float(np.var(laplacian, dtype=np.float64))


def assess_quality(image: Image.Image, settings: APISettings) -> QualityResult:
    width, height = image.size
    # Bound temporary arrays for predictable memory/latency while preserving
    # original dimensions in the response.
    analysis_image = image.copy()
    analysis_image.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
    rgb = np.asarray(analysis_image, dtype=np.float32)
    # ITU-R BT.601 luma is sufficient for explainable exposure heuristics.
    luma = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
    brightness_mean = float(np.mean(luma))
    brightness_p25, brightness_p75 = (float(value) for value in np.percentile(luma, [25, 75]))
    laplacian_variance = _laplacian_variance(luma)

    channel_range = np.max(rgb, axis=2) - np.min(rgb, axis=2)
    near_white_neutral = (luma >= settings.glare_luminance_min) & (
        channel_range <= settings.glare_chroma_max
    )
    glare_ratio = float(np.mean(near_white_neutral))

    issues: list[QualityIssue] = []
    if width < settings.min_image_width or height < settings.min_image_height:
        issues.append(
            QualityIssue(
                "resolution_too_small",
                "Ảnh có độ phân giải quá thấp.",
                "Em hãy tiến lại gần hơn và đưa toàn bộ hiện vật vào trong khung.",
            )
        )
    if brightness_mean < settings.dark_mean_max and brightness_p75 < settings.dark_p75_max:
        issues.append(
            QualityIssue(
                "too_dark",
                "Ảnh đang quá tối.",
                "Em hãy tiến gần nguồn sáng hơn hoặc tăng độ sáng rồi chụp lại.",
            )
        )
    if brightness_mean > settings.bright_mean_min and brightness_p25 > settings.bright_p25_min:
        issues.append(
            QualityIssue(
                "too_bright",
                "Ảnh đang quá sáng.",
                "Em hãy giảm độ sáng hoặc tránh hướng đèn chiếu thẳng vào hiện vật.",
            )
        )
    if laplacian_variance < settings.blur_laplacian_variance_min:
        issues.append(
            QualityIssue(
                "blurry",
                "Ảnh có thể bị mờ.",
                "Em hãy giữ chắc điện thoại, chạm lấy nét và chụp lại.",
            )
        )
    if glare_ratio > settings.glare_ratio_max:
        issues.append(
            QualityIssue(
                "strong_glare",
                "Ảnh có vùng sáng trắng lớn, có thể do lóa hoặc nền sáng.",
                "Em hãy kiểm tra chi tiết hiện vật. Nếu bị lóa, dịch điện thoại sang một bên rồi chụp lại.",
                severity="warning",
            )
        )

    return QualityResult(
        width=width,
        height=height,
        pixel_count=width * height,
        brightness_mean=brightness_mean,
        brightness_p25=brightness_p25,
        brightness_p75=brightness_p75,
        laplacian_variance=laplacian_variance,
        glare_ratio=glare_ratio,
        issues=tuple(issues),
    )
