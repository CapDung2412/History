from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

from .schemas import RelatedVideo


@dataclass(frozen=True, slots=True)
class CuratedVideoEntry:
    """A manually reviewed recommendation, distinct from provider web evidence."""

    ref: str
    title: str
    url: str
    channel_name: str
    trust_level: Literal["official", "reputable_institution"]
    trust_reason: str
    scope: Literal[
        "exact_artifact",
        "related_event",
        "site_or_museum",
        "broader_context",
    ]
    relevance: str
    reviewed_at: str
    provenance: Literal["editorial_curated"] = "editorial_curated"

    def as_related_video(self) -> RelatedVideo:
        return RelatedVideo(
            title=self.title,
            url=self.url,
            channel_name=self.channel_name,
            trust_level=self.trust_level,
            trust_reason=self.trust_reason,
            scope=self.scope,
            relevance=self.relevance,
            evidence_refs=[self.ref],
        )


_MUSEUM_SITE_VIDEOS: tuple[CuratedVideoEntry, ...] = (
    CuratedVideoEntry(
        ref="curated.video.1",
        title=(
            "Bảo tàng Chứng tích Chiến tranh: Nơi gìn giữ khát vọng hòa bình"
        ),
        url="https://www.youtube.com/watch?v=-UFZ-v4VIiI",
        channel_name="HTV Tin Tức",
        trust_level="official",
        trust_reason=(
            "HTV Tin Tức là kênh tin tức chính thức của Đài Truyền hình "
            "Thành phố Hồ Chí Minh."
        ),
        scope="site_or_museum",
        relevance=(
            "Video giới thiệu Bảo tàng Chứng tích Chiến tranh và các không gian "
            "trưng bày về hậu quả chiến tranh; đây là bối cảnh nơi lưu giữ hiện vật, "
            "không phải video riêng về tượng bà mẹ bằng mảnh bom."
        ),
        reviewed_at="2026-09-16",
    ),
    CuratedVideoEntry(
        ref="curated.video.2",
        title=(
            "Bảo tàng Chứng tích Chiến tranh - Điểm đến lịch sử vì hòa bình"
        ),
        url="https://www.youtube.com/watch?v=YAedbui1Juc",
        channel_name="HTV Tin Tức",
        trust_level="official",
        trust_reason=(
            "HTV Tin Tức là kênh tin tức chính thức của Đài Truyền hình "
            "Thành phố Hồ Chí Minh."
        ),
        scope="site_or_museum",
        relevance=(
            "Video trình bày vai trò và hoạt động của Bảo tàng Chứng tích Chiến "
            "tranh; liên kết cung cấp bối cảnh bảo tàng, không mô tả trực tiếp "
            "tượng bà mẹ bằng mảnh bom."
        ),
        reviewed_at="2026-09-16",
    ),
)

_EXPLOSIVE_REMNANTS_VIDEO = CuratedVideoEntry(
    ref="curated.video.3",
    title=(
        "Bộ đội công binh và cuộc chiến rà phá bom mìn sau chiến tranh | VTV24"
    ),
    url="https://www.youtube.com/watch?v=mhlAVm92uYY",
    channel_name="VTV24",
    trust_level="reputable_institution",
    trust_reason=(
        "VTV24 là đơn vị tin tức thuộc Đài Truyền hình Việt Nam, có quy trình "
        "biên tập báo chí."
    ),
    scope="broader_context",
    relevance=(
        "Video nói về công việc rà phá bom mìn và di vật nổ còn lại sau chiến "
        "tranh, cung cấp bối cảnh rộng về hậu quả vật chất của chiến tranh; "
        "video không trình bày trực tiếp về bức tượng."
    ),
    reviewed_at="2026-09-16",
)


def curated_videos_for(
    artifact_id: str,
    *,
    location_address: str | None = None,
    description: str | None = None,
) -> tuple[CuratedVideoEntry, ...]:
    """Select reviewed videos by exact artifact or narrowly defined context."""

    normalized_address = _search_text(location_address)
    normalized_description = _search_text(description)
    is_target = artifact_id == "tuong-ba-me-bang-manh-bom"
    is_war_remnants_museum = (
        is_target
        or "28 vo van tan" in normalized_address
        or "bao tang chung tich chien tranh" in normalized_description
    )
    concerns_explosive_remnants = is_target or bool(
        re.search(r"\b(?:bom|min|bom dan|manh bom)\b", normalized_description)
    )
    selected: list[CuratedVideoEntry] = []
    if is_war_remnants_museum:
        selected.extend(_MUSEUM_SITE_VIDEOS)
    if concerns_explosive_remnants:
        selected.append(_EXPLOSIVE_REMNANTS_VIDEO)
    return tuple(selected[:3])


def _search_text(value: str | None) -> str:
    decomposed = unicodedata.normalize("NFD", value or "")
    without_marks = "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    )
    return " ".join(without_marks.casefold().replace("đ", "d").split())
