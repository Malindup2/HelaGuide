"""Reusable wording; never a replacement for the canonical procedure graph."""

from typing import Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from app.models.explanations import EvidenceQuote, HumanReview, ProviderCall, ProviderIdentity
from app.models.procedure_graph import CanonicalProcedureGraph, GraphRecord


WordingStyle = Literal["plain", "extra_plain", "concise"]
SlotKind = Literal[
    "action_heading", "action_explanation", "action_summary",
    "diagram_label", "prerequisite_explanation",
]


class WordingReference(GraphRecord):
    kind: Literal[
        "stage", "action", "content", "condition", "fact", "evidence",
        "stage_dependency", "action_prerequisite", "branch_group",
        "branch_option", "parallel_group",
    ]
    reference_id: str = Field(min_length=1)


class WordingTarget(GraphRecord):
    slot_id: str = Field(min_length=1)
    kind: SlotKind
    subject: WordingReference
    source_references: tuple[WordingReference, ...]
    evidence_ids: tuple[str, ...]
    fallback_text: str


class WordingPacket(GraphRecord):
    contract_version: Literal["c4-prepared-wording-1.0"] = "c4-prepared-wording-1.0"
    graph_fingerprint: str
    language: Literal["en"] = "en"
    writing_style: WordingStyle
    graph: CanonicalProcedureGraph
    targets: tuple[WordingTarget, ...]


class WordingItem(GraphRecord):
    slot_id: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=2000)
    source_references: tuple[WordingReference, ...]
    citations: tuple[EvidenceQuote, ...]


class WordingDraft(GraphRecord):
    synthetic: bool
    items: tuple[WordingItem, ...]


class HumanWordingSubmission(GraphRecord):
    source: WordingPacket
    author_reference: str = Field(min_length=1)
    draft: WordingDraft


class WordingAssessmentItem(GraphRecord):
    slot_id: str
    supported: bool
    preserves_meaning: bool
    contains_new_requirement: bool
    reason: str


class WordingAssessment(GraphRecord):
    items: tuple[WordingAssessmentItem, ...]


class WordingArtifact(GraphRecord):
    schema_version: Literal["c4-prepared-artifact-1.0"] = "c4-prepared-artifact-1.0"
    request_key: str
    recipe_version: str
    created_at: AwareDatetime
    source: WordingPacket
    origin: Literal["human_prepared", "provider_generated"]
    author_reference: str | None
    provider: ProviderIdentity | None
    generation_calls: tuple[ProviderCall, ...]
    assessment_calls: tuple[ProviderCall, ...]
    draft: WordingDraft
    assessment: WordingAssessment | None
    review: HumanReview | None = None

    @model_validator(mode="after")
    def provenance_is_honest(self) -> Self:
        if self.origin == "human_prepared":
            if (
                not self.author_reference or not self.author_reference.strip()
                or self.provider is not None or self.generation_calls
                or self.assessment_calls or self.assessment is not None
            ):
                raise ValueError("human content requires author reference and no provider records")
        elif (
            self.author_reference is not None or self.provider is None
            or not self.generation_calls or not self.assessment_calls
            or len(self.generation_calls) != len(self.assessment_calls)
            or self.assessment is None
        ):
            raise ValueError("generated content requires actual generation and assessment records")
        return self


class ResolvedWordingItem(GraphRecord):
    slot_id: str
    text: str
    source_references: tuple[WordingReference, ...]
    origin: Literal["human_prepared", "provider_generated", "source_fallback"]


class WordingResolution(GraphRecord):
    request_key: str
    graph_fingerprint: str
    artifact_digest: str | None
    diagnostics: tuple[str, ...]
    items: tuple[ResolvedWordingItem, ...]
