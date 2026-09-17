from __future__ import annotations

import json
import unicodedata
from pathlib import Path

from src.config import PROJECT_ROOT
from src.dataset.catalog import load_document
from src.text import clean_speech_text, contains_mojibake


GOLDEN_TEXT = (
    "Tác phẩm điêu khắc “Bà mẹ” của nhà điêu khắc Nguyễn Hoàng Huy "
    "được tạo hình từ những mảnh bom còn sót lại sau chiến tranh"
)


def test_json_boundary_normalizes_decomposed_vietnamese_to_nfc(tmp_path: Path) -> None:
    decomposed = unicodedata.normalize("NFD", "ă â đ ê ô ơ ư á à ả ã ạ ấ ầ ẩ ẫ ậ")
    path = tmp_path / "unicode.json"
    path.write_text(
        json.dumps({"text": decomposed}, ensure_ascii=False),
        encoding="utf-8",
    )

    document = load_document(path)

    assert document["text"] == unicodedata.normalize("NFC", decomposed)
    assert unicodedata.is_normalized("NFC", document["text"])


def test_golden_artifact_text_is_valid_utf8_nfc_without_mojibake() -> None:
    matches = list(
        (PROJECT_ROOT / "JSON").rglob("tuong-ba-me-bang-manh-bom.json")
    )
    assert len(matches) == 1
    raw = matches[0].read_text(encoding="utf-8")
    document = load_document(matches[0])
    description = document["locations"][0]["historical_info"]["description"]

    assert unicodedata.is_normalized("NFC", raw)
    assert not contains_mojibake(raw)
    assert GOLDEN_TEXT in description


def test_speech_text_is_plain_nfc_vietnamese() -> None:
    dirty = unicodedata.normalize("NFD", "Tượng bà mẹ bằng mảnh bom")
    cleaned = clean_speech_text(
        f"<p>{dirty}</p> https://example.invalid/source"
    )

    assert cleaned == "Tượng bà mẹ bằng mảnh bom"
    assert unicodedata.is_normalized("NFC", cleaned)
