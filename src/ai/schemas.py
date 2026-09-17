from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.text import normalize_unicode_tree


EvidenceRef = str


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, strict=True)

    @model_validator(mode="before")
    @classmethod
    def normalize_unicode(cls, value: Any) -> Any:
        return normalize_unicode_tree(value)


class EvidenceClaim(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,79}$")
    text: str = Field(min_length=1, max_length=600)
    evidence_refs: list[EvidenceRef] = Field(min_length=1, max_length=8)


class StoryBlock(StrictModel):
    text: str = Field(min_length=1, max_length=3_800)
    claim_ids: list[str] = Field(min_length=1, max_length=20)


class StoryContent(StrictModel):
    quick: StoryBlock = Field(
        description=(
            "A 10-second Vietnamese identity card: the artifact name, type, "
            "recorded period, and place when supported."
        )
    )
    one_minute: StoryBlock = Field(
        description=(
            "A coherent 135-165-word Vietnamese story written for natural "
            "reading in about one minute. It connects identity, historical "
            "context, event flow, the artifact's role, and lasting meaning."
        )
    )


class DeepSection(StrictModel):
    key: Literal[
        "overview",
        "identity",
        "recognition",
        "material",
        "context",
        "timeline",
        "role",
        "impact",
        "provenance",
        "education",
        "sources",
        "significance",
        "story",
        "related",
    ]
    title: str = Field(
        min_length=1,
        max_length=100,
        description="Specific Vietnamese heading; never a generic placeholder.",
    )
    summary: str = Field(
        min_length=1,
        max_length=300,
        description="A concrete two- or three-sentence orientation for this section.",
    )
    body: str = Field(
        min_length=1,
        max_length=2_400,
        description=(
            "Detailed source-grounded Vietnamese explanation that adds concrete "
            "object details, historical causality, or documented meaning instead "
            "of repeating the overview. Material and technique must never be inferred."
        ),
    )
    claim_ids: list[str] = Field(min_length=1, max_length=20)


class TimelineEntry(StrictModel):
    label: str = Field(
        min_length=1,
        max_length=220,
        description=(
            "Concrete historical development and its direct connection to the artifact."
        ),
    )
    year: int | None
    period: str | None = Field(max_length=160)
    evidence_refs: list[EvidenceRef] = Field(min_length=1, max_length=8)


class Keyword(StrictModel):
    term: str = Field(min_length=1, max_length=100)
    explanation: str = Field(min_length=1, max_length=260)
    evidence_refs: list[EvidenceRef] = Field(min_length=1, max_length=6)


class MindMapNode(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,79}$")
    label: str = Field(min_length=1, max_length=180)
    note: str = Field(
        min_length=1,
        max_length=650,
        description=(
            "Two concise Vietnamese sentences: explain this step's exact connection "
            "to the artifact, then connect it to the next historical development."
        ),
    )
    evidence_refs: list[EvidenceRef] = Field(min_length=1, max_length=6)


class MindMapBranch(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,79}$")
    label: str = Field(
        min_length=1,
        max_length=100,
        description=(
            "An ordered, concrete stage of the related history, such as the "
            "antecedent, event, consequence, or legacy."
        ),
    )
    relation: Literal[
        "identified_by",
        "dated_to",
        "located_at",
        "associated_with",
        "used_by",
        "part_of",
        "led_to",
        "evidenced_by",
        "described_by",
    ]
    evidence_refs: list[EvidenceRef] = Field(min_length=1, max_length=8)
    nodes: list[MindMapNode] = Field(
        min_length=1,
        max_length=5,
        description="Three to five ordered, concrete, source-grounded steps within this stage.",
    )


class MindMap(StrictModel):
    central_label: str = Field(min_length=1, max_length=180)
    branches: list[MindMapBranch] = Field(
        min_length=1,
        max_length=10,
        description=(
            "Five to six branches ordered as a causal and chronological historical "
            "flow around the artifact: antecedent, actors, central event, immediate "
            "human consequence, later consequence, and legacy when supported."
        ),
    )


class SelfCheckOption(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,79}$")
    label: str = Field(min_length=1, max_length=220)


class SelfCheck(StrictModel):
    question: str = Field(min_length=1, max_length=500)
    options: list[SelfCheckOption] = Field(min_length=2, max_length=5)
    correct_option_id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,79}$")
    explanation: str = Field(min_length=1, max_length=700)
    evidence_refs: list[EvidenceRef] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def correct_option_exists(self) -> "SelfCheck":
        option_ids = [option.id for option in self.options]
        if len(option_ids) != len(set(option_ids)):
            raise ValueError("Self-check option ids must be unique")
        if self.correct_option_id not in option_ids:
            raise ValueError("correct_option_id must refer to an offered option")
        return self


class NarrationText(StrictModel):
    short_text: str = Field(min_length=1, max_length=500)
    full_text: str = Field(min_length=1, max_length=3_800)


class WebEvidence(StrictModel):
    """A source discovered by the provider's web-search tool.

    The provider verifies ``url`` against the URLs returned by the tool before
    this object can reach the service or cache.
    """

    ref: str = Field(pattern=r"^web\.[1-9][0-9]{0,1}$")
    title: str = Field(min_length=1, max_length=300)
    url: str = Field(min_length=1, max_length=2_000)
    evidence_text: str = Field(min_length=1, max_length=1_200)


class GeneratedLearningContent(StrictModel):
    """Only the model-generated portion of the public response.

    Every property is required, including nullable/empty-list properties.  It
    keeps the JSON Schema compatible with strict Structured Outputs.
    """

    factual_claims: list[EvidenceClaim] = Field(min_length=1, max_length=30)
    storytelling: StoryContent
    deep_sections: list[DeepSection] = Field(
        max_length=12,
        description=(
            "Six to eight non-repeating sections. Start with a detailed overview, "
            "then cover recognition, source-supported material or construction, "
            "historical context and story, role or impact, documented meaning, and sources."
        ),
    )
    timeline: list[TimelineEntry] = Field(
        max_length=20,
        description=(
            "Chronologically ordered historical developments; use a null year when "
            "the evidence supplies only a period and never infer a date."
        ),
    )
    keywords: list[Keyword] = Field(max_length=20)
    mindmap: MindMap
    self_check: SelfCheck | None
    narration: NarrationText
    web_evidence: list[WebEvidence] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def storytelling_levels_are_distinct(self) -> "GeneratedLearningContent":
        quick = " ".join(self.storytelling.quick.text.casefold().split())
        one_minute = " ".join(self.storytelling.one_minute.text.casefold().split())
        if quick == one_minute:
            raise ValueError("Quick and one-minute storytelling must be distinct")
        section_keys = [section.key for section in self.deep_sections]
        if len(section_keys) != len(set(section_keys)):
            raise ValueError("Deep-section keys must be unique")
        return self

    @classmethod
    def openai_json_schema(cls) -> dict[str, Any]:
        schema = cls.model_json_schema()
        # These richer bounds apply only to provider Structured Outputs. The
        # runtime Pydantic model intentionally remains able to represent a
        # smaller deterministic fallback when the source record is sparse.
        schema["properties"]["deep_sections"].update(
            {"minItems": 6, "maxItems": 8}
        )
        schema["properties"]["timeline"].update(
            {"minItems": 4, "maxItems": 12}
        )
        definitions = schema.get("$defs", {})
        definitions["DeepSection"]["properties"]["summary"].update(
            {"minLength": 80}
        )
        definitions["DeepSection"]["properties"]["body"].update(
            {"minLength": 220}
        )
        definitions["MindMap"]["properties"]["branches"].update(
            {"minItems": 5, "maxItems": 6}
        )
        definitions["MindMapBranch"]["properties"]["nodes"].update(
            {"minItems": 3, "maxItems": 5}
        )
        definitions["MindMapNode"]["properties"]["note"].update(
            {"minLength": 80}
        )
        # OpenAI strict schemas do not allow sibling keywords beside ``$ref``.
        # Pydantic adds each field description next to that reference, so
        # inline both StoryBlock uses before applying their distinct bounds.
        quick = deepcopy(definitions["StoryBlock"])
        quick["description"] = definitions["StoryContent"]["properties"][
            "quick"
        ].get("description", "")
        definitions["StoryContent"]["properties"]["quick"] = quick

        # ``quick`` and ``one_minute`` share the runtime StoryBlock model, but
        # only the latter needs enough prose for roughly one spoken minute.
        one_minute = deepcopy(definitions["StoryBlock"])
        one_minute["description"] = definitions["StoryContent"]["properties"][
            "one_minute"
        ].get("description", "")
        one_minute["properties"]["text"].update(
            {"minLength": 600, "maxLength": 1_400}
        )
        definitions["StoryContent"]["properties"]["one_minute"] = one_minute
        _make_schema_strict(schema)
        return schema


def _make_schema_strict(node: Any) -> None:
    """Add strict-object constraints throughout a Pydantic JSON Schema."""

    if isinstance(node, dict):
        if node.get("type") == "object" or "properties" in node:
            node["additionalProperties"] = False
            properties = node.get("properties")
            if isinstance(properties, dict):
                node["required"] = list(properties)
        for value in node.values():
            _make_schema_strict(value)
    elif isinstance(node, list):
        for value in node:
            _make_schema_strict(value)


class EvidenceReference(StrictModel):
    ref: str = Field(min_length=1, max_length=180)
    label: str = Field(min_length=1, max_length=180)
    value: str = Field(min_length=1, max_length=1_200)
    source_status: Literal["not_applicable", "missing", "available_unverified", "verified"]
    url: str | None = Field(max_length=2_000)


DataStatus = Literal["missing", "needs_verification", "sufficient"]
GenerationStatus = Literal[
    "generated",
    "fallback_missing_source",
    "fallback_needs_verification",
    "fallback_insufficient_data",
    "fallback_disabled",
    "fallback_unavailable",
    "fallback_invalid_output",
]
CacheStatus = Literal["hit", "miss", "bypass"]


class LearningContentEnvelope(StrictModel):
    artifact_id: str
    data_status: DataStatus
    source_status: Literal["missing", "available_unverified", "verified"]
    generation_status: GenerationStatus
    cache_status: CacheStatus
    prompt_version: str
    schema_version: str
    model: str | None
    content: GeneratedLearningContent
    references: list[EvidenceReference]
    notice: str


class NarrationRequest(StrictModel):
    variant: Literal["short", "full"]


class NarrationResponse(StrictModel):
    artifact_id: str
    variant: Literal["short", "full"]
    status: Literal["ready", "fallback_required"]
    cache_status: CacheStatus
    transcript: str = Field(min_length=1, max_length=3_800)
    asset_id: str | None
    audio_url: str | None
    mime_type: Literal["audio/wav"] | None
    notice: str
