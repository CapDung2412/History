from __future__ import annotations

import io
from dataclasses import replace

import numpy as np
import pytest
from PIL import Image

from src.api.quality import ImageValidationError, assess_quality, read_image
from src.api.settings import APISettings


def _encoded(image: Image.Image, image_format: str = "PNG", *, exif=None) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format=image_format, exif=exif)
    return buffer.getvalue()


def test_quality_detects_dark_image() -> None:
    result = assess_quality(Image.new("RGB", (640, 480), (10, 10, 10)), APISettings())
    assert "too_dark" in {issue.code for issue in result.issues}


def test_quality_detects_bright_image() -> None:
    result = assess_quality(Image.new("RGB", (640, 480), "white"), APISettings())
    codes = {issue.code for issue in result.issues}
    assert "too_bright" in codes
    assert "strong_glare" in codes


def test_quality_detects_blur_without_claiming_object_is_too_far() -> None:
    result = assess_quality(Image.new("RGB", (640, 480), (120, 120, 120)), APISettings())
    codes = {issue.code for issue in result.issues}
    assert "blurry" in codes
    assert "too_far" not in codes


def test_quality_detects_large_neutral_glare_area() -> None:
    values = np.full((480, 640, 3), (70, 100, 140), dtype=np.uint8)
    values[:, :200] = 252
    result = assess_quality(Image.fromarray(values), APISettings())
    assert "strong_glare" in {issue.code for issue in result.issues}


def test_bright_background_is_warning_not_a_reflection_diagnosis() -> None:
    values = np.random.default_rng(10).integers(45, 210, size=(480, 640, 3), dtype=np.uint8)
    values[:, :150] = 252
    result = assess_quality(Image.fromarray(values), APISettings())
    assert result.passed
    glare = next(issue for issue in result.issues if issue.code == "strong_glare")
    assert glare.severity == "warning"
    assert "có thể" in glare.message


def test_read_image_rejects_size_format_and_pixel_bomb() -> None:
    with pytest.raises(ImageValidationError, match="giới hạn") as oversized:
        read_image(b"x" * 11, replace(APISettings(), max_upload_bytes=10))
    assert oversized.value.status_code == 413

    bmp = _encoded(Image.new("RGB", (10, 10)), "BMP")
    with pytest.raises(ImageValidationError) as unsupported:
        read_image(bmp, APISettings())
    assert unsupported.value.code == "unsupported_format"

    png = _encoded(Image.new("RGB", (11, 10)))
    with pytest.raises(ImageValidationError) as bomb:
        read_image(png, replace(APISettings(), max_image_pixels=100))
    assert bomb.value.code == "too_many_pixels"


def test_read_image_applies_exif_orientation_and_discards_metadata() -> None:
    source = Image.new("RGB", (40, 80), "navy")
    exif = Image.Exif()
    exif[274] = 6
    exif[270] = "Private photograph description"
    exif[315] = "Private photographer name"
    decoded = read_image(_encoded(source, "JPEG", exif=exif), APISettings())
    assert decoded.size == (80, 40)
    assert len(decoded.getexif()) == 0
    assert decoded.info == {}
