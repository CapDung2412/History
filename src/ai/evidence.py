from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, replace
from typing import Any, Iterable, Literal
from urllib.parse import parse_qs, urlsplit

from src.repositories.content import category_label
from src.repositories.models import ArtifactRecord

from .curated_videos import CuratedVideoEntry
from .schemas import (
    DeepSection,
    EvidenceClaim,
    EvidenceReference,
    GeneratedLearningContent,
    Keyword,
    MindMap,
    MindMapBranch,
    MindMapNode,
    NarrationText,
    RelatedVideo,
    SelfCheck,
    SelfCheckOption,
    StoryBlock,
    StoryContent,
    TimelineEntry,
    WebEvidence,
)

SourceStatus = Literal["missing", "available_unverified", "verified"]
DataStatus = Literal["missing", "needs_verification", "sufficient"]
YEAR_TOKEN = re.compile(r"(?<!\d)(?:1\d{3}|20\d{2})(?!\d)")
URL_TOKEN = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
WORD_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)
MEASUREMENT_TOKEN = re.compile(
    r"(?<!\w)\d+(?:[.,]\d+)?\s*(?:mm|cm|m|g|kg)(?!\w)", re.IGNORECASE
)
URL_TRAILING_DELIMITERS = frozenset(".,;:!?)]}'\"”’")
DISCOURAGED_UI_TERM = re.compile(r"\bhồ\s+sơ\b", re.IGNORECASE)
AUDIENCE_NOUN_PATTERN = (
    r"(?:học\s+sinh|người\s+học|người\s+xem|người\s+đọc|"
    r"khách\s+tham\s+quan|em|bạn|chúng\s+ta)"
)
AUDIENCE_DIRECTED_FRAMING = re.compile(
    r"\b(?:người\s+học|người\s+xem|người\s+đọc|khách\s+tham\s+quan)\b"
    r"|\b(?:giúp|hỗ\s+trợ)\s+(?:cho\s+)?(?:các\s+)?"
    + AUDIENCE_NOUN_PATTERN
    + r"\b"
    r"|\b(?:đối\s+với|với|dành\s+cho)\s+(?:các\s+)?"
    + AUDIENCE_NOUN_PATTERN
    + r"\b"
    r"|\b"
    + AUDIENCE_NOUN_PATTERN
    + r"\s+(?:có\s+thể|sẽ|cần|nên|hiểu|nhận\s+ra|ghi\s+nhớ|"
    r"biết|thấy|cảm\s+nhận|liên\s+hệ)\b"
    r"|\b(?:từ\s+góc\s+độ|về\s+mặt)\s+giáo\s+dục\b"
    r"|\bkhi\s+(?:học|tìm\s+hiểu|khám\s+phá)\s+(?:về\s+)?(?:hiện\s+vật|sự\s+kiện)\b"
    r"|\b(?:bài\s+học|thông\s+điệp)\s+(?:dành\s+)?cho\s+"
    + AUDIENCE_NOUN_PATTERN
    + r"\b"
    r"|\b(?:ý\s+nghĩa|giá\s+trị|diễn\s+giải|mục\s+đích)\s+"
    r"(?:giáo\s+dục|học\s+tập|sư\s+phạm)\b"
    r"|\b(?:không\s+gian|vai\s+trò|chức\s+năng)\s+giáo\s+dục\b"
    r"|\b(?:nguồn|tư\s+liệu|công\s+cụ)\s+(?:học\s+tập|giảng\s+dạy|dạy\s+học)\b"
    r"|\bphù\s+hợp\s+(?:để|cho)\s+(?:việc\s+)?(?:dạy\s+học|giảng\s+dạy|học\s+tập)\b"
    r"|\b(?:có\s+thể\s+)?(?:được\s+)?(?:dùng|sử\s+dụng)\s+"
    r"(?:như\s+(?:một\s+)?(?:nguồn|tư\s+liệu|công\s+cụ)\s+)?(?:để|cho)\s+"
    r"(?:dạy|học|dạy\s+học|giảng\s+dạy|minh\s+họa\s+bài\s+học)\b"
    r"|\bkhi\s+(?:các\s+)?(?:người\s+học|người\s+xem|người\s+đọc|khách\s+tham\s+quan)\s+"
    r"(?:theo\s+dõi|đọc|quan\s+sát|khám\s+phá|tiếp\s+cận)\b"
    r"|\b(?:hướng|đưa|dẫn)\s+(?:các\s+)?"
    + AUDIENCE_NOUN_PATTERN
    + r"\s+(?:đến|tới)\b"
    r"|\bcầu\s+nối\b.{0,100}\b(?:với|và)\s+(?:các\s+)?"
    + AUDIENCE_NOUN_PATTERN
    + r"\b"
    r"|\b(?:trong|cho|của)\s+(?:một\s+)?bài\s+học\b"
    r"|\b(?:dạy\s+học|giảng\s+dạy)\b",
    re.IGNORECASE,
)
SECTION_META_OPENING = re.compile(
    r"^\s*(?:phần|mục|nội\s+dung)\s+này\b",
    re.IGNORECASE,
)
SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")
YOUTUBE_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
MATERIAL_DETAIL_TOKENS = frozenset(
    {
        "bạc",
        "bê tông",
        "chạm",
        "chì",
        "composite",
        "dán",
        "dệt",
        "đá",
        "đất",
        "đúc",
        "gang",
        "giấy",
        "gốm",
        "gỗ",
        "hàn",
        "hợp kim",
        "khắc",
        "kính",
        "lụa",
        "kim loại",
        "mảnh bom",
        "mạ",
        "may",
        "mây",
        "nhôm",
        "nhựa",
        "nung",
        "rèn",
        "sắt",
        "sơn",
        "sứ",
        "thép",
        "thiếc",
        "tre",
        "vải",
        "vàng",
        "xi măng",
    }
)
SUPPORT_STOPWORDS = frozenset(
    {
        "ai",
        "bị",
        "bởi",
        "các",
        "cho",
        "chưa",
        "có",
        "của",
        "cùng",
        "đã",
        "đang",
        "để",
        "đến",
        "được",
        "hay",
        "khi",
        "không",
        "là",
        "lại",
        "mà",
        "một",
        "này",
        "những",
        "ở",
        "qua",
        "sau",
        "theo",
        "thì",
        "trong",
        "trước",
        "từ",
        "và",
        "vào",
        "về",
        "với",
    }
)


class EvidenceValidationError(ValueError):
    """Generated content cannot be tied to the canonical input evidence."""


DEEP_SECTION_ORDER = {
    "overview": 0,
    "identity": 1,
    "recognition": 2,
    "material": 3,
    "context": 4,
    "activities": 5,
    "timeline": 6,
    "story": 7,
    "role": 8,
    "impact": 9,
    "highlights": 10,
    "significance": 11,
    "provenance": 12,
    "related": 13,
    "sources": 14,
}


@dataclass(frozen=True, slots=True)
class EvidenceValue:
    ref: str
    label: str
    value: str
    source_status: Literal[
        "not_applicable", "missing", "available_unverified", "verified"
    ] = "not_applicable"
    url: str | None = None
    provenance: Literal["canonical", "web_search", "editorial_curated"] = "canonical"


@dataclass(frozen=True, slots=True)
class EvidenceCatalog:
    artifact_id: str
    source_status: SourceStatus
    data_status: DataStatus
    normalized_input: dict[str, Any]
    values: dict[str, EvidenceValue]
    explicit_years: frozenset[int]
    allowed_year_tokens: frozenset[str]
    allowed_urls: frozenset[str]
    central_labels: frozenset[str]

    @property
    def input_hash(self) -> str:
        encoded = json.dumps(
            self.normalized_input,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def public_references(self) -> list[EvidenceReference]:
        return [
            EvidenceReference(
                ref=value.ref,
                label=value.label,
                value=_clip_text(value.value, 1_200),
                source_status=value.source_status,
                provenance=value.provenance,
                url=value.url,
            )
            for value in self.values.values()
        ]


def _clean_text(value: object, limit: int) -> str | None:
    if value is None:
        return None
    text = unicodedata.normalize("NFC", str(value))
    text = " ".join(text.replace("\x00", " ").split())
    if not text:
        return None
    return _clip_text(text, limit)


def _clip_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    clipped = text[: limit + 1]
    boundary = clipped.rfind(" ", 0, limit + 1)
    return (clipped[:boundary] if boundary >= max(1, limit // 2) else text[:limit]).rstrip()


def build_evidence_catalog(artifact: ArtifactRecord) -> EvidenceCatalog:
    """Create the only data payload that may be sent to a content model.

    Local file paths and Drive image URLs are deliberately excluded.  Every
    value gets a stable reference so generated claims can be checked later.
    """

    values: dict[str, EvidenceValue] = {}

    def add(
        ref: str,
        label: str,
        raw: object,
        *,
        limit: int = 1_000,
        source_status: Literal[
            "not_applicable", "missing", "available_unverified", "verified"
        ] = "not_applicable",
        url: str | None = None,
    ) -> None:
        text = _clean_text(raw, limit)
        if text is None:
            return
        values[ref] = EvidenceValue(ref, label, text, source_status, url)

    history = artifact.historical_info
    add("artifact.name", "Tên hiện vật", artifact.name, limit=300)
    add("artifact.category", "Loại hiện vật", artifact.category, limit=120)
    add(
        "artifact.category_label",
        "Tên loại hiện vật bằng tiếng Việt",
        category_label(artifact.category),
        limit=120,
    )
    add("dataset.name", "Tên bộ sưu tập hoặc bảo tàng", artifact.dataset_name, limit=300)
    add("dataset.version", "Phiên bản bộ dữ liệu", artifact.dataset_version, limit=80)
    for index, tag in enumerate(artifact.tags[:24]):
        add(f"artifact.tags[{index}]", "Từ khóa dữ liệu", tag, limit=120)
    add("history.title", "Tên tư liệu lịch sử", history.title, limit=300)
    add("history.description", "Mô tả tư liệu", history.description, limit=8_000)
    add("history.period", "Giai đoạn lịch sử", history.historical_period, limit=300)
    add("history.year", "Năm được ghi nhận", history.year, limit=20)
    add("history.event", "Sự kiện được ghi nhận", history.event, limit=500)

    location = artifact.location
    add("location.address", "Địa chỉ lưu giữ", location.address, limit=300)
    add("location.city", "Thành phố", location.city, limit=160)
    add("location.province", "Tỉnh hoặc thành phố", location.province, limit=160)
    add("location.country", "Quốc gia", location.country, limit=120)

    for image in artifact.images[:12]:
        safe_id = re.sub(r"[^A-Za-z0-9_-]", "-", image.id)[:80] or "image"
        prefix = f"image.{safe_id}"
        add(f"{prefix}.caption", "Chú thích ảnh", image.caption, limit=600)
        add(f"{prefix}.year", "Năm của ảnh", image.year, limit=20)
        add(f"{prefix}.view", "Góc nhìn ảnh", image.view, limit=160)

    source_present = bool((history.source or "").strip() or artifact.sources)
    explicitly_verified = source_present and history.source_status == "verified"
    source_status: SourceStatus = (
        "verified"
        if explicitly_verified
        else "available_unverified"
        if source_present
        else "missing"
    )
    evidence_source_status = source_status if source_present else "missing"
    if history.source:
        add(
            "history.source",
            "Nguồn được cung cấp",
            history.source,
            limit=2_000,
            source_status=evidence_source_status,
            url=_http_url(history.source),
        )
    for source in artifact.sources[:10]:
        prefix = f"source.{source.id}"
        add(
            f"{prefix}.citation",
            source.title or "Trích dẫn nguồn",
            source.citation,
            limit=2_000,
            source_status=evidence_source_status,
            url=_http_url(source.url),
        )
        add(
            f"{prefix}.title",
            "Tên nguồn",
            source.title,
            limit=500,
            source_status=evidence_source_status,
        )

    has_core = bool(
        _clean_text(artifact.name, 300)
        and _clean_text(artifact.category, 120)
        and _clean_text(history.description, 8_000)
    )
    data_status: DataStatus
    if not has_core or source_status == "missing":
        data_status = "missing"
    elif source_status == "available_unverified":
        data_status = "needs_verification"
    else:
        data_status = "sufficient"

    facts = [
        {
            "ref": evidence.ref,
            "label": evidence.label,
            "value": evidence.value,
            "source_status": evidence.source_status,
            **({"url": evidence.url} if evidence.url else {}),
        }
        for evidence in values.values()
    ]
    normalized_input = {
        "artifact_id": artifact.id,
        "data_status": data_status,
        "source_status": source_status,
        "facts": facts,
    }
    explicit_years = {
        value
        for value in [history.year, *(image.year for image in artifact.images[:12])]
        if isinstance(value, int) and not isinstance(value, bool)
    }
    allowed_year_tokens = {
        match.group(0)
        for evidence in values.values()
        for match in YEAR_TOKEN.finditer(evidence.value)
    }
    allowed_urls = {
        evidence.url for evidence in values.values() if evidence.url is not None
    }
    central_labels = {
        value
        for value in (
            _clean_text(artifact.name, 180),
            _clean_text(history.title, 180),
        )
        if value
    }
    return EvidenceCatalog(
        artifact_id=artifact.id,
        source_status=source_status,
        data_status=data_status,
        normalized_input=normalized_input,
        values=values,
        explicit_years=frozenset(explicit_years),
        allowed_year_tokens=frozenset(allowed_year_tokens),
        allowed_urls=frozenset(allowed_urls),
        central_labels=frozenset(central_labels),
    )


def _http_url(value: object) -> str | None:
    text = _clean_text(value, 2_000)
    if text and re.fullmatch(r"https?://[^\s<>]+", text, flags=re.IGNORECASE):
        return text
    return None


def validate_generated_content(
    content: GeneratedLearningContent,
    catalog: EvidenceCatalog,
) -> None:
    """Reject structurally valid output that is not grounded in input refs."""

    catalog = extend_catalog_with_web_evidence(catalog, content.web_evidence)

    claim_ids: set[str] = set()
    for claim in content.factual_claims:
        if claim.id in claim_ids:
            raise EvidenceValidationError("Duplicate factual claim id")
        claim_ids.add(claim.id)
        _validate_refs(claim.evidence_refs, catalog)
        if not _is_evidence_excerpt(claim.text, claim.evidence_refs, catalog):
            raise EvidenceValidationError(
                "Factual claim is not an excerpt of its cited evidence"
            )

    _validate_claim_ids(content.storytelling.quick.claim_ids, claim_ids)
    _validate_claim_ids(content.storytelling.one_minute.claim_ids, claim_ids)
    for section in content.deep_sections:
        _validate_claim_ids(section.claim_ids, claim_ids)
    _validate_material_sections(content, catalog)
    _validate_historical_framing(content)
    dated_years = [entry.year for entry in content.timeline if entry.year is not None]
    if dated_years != sorted(dated_years):
        raise EvidenceValidationError("Timeline entries are not chronological")
    for entry in content.timeline:
        _validate_refs(entry.evidence_refs, catalog)
        if entry.year is not None and str(entry.year) not in catalog.allowed_year_tokens:
            raise EvidenceValidationError("Timeline contains a year absent from explicit year fields")
    for keyword in content.keywords:
        _validate_refs(keyword.evidence_refs, catalog)
        if not _is_evidence_excerpt(keyword.term, keyword.evidence_refs, catalog):
            raise EvidenceValidationError("Keyword is absent from its cited evidence")
    if content.mindmap.central_label not in catalog.central_labels:
        raise EvidenceValidationError("Mindmap center must use the canonical artifact name")
    seen_mindmap_ids: set[str] = set()
    for branch in content.mindmap.branches:
        if branch.id in seen_mindmap_ids:
            raise EvidenceValidationError("Duplicate mindmap id")
        seen_mindmap_ids.add(branch.id)
        _validate_refs(branch.evidence_refs, catalog)
        for node in branch.nodes:
            if node.id in seen_mindmap_ids:
                raise EvidenceValidationError("Duplicate mindmap id")
            seen_mindmap_ids.add(node.id)
            _validate_refs(node.evidence_refs, catalog)
            if not _is_evidence_excerpt(node.label, node.evidence_refs, catalog):
                raise EvidenceValidationError(
                    "Mindmap label is absent from its cited evidence"
                )
            if _support_text(node.label) in {
                "lịch sử",
                "thông tin",
                "ý nghĩa",
                "bối cảnh",
                "sự kiện",
                "câu chuyện",
            }:
                raise EvidenceValidationError("Mindmap node label is too generic")
    _validate_related_videos(content, catalog)
    if content.self_check is not None:
        _validate_refs(content.self_check.evidence_refs, catalog)
        correct = next(
            option
            for option in content.self_check.options
            if option.id == content.self_check.correct_option_id
        )
        if not _is_evidence_excerpt(
            correct.label,
            content.self_check.evidence_refs,
            catalog,
        ):
            raise EvidenceValidationError(
                "Correct self-check option is absent from its cited evidence"
            )

    # Structured Outputs guarantees shape, not historical truth.  Block the
    # easiest high-impact additions: new dates and URLs that never appeared in
    # the canonical payload.  Semantic evidence review remains a separate
    # editorial responsibility.
    # Provider-verified web source metadata establishes its own URL/year
    # allowlist. Check generated learning prose here, not the source records
    # themselves (a publication year may legitimately occur in a source URL).
    for text in _generated_prose_strings(content):
        for year in YEAR_TOKEN.findall(text):
            if year not in catalog.allowed_year_tokens:
                raise EvidenceValidationError("Generated text contains an unsupported year")
        for url in URL_TOKEN.findall(text):
            if not _matches_allowed_url(url, catalog.allowed_urls):
                raise EvidenceValidationError("Generated text contains an unsupported URL")

    web_refs = {evidence.ref for evidence in content.web_evidence}
    if web_refs and not web_refs.issubset(_content_evidence_refs(content)):
        raise EvidenceValidationError("Web evidence must be cited by generated content")


def normalize_generated_editorial_structure(
    content: GeneratedLearningContent,
) -> GeneratedLearningContent:
    """Apply safe presentation invariants without adding historical facts.

    Model prose stays untouched. We only order existing sections and dated
    timeline entries, use the agreed overview heading, and make narration read
    exactly the same stories that the learner sees.
    """

    ordered_sections = sorted(
        enumerate(content.deep_sections),
        key=lambda item: (DEEP_SECTION_ORDER.get(item[1].key, 99), item[0]),
    )
    deep_sections = [
        section.model_copy(
            update={
                "title": _preferred_ui_wording(section.title),
                "summary": _preferred_ui_wording(section.summary),
                "body": _preferred_ui_wording(section.body),
            }
        )
        for _index, section in ordered_sections
    ]
    if deep_sections and deep_sections[0].key == "overview":
        deep_sections[0] = deep_sections[0].model_copy(
            update={"title": "Giới thiệu tổng quát"}
        )

    sorted_dated_entries = iter(
        sorted(
            (entry for entry in content.timeline if entry.year is not None),
            key=lambda entry: entry.year or 0,
        )
    )
    timeline = []
    for original in content.timeline:
        entry = next(sorted_dated_entries) if original.year is not None else original
        timeline.append(
            entry.model_copy(
                update={
                    "label": _preferred_ui_wording(entry.label),
                    "period": (
                        _preferred_ui_wording(entry.period)
                        if entry.period is not None
                        else None
                    ),
                }
            )
        )
    quick = content.storytelling.quick.model_copy(
        update={"text": _preferred_ui_wording(content.storytelling.quick.text)}
    )
    one_minute = content.storytelling.one_minute.model_copy(
        update={"text": _preferred_ui_wording(content.storytelling.one_minute.text)}
    )
    storytelling = content.storytelling.model_copy(
        update={"quick": quick, "one_minute": one_minute}
    )
    keywords = [
        keyword.model_copy(
            update={"explanation": _preferred_ui_wording(keyword.explanation)}
        )
        for keyword in content.keywords
    ]
    branches = [
        branch.model_copy(
            update={
                "label": _preferred_ui_wording(branch.label),
                "nodes": [
                    node.model_copy(
                        update={"note": _preferred_ui_wording(node.note)}
                    )
                    for node in branch.nodes
                ],
            }
        )
        for branch in content.mindmap.branches
    ]
    mindmap = content.mindmap.model_copy(update={"branches": branches})
    related_videos = [
        video.model_copy(
            update={
                "title": _preferred_ui_wording(video.title),
                "channel_name": _preferred_ui_wording(video.channel_name),
                "trust_reason": _preferred_ui_wording(video.trust_reason),
                "relevance": _preferred_ui_wording(video.relevance),
            }
        )
        for video in content.related_videos
    ]
    self_check = content.self_check
    if self_check is not None:
        self_check = self_check.model_copy(
            update={
                "question": _preferred_ui_wording(self_check.question),
                "explanation": _preferred_ui_wording(self_check.explanation),
            }
        )
    narration = content.narration.model_copy(
        update={
            "short_text": quick.text,
            "full_text": one_minute.text,
        }
    )
    return content.model_copy(
        update={
            "storytelling": storytelling,
            "deep_sections": deep_sections,
            "timeline": timeline,
            "keywords": keywords,
            "mindmap": mindmap,
            "related_videos": related_videos,
            "self_check": self_check,
            "narration": narration,
        }
    )


def _preferred_ui_wording(value: str) -> str:
    """Replace an unwanted interface noun without altering cited source records."""

    def replacement(match: re.Match[str]) -> str:
        return "Dữ liệu" if match.group(0)[:1].isupper() else "dữ liệu"

    return DISCOURAGED_UI_TERM.sub(replacement, value)


def _fallback_historical_excerpt(value: str | None) -> str | None:
    """Keep factual source sentences while omitting audience-directed copy.

    Canonical JSON remains untouched. This only protects deterministic fallback
    narration when an older description contains wording such as “người xem”.
    """

    cleaned = _clean_text(value, 3_000)
    if not cleaned:
        return None
    sentences = SENTENCE_BOUNDARY.split(cleaned)
    retained = [
        sentence.strip()
        for sentence in sentences
        if sentence.strip()
        and not AUDIENCE_DIRECTED_FRAMING.search(sentence)
        and not SECTION_META_OPENING.search(sentence)
    ]
    return " ".join(retained) or None


def extend_catalog_with_web_evidence(
    catalog: EvidenceCatalog,
    web_evidence: Iterable[WebEvidence],
) -> EvidenceCatalog:
    """Create a validation/public-reference view containing provider-verified web evidence."""

    values = dict(catalog.values)
    years = set(catalog.allowed_year_tokens)
    explicit_years = set(catalog.explicit_years)
    urls = set(catalog.allowed_urls)
    changed = False
    for evidence in web_evidence:
        if evidence.ref in values:
            raise EvidenceValidationError("Web evidence ref collides with existing evidence")
        safe_url = _http_url(evidence.url)
        if safe_url is None:
            raise EvidenceValidationError("Web evidence contains an invalid URL")
        values[evidence.ref] = EvidenceValue(
            ref=evidence.ref,
            label=_clip_text(evidence.title, 180),
            value=_clip_text(evidence.evidence_text, 1_200),
            source_status="available_unverified",
            url=safe_url,
            provenance="web_search",
        )
        urls.add(safe_url)
        for match in YEAR_TOKEN.finditer(evidence.evidence_text):
            years.add(match.group(0))
            explicit_years.add(int(match.group(0)))
        changed = True
    if not changed:
        return catalog
    return replace(
        catalog,
        values=values,
        explicit_years=frozenset(explicit_years),
        allowed_year_tokens=frozenset(years),
        allowed_urls=frozenset(urls),
    )


def extend_catalog_with_curated_videos(
    catalog: EvidenceCatalog,
    curated_videos: Iterable[CuratedVideoEntry],
) -> EvidenceCatalog:
    """Add manually reviewed video links without presenting them as tool sources."""

    values = dict(catalog.values)
    urls = set(catalog.allowed_urls)
    changed = False
    for video in curated_videos:
        if video.ref in values:
            raise EvidenceValidationError(
                "Curated video ref collides with existing evidence"
            )
        safe_url = _http_url(video.url)
        if safe_url is None or _youtube_video_id(safe_url) is None:
            raise EvidenceValidationError(
                "Curated video is not a specific YouTube video"
            )
        values[video.ref] = EvidenceValue(
            ref=video.ref,
            label=_clip_text(f"Video do ban biên tập chọn: {video.title}", 180),
            value=_clip_text(
                f"{video.relevance} Rà soát ngày {video.reviewed_at}.",
                1_200,
            ),
            source_status="verified",
            url=safe_url,
            provenance=video.provenance,
        )
        urls.add(safe_url)
        changed = True
    if not changed:
        return catalog
    return replace(
        catalog,
        values=values,
        allowed_urls=frozenset(urls),
    )


def _validate_refs(refs: Iterable[str], catalog: EvidenceCatalog) -> None:
    for ref in refs:
        if ref not in catalog.values:
            raise EvidenceValidationError("Generated content references unknown evidence")


def _validate_claim_ids(ids: Iterable[str], known_ids: set[str]) -> None:
    for claim_id in ids:
        if claim_id not in known_ids:
            raise EvidenceValidationError("Narrative references an unknown factual claim")


def _validate_material_sections(
    content: GeneratedLearningContent,
    catalog: EvidenceCatalog,
) -> None:
    """Reject concrete physical details absent from a material section's cited evidence."""

    claims = {claim.id: claim for claim in content.factual_claims}
    for section in content.deep_sections:
        if section.key != "material":
            continue
        refs = {
            ref
            for claim_id in section.claim_ids
            for ref in claims[claim_id].evidence_refs
        }
        evidence = _lexical_text(
            " ".join(catalog.values[ref].value for ref in refs if ref in catalog.values)
        )
        prose = " ".join((section.title, section.summary, section.body))
        lexical_prose = _lexical_text(prose)
        unsupported_terms = sorted(
            term
            for term in MATERIAL_DETAIL_TOKENS
            if _lexical_contains(lexical_prose, term)
            and not _lexical_contains(evidence, term)
        )
        unsupported_measurements = [
            match.group(0)
            for match in MEASUREMENT_TOKEN.finditer(prose)
            if _support_text(match.group(0)) not in _support_text(evidence)
        ]
        if unsupported_terms or unsupported_measurements:
            raise EvidenceValidationError(
                "Material section contains an unsupported physical detail"
            )


def _lexical_text(value: str) -> str:
    return " ".join(WORD_TOKEN.findall(_support_text(value)))


def _lexical_contains(value: str, term: str) -> bool:
    return f" {term} " in f" {value} "


def _is_evidence_excerpt(
    text: str,
    refs: Iterable[str],
    catalog: EvidenceCatalog,
) -> bool:
    candidate = _support_text(text)
    if not candidate:
        return False
    evidence_texts = [
        _support_text(catalog.values[ref].value)
        for ref in refs
        if ref in catalog.values
    ]
    if any(candidate in evidence for evidence in evidence_texts):
        return True

    # Models often make harmless Vietnamese inflection, punctuation, or word-order
    # changes even when asked for a contiguous quote. Require strong lexical support
    # instead of rejecting the whole response solely because it is not verbatim.
    # Dates and URLs remain subject to the exact allowlists below.
    candidate_tokens = list(dict.fromkeys(_significant_tokens(candidate)))
    if not candidate_tokens:
        return False
    evidence_tokens = {
        token
        for evidence in evidence_texts
        for token in _significant_tokens(evidence)
    }
    overlap = sum(token in evidence_tokens for token in candidate_tokens)
    required_ratio = 1.0 if len(candidate_tokens) <= 2 else 0.65
    return overlap >= min(2, len(candidate_tokens)) and (
        overlap / len(candidate_tokens)
    ) >= required_ratio


def _support_text(value: str) -> str:
    return " ".join(
        unicodedata.normalize("NFC", value)
        .casefold()
        .replace("_", " ")
        .replace("-", " ")
        .split()
    )


def _matches_allowed_url(url: str, allowed_urls: frozenset[str]) -> bool:
    """Accept an exact source URL followed only by prose/Markdown delimiters.

    A model may render an approved URL as ``(https://example.org/page).``. The
    URL tokenizer necessarily captures the closing characters; remove them
    one at a time while retaining exact allow-list matching at every step.
    """

    candidate = url
    while candidate:
        if candidate in allowed_urls:
            return True
        if candidate[-1] not in URL_TRAILING_DELIMITERS:
            return False
        candidate = candidate[:-1]
    return False


def _youtube_video_id(value: str) -> str | None:
    """Return a specific public YouTube video id, never a search/channel URL."""

    safe_url = _http_url(value)
    if safe_url is None:
        return None
    try:
        parsed = urlsplit(safe_url)
        if (
            parsed.scheme.casefold() != "https"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port is not None
        ):
            return None
    except ValueError:
        return None
    host = (parsed.hostname or "").casefold()
    candidate: str | None = None
    if host in {"youtu.be", "www.youtu.be"}:
        candidate = parsed.path.strip("/").split("/", 1)[0]
    elif host in {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
    }:
        path_parts = [part for part in parsed.path.split("/") if part]
        if parsed.path.rstrip("/") == "/watch":
            candidate = (parse_qs(parsed.query).get("v") or [None])[0]
        elif len(path_parts) == 2 and path_parts[0] in {"shorts", "live"}:
            candidate = path_parts[1]
    return candidate if candidate and YOUTUBE_VIDEO_ID.fullmatch(candidate) else None


def _validate_related_videos(
    content: GeneratedLearningContent,
    catalog: EvidenceCatalog,
) -> None:
    seen_video_ids: set[str] = set()
    for video in content.related_videos:
        _validate_refs(video.evidence_refs, catalog)
        video_id = _youtube_video_id(video.url)
        if video_id is None:
            raise EvidenceValidationError(
                "Related video URL is not a specific YouTube video"
            )
        if video_id in seen_video_ids:
            raise EvidenceValidationError("Duplicate related YouTube video")
        seen_video_ids.add(video_id)
        matching_source = any(
            ref.startswith(("web.", "curated.video."))
            and catalog.values[ref].url == video.url
            and _youtube_video_id(catalog.values[ref].url or "") == video_id
            for ref in video.evidence_refs
        )
        if not matching_source:
            raise EvidenceValidationError(
                "Related video URL is not backed by cited web evidence"
            )


def _significant_tokens(value: str) -> list[str]:
    return [
        token
        for token in WORD_TOKEN.findall(value)
        if token not in SUPPORT_STOPWORDS and (len(token) > 1 or token.isdigit())
    ]


def ground_web_evidence(
    content: GeneratedLearningContent,
) -> GeneratedLearningContent:
    """Attach verified searched sources to exact, non-invented factual claims.

    Structured generation can occasionally return valid ``web_evidence`` but
    forget to use its ref elsewhere. Preserve only sources that are already
    cited or can be represented by a verbatim evidence excerpt. This repairs a
    reference-link omission without manufacturing a historical assertion.
    """

    cited_refs = _content_evidence_refs(content)
    claims = list(content.factual_claims)
    claim_ids = {claim.id for claim in claims}
    retained: list[WebEvidence] = []
    changed = False
    for index, evidence in enumerate(content.web_evidence, start=1):
        retained.append(evidence)
        if evidence.ref in cited_refs:
            continue
        if len(claims) >= 30:
            retained.pop()
            changed = True
            continue
        base_id = f"web-evidence-{index}"
        claim_id = base_id
        suffix = 2
        while claim_id in claim_ids:
            claim_id = f"{base_id}-{suffix}"
            suffix += 1
        claims.append(
            EvidenceClaim(
                id=claim_id,
                text=_clip_text(evidence.evidence_text, 600),
                evidence_refs=[evidence.ref],
            )
        )
        claim_ids.add(claim_id)
        cited_refs.add(evidence.ref)
        changed = True
    if not changed:
        return content
    return content.model_copy(
        update={"factual_claims": claims, "web_evidence": retained}
    )


def repair_generated_grounding(
    content: GeneratedLearningContent,
    catalog: EvidenceCatalog,
) -> GeneratedLearningContent:
    """Reconcile model-created refs and exact-label fields with real evidence.

    Unknown model refs are never exposed. When a required ref or literal label
    is invalid, choose the closest existing local/provider-verified evidence
    and copy its text. Narrative prose is not rewritten here; unsupported
    years and URLs are still rejected by ``validate_generated_content``.
    """

    extended = extend_catalog_with_web_evidence(catalog, content.web_evidence)
    fallback_ref = _fallback_evidence_ref(extended)
    seen_claim_ids: set[str] = set()
    claims: list[EvidenceClaim] = []
    for index, claim in enumerate(content.factual_claims, start=1):
        claim_id = _unique_generated_id(
            claim.id, f"fact-{index}", seen_claim_ids
        )
        refs = _known_or_best_refs(claim.text, claim.evidence_refs, extended)
        text = claim.text
        if not _is_evidence_excerpt(text, refs, extended):
            best_ref = _best_evidence_ref(text, refs, extended)
            text = _clip_text(extended.values[best_ref].value, 600)
        claims.append(
            claim.model_copy(
                update={"id": claim_id, "text": text, "evidence_refs": refs}
            )
        )

    claim_ids = {claim.id for claim in claims}
    first_claim_id = claims[0].id
    quick = content.storytelling.quick.model_copy(
        update={
            "claim_ids": _known_claim_ids(
                content.storytelling.quick.claim_ids, claim_ids, first_claim_id
            )
        }
    )
    one_minute = content.storytelling.one_minute.model_copy(
        update={
            "claim_ids": _known_claim_ids(
                content.storytelling.one_minute.claim_ids,
                claim_ids,
                first_claim_id,
            )
        }
    )
    storytelling = content.storytelling.model_copy(
        update={"quick": quick, "one_minute": one_minute}
    )
    deep_sections = [
        section.model_copy(
            update={
                "claim_ids": _known_claim_ids(
                    section.claim_ids, claim_ids, first_claim_id
                )
            }
        )
        for section in content.deep_sections
    ]

    timeline: list[TimelineEntry] = []
    for entry in content.timeline:
        if entry.year is not None and str(entry.year) not in extended.allowed_year_tokens:
            continue
        refs = _known_or_best_refs(
            " ".join(
                part
                for part in (entry.label, entry.period, str(entry.year) if entry.year else None)
                if part
            ),
            entry.evidence_refs,
            extended,
        )
        timeline.append(entry.model_copy(update={"evidence_refs": refs}))

    keywords: list[Keyword] = []
    for keyword in content.keywords:
        refs = _known_or_best_refs(keyword.term, keyword.evidence_refs, extended)
        term = keyword.term
        if not _is_evidence_excerpt(term, refs, extended):
            best_ref = _best_evidence_ref(term, refs, extended)
            term = _clip_text(extended.values[best_ref].value, 100)
        keywords.append(
            keyword.model_copy(update={"term": term, "evidence_refs": refs})
        )

    seen_mindmap_ids: set[str] = set()
    branches: list[MindMapBranch] = []
    for branch_index, branch in enumerate(content.mindmap.branches, start=1):
        branch_id = _unique_generated_id(
            branch.id, f"branch-{branch_index}", seen_mindmap_ids
        )
        branch_refs = _known_or_best_refs(
            branch.label, branch.evidence_refs, extended
        )
        nodes: list[MindMapNode] = []
        for node_index, node in enumerate(branch.nodes, start=1):
            node_id = _unique_generated_id(
                node.id,
                f"node-{branch_index}-{node_index}",
                seen_mindmap_ids,
            )
            refs = _known_or_best_refs(node.label, node.evidence_refs, extended)
            label = node.label
            if not _is_evidence_excerpt(label, refs, extended):
                best_ref = _best_evidence_ref(label, refs, extended)
                label = _clip_text(extended.values[best_ref].value, 180)
            if _is_generic_mindmap_label(label):
                label = _clip_text(extended.values[fallback_ref].value, 180)
                refs = [fallback_ref]
            nodes.append(
                node.model_copy(
                    update={"id": node_id, "label": label, "evidence_refs": refs}
                )
            )
        branches.append(
            branch.model_copy(
                update={
                    "id": branch_id,
                    "evidence_refs": branch_refs,
                    "nodes": nodes,
                }
            )
        )

    central_label = content.mindmap.central_label
    if central_label not in extended.central_labels:
        central_ref = (
            "artifact.name"
            if "artifact.name" in extended.values
            else "history.title"
        )
        central_label = extended.values[central_ref].value
    mindmap = content.mindmap.model_copy(
        update={"central_label": central_label, "branches": branches}
    )

    related_videos: list[RelatedVideo] = []
    seen_video_ids: set[str] = set()
    for video in content.related_videos:
        source_ref = next(
            (
                ref
                for ref in video.evidence_refs
                if ref.startswith("web.")
                and ref in extended.values
                and extended.values[ref].url is not None
                and _youtube_video_id(extended.values[ref].url or "") is not None
            ),
            None,
        )
        if source_ref is None:
            continue
        source = extended.values[source_ref]
        assert source.url is not None
        video_id = _youtube_video_id(source.url)
        if video_id is None or video_id in seen_video_ids:
            continue
        seen_video_ids.add(video_id)
        related_videos.append(
            video.model_copy(
                update={
                    "title": _clip_text(source.label, 300),
                    "url": source.url,
                    "evidence_refs": [source_ref],
                }
            )
        )

    self_check = content.self_check
    if self_check is not None:
        correct_index = next(
            index
            for index, option in enumerate(self_check.options)
            if option.id == self_check.correct_option_id
        )
        correct = self_check.options[correct_index]
        refs = _known_or_best_refs(
            correct.label, self_check.evidence_refs, extended
        )
        label = correct.label
        if not _is_evidence_excerpt(label, refs, extended):
            best_ref = _best_evidence_ref(label, refs, extended)
            label = _clip_text(extended.values[best_ref].value, 220)
        options = list(self_check.options)
        options[correct_index] = correct.model_copy(update={"label": label})
        self_check = self_check.model_copy(
            update={"options": options, "evidence_refs": refs}
        )

    return content.model_copy(
        update={
            "factual_claims": claims,
            "storytelling": storytelling,
            "deep_sections": deep_sections,
            "timeline": timeline,
            "keywords": keywords,
            "mindmap": mindmap,
            "related_videos": related_videos,
            "self_check": self_check,
        }
    )


def _known_or_best_refs(
    text: str,
    refs: Iterable[str],
    catalog: EvidenceCatalog,
) -> list[str]:
    known = list(dict.fromkeys(ref for ref in refs if ref in catalog.values))
    if known:
        return known
    return [_best_evidence_ref(text, catalog.values, catalog)]


def _best_evidence_ref(
    text: str,
    refs: Iterable[str],
    catalog: EvidenceCatalog,
) -> str:
    refs = list(refs)
    wanted_tokens = set(_significant_tokens(_support_text(text)))
    scored = [
        (
            len(
                wanted_tokens
                & set(_significant_tokens(_support_text(catalog.values[ref].value)))
            ),
            ref,
        )
        for ref in refs
        if ref in catalog.values
    ]
    if not scored:
        return _fallback_evidence_ref(catalog)
    if max(score for score, _ref in scored) == 0:
        return scored[0][1]
    return max(
        scored,
        key=lambda item: item[0],
    )[1]


def _fallback_evidence_ref(catalog: EvidenceCatalog) -> str:
    for ref in ("history.description", "artifact.name", "history.title"):
        if ref in catalog.values:
            return ref
    return next(iter(catalog.values))


def _known_claim_ids(
    ids: Iterable[str],
    known_ids: set[str],
    fallback_id: str,
) -> list[str]:
    known = list(dict.fromkeys(claim_id for claim_id in ids if claim_id in known_ids))
    return known or [fallback_id]


def _unique_generated_id(value: str, fallback: str, seen: set[str]) -> str:
    candidate = value if value not in seen else fallback
    suffix = 2
    base = candidate
    while candidate in seen:
        candidate = f"{base}-{suffix}"
        suffix += 1
    seen.add(candidate)
    return candidate


def _is_generic_mindmap_label(value: str) -> bool:
    return _support_text(value) in {
        "lịch sử",
        "thông tin",
        "ý nghĩa",
        "bối cảnh",
        "sự kiện",
        "câu chuyện",
    }


def _validate_historical_framing(content: GeneratedLearningContent) -> None:
    """Reject museum prose that talks about teaching instead of the history."""

    for text in _historical_narrative_strings(content):
        if AUDIENCE_DIRECTED_FRAMING.search(text):
            raise EvidenceValidationError(
                "Generated text uses audience-directed educational framing"
            )
    for section in content.deep_sections:
        if SECTION_META_OPENING.search(section.summary) or SECTION_META_OPENING.search(
            section.body
        ):
            raise EvidenceValidationError("Deep section uses a meta introduction")


def _historical_narrative_strings(
    content: GeneratedLearningContent,
) -> Iterable[str]:
    """Yield authored explanation while leaving verbatim evidence claims untouched."""

    yield content.storytelling.quick.text
    yield content.storytelling.one_minute.text
    for section in content.deep_sections:
        yield section.title
        yield section.summary
        yield section.body
    for entry in content.timeline:
        yield entry.label
    for keyword in content.keywords:
        yield keyword.explanation
    for branch in content.mindmap.branches:
        yield branch.label
        for node in branch.nodes:
            yield node.note
    for video in content.related_videos:
        yield video.relevance
    if content.self_check is not None:
        yield content.self_check.question
        yield content.self_check.explanation


def _generated_prose_strings(
    content: GeneratedLearningContent,
) -> Iterable[str]:
    """Yield user-visible model prose, excluding ids and evidence ref tokens."""

    yield from (claim.text for claim in content.factual_claims)
    yield content.storytelling.quick.text
    yield content.storytelling.one_minute.text
    for section in content.deep_sections:
        yield section.title
        yield section.summary
        yield section.body
    for entry in content.timeline:
        yield entry.label
        if entry.period:
            yield entry.period
    for keyword in content.keywords:
        yield keyword.term
        yield keyword.explanation
    yield content.mindmap.central_label
    for branch in content.mindmap.branches:
        yield branch.label
        for node in branch.nodes:
            yield node.label
            if node.note:
                yield node.note
    for video in content.related_videos:
        yield video.title
        yield video.url
        yield video.channel_name
        yield video.trust_reason
        yield video.relevance
    if content.self_check is not None:
        yield content.self_check.question
        yield from (option.label for option in content.self_check.options)
        yield content.self_check.explanation
    yield content.narration.short_text
    yield content.narration.full_text


def _content_evidence_refs(content: GeneratedLearningContent) -> set[str]:
    refs = {
        ref
        for claim in content.factual_claims
        for ref in claim.evidence_refs
    }
    refs.update(
        ref
        for entry in content.timeline
        for ref in entry.evidence_refs
    )
    refs.update(
        ref
        for keyword in content.keywords
        for ref in keyword.evidence_refs
    )
    for branch in content.mindmap.branches:
        refs.update(branch.evidence_refs)
        for node in branch.nodes:
            refs.update(node.evidence_refs)
    refs.update(
        ref
        for video in content.related_videos
        for ref in video.evidence_refs
    )
    if content.self_check is not None:
        refs.update(content.self_check.evidence_refs)
    return refs


def build_fallback_content(
    artifact: ArtifactRecord,
    catalog: EvidenceCatalog,
) -> GeneratedLearningContent:
    """Build useful learning UI from canonical fields without an AI call."""

    history = artifact.historical_info
    claims: list[EvidenceClaim] = []

    def claim(text: str, refs: list[str]) -> str:
        existing_refs = [ref for ref in refs if ref in catalog.values]
        claim_id = f"fact-{len(claims) + 1}"
        claims.append(EvidenceClaim(id=claim_id, text=_clip_text(text, 600), evidence_refs=existing_refs))
        return claim_id

    title = _clean_text(history.title, 300) or _clean_text(artifact.name, 300) or "Hiện vật"
    title_ref = "history.title" if "history.title" in catalog.values else "artifact.name"
    title_claim = claim(title, [title_ref])
    category_text = _clean_text(artifact.category, 120) or "chưa phân loại"
    category_display = category_label(category_text)
    category_ref = (
        "artifact.category_label"
        if "artifact.category_label" in catalog.values
        else "artifact.category"
    )
    category_claim = claim(category_display, [category_ref])
    quick_parts = [title, category_display]
    quick_claims = [title_claim, category_claim]

    if history.historical_period and "history.period" in catalog.values:
        period = _clean_text(history.historical_period, 300) or ""
        quick_parts.append(period)
        quick_claims.append(claim(period, ["history.period"]))
    if history.year is not None and "history.year" in catalog.values:
        quick_parts.append(str(history.year))
        quick_claims.append(claim(str(history.year), ["history.year"]))

    description = _fallback_historical_excerpt(history.description)
    if description:
        description_refs = (
            ["history.description"]
            if "history.description" in catalog.values
            else [title_ref]
        )
    else:
        description = title
        description_refs = [title_ref]
    description_claim = claim(description, description_refs)
    event_claim: str | None = None
    event = _clean_text(history.event, 500)
    if event and "history.event" in catalog.values:
        event_claim = claim(event, ["history.event"])

    deep_sections = [
        DeepSection(
            key="overview",
            title="Tổng quan hiện vật",
            summary=_clip_text(description, 300),
            body=_clip_text(description, 2_400),
            claim_ids=[description_claim],
        ),
        DeepSection(
            key="recognition",
            title="Đặc điểm nhận diện",
            summary=f"Tên: {title}",
            body=f"Dữ liệu nhận diện hiện vật là {title}, thuộc nhóm {category_display}.",
            claim_ids=[title_claim, category_claim],
        ),
    ]
    context_ids = quick_claims[2:] + ([event_claim] if event_claim else [])
    if context_ids:
        context_body = ". ".join(quick_parts[2:] + ([event] if event else []))
        deep_sections.append(
            DeepSection(
                key="context",
                title="Bối cảnh được ghi nhận",
                summary=_clip_text(context_body, 300),
                body=_clip_text(context_body, 2_400),
                claim_ids=context_ids,
            )
        )

    timeline: list[TimelineEntry] = []
    if history.year is not None and "history.year" in catalog.values:
        timeline.append(
            TimelineEntry(
                label=f"Mốc năm được ghi cho {title}",
                year=history.year,
                period=None,
                evidence_refs=["history.year"],
            )
        )
    for image in artifact.images[:12]:
        if image.year is None:
            continue
        safe_id = re.sub(r"[^A-Za-z0-9_-]", "-", image.id)[:80] or "image"
        ref = f"image.{safe_id}.year"
        if ref in catalog.values:
            timeline.append(
                TimelineEntry(
                    label=_clean_text(image.caption, 220) or f"Ảnh của {title}",
                    year=image.year,
                    period=None,
                    evidence_refs=[ref],
                )
            )

    keywords: list[Keyword] = [
        Keyword(term=_clip_text(title, 100), explanation="Tên được ghi trong dữ liệu hiện vật.", evidence_refs=[title_ref]),
        Keyword(
            term=_clip_text(category_display, 100),
            explanation="Nhóm phân loại trong bộ dữ liệu.",
            evidence_refs=[category_ref],
        ),
    ]
    for index, tag in enumerate(artifact.tags[:8]):
        ref = f"artifact.tags[{index}]"
        if ref in catalog.values:
            keywords.append(
                Keyword(
                    term=_clip_text(tag.replace("-", " ").replace("_", " "), 100),
                    explanation="Từ khóa có trong dữ liệu hiện vật.",
                    evidence_refs=[ref],
                )
            )

    recognition_nodes = [
        MindMapNode(id="node-name", label=_clip_text(title, 180), note="Tên hiện vật", evidence_refs=[title_ref]),
        MindMapNode(
            id="node-category",
            label=_clip_text(category_display, 180),
            note="Nhóm phân loại",
            evidence_refs=[category_ref],
        ),
    ]
    branches = [
        MindMapBranch(
            id="branch-recognition",
            label="Nhận diện",
            relation="identified_by",
            evidence_refs=[title_ref, category_ref],
            nodes=recognition_nodes,
        )
    ]
    time_nodes: list[MindMapNode] = []
    if "history.period" in catalog.values:
        time_nodes.append(
            MindMapNode(
                id="node-period",
                label=_clip_text(history.historical_period or "", 180),
                note="Giai đoạn được ghi trong dữ liệu",
                evidence_refs=["history.period"],
            )
        )
    if "history.year" in catalog.values:
        time_nodes.append(
            MindMapNode(
                id="node-year",
                label=str(history.year),
                note="Năm được ghi trong dữ liệu",
                evidence_refs=["history.year"],
            )
        )
    if time_nodes:
        branches.append(
            MindMapBranch(
                id="branch-time",
                label="Thời gian",
                relation="dated_to",
                evidence_refs=[
                    ref
                    for ref in ("history.period", "history.year")
                    if ref in catalog.values
                ],
                nodes=time_nodes,
            )
        )

    location_nodes: list[MindMapNode] = []
    for suffix, label in (("city", "Thành phố"), ("province", "Tỉnh/thành"), ("country", "Quốc gia")):
        ref = f"location.{suffix}"
        if ref in catalog.values:
            location_nodes.append(
                MindMapNode(
                    id=f"node-{suffix}",
                    label=_clip_text(catalog.values[ref].value, 180),
                    note=label,
                    evidence_refs=[ref],
                )
            )
    if location_nodes:
        branches.append(
            MindMapBranch(
                id="branch-location",
                label="Địa điểm",
                relation="located_at",
                evidence_refs=[
                    ref
                    for ref in (
                        "location.city",
                        "location.province",
                        "location.country",
                    )
                    if ref in catalog.values
                ],
                nodes=location_nodes,
            )
        )
    if event and "history.event" in catalog.values:
        branches.append(
            MindMapBranch(
                id="branch-context",
                label="Bối cảnh",
                relation="associated_with",
                evidence_refs=["history.event"],
                nodes=[
                    MindMapNode(
                        id="node-event",
                        label=_clip_text(event, 180),
                        note="Sự kiện được ghi trong dữ liệu",
                        evidence_refs=["history.event"],
                    )
                ],
            )
        )

    quick_text = _clip_text(" — ".join(part for part in quick_parts if part), 500)
    full_text = _clip_text(
        " ".join(part for part in [quick_text + ".", description, f"Sự kiện liên quan: {event}." if event else None] if part),
        3_800,
    )
    self_check = SelfCheck(
        question=f"Theo dữ liệu hiện vật, “{_clip_text(title, 180)}” thuộc nhóm nào?",
        options=[
            SelfCheckOption(id="answer-category", label=category_display),
            SelfCheckOption(id="answer-unknown", label="Chưa có thông tin phân loại"),
        ],
        correct_option_id="answer-category",
        explanation=f"Dữ liệu xếp hiện vật vào nhóm {category_display}.",
        evidence_refs=[category_ref],
    )
    result = GeneratedLearningContent(
        factual_claims=claims,
        storytelling=StoryContent(
            quick=StoryBlock(text=quick_text, claim_ids=quick_claims),
            one_minute=StoryBlock(
                text=full_text,
                claim_ids=list(
                    dict.fromkeys(
                        quick_claims
                        + [description_claim]
                        + ([event_claim] if event_claim else [])
                    )
                ),
            ),
        ),
        deep_sections=deep_sections,
        timeline=timeline,
        keywords=keywords,
        mindmap=MindMap(central_label=_clip_text(title, 180), branches=branches),
        self_check=self_check,
        narration=NarrationText(short_text=quick_text, full_text=full_text),
    )
    result = normalize_generated_editorial_structure(result)
    validate_generated_content(result, catalog)
    return result
