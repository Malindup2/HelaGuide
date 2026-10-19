"""Structured explanation, assessment and source-preservation records."""

from typing import Literal

from pydantic import AwareDatetime, Field

from app.models.procedure_graph import CanonicalProcedureGraph, GraphRecord
from app.models.scaffolds import (
    Notice,
    PreservationContract,
    ScaffoldConfiguration,
)


class EvidenceQuote(GraphRecord):
    evidence_id: str
    quote: str


class ExplanationDraftItem(GraphRecord):
    unit_id: str
    text: str
    fact_ids: tuple[str, ...]
    citations: tuple[EvidenceQuote, ...]


class ExplanationDraft(GraphRecord):
    synthetic: bool
    items: tuple[ExplanationDraftItem, ...]


class ItemAssessment(GraphRecord):
    unit_id: str
    supported: bool
    preserves_meaning: bool
    contains_new_requirement: bool
    reason: str


class ExplanationAssessment(GraphRecord):
    items: tuple[ItemAssessment, ...]


class ProviderIdentity(GraphRecord):
    name: str
    requested_model: str
    sdk_version: str
    reasoning_effort: Literal["low"] = "low"
    max_output_tokens: int = Field(default=6000, ge=512, le=16000)


class ProviderCall(GraphRecord):
    response_id: str
    returned_model: str
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)


class ProviderReply(GraphRecord):
    text: str
    call: ProviderCall


class HumanReview(GraphRecord):
    artifact_digest: str
    reviewer_reference: str
    reviewed_at: AwareDatetime
    statement: Literal["checked_against_supplied_sources"] = (
        "checked_against_supplied_sources"
    )


class CachedExplanation(GraphRecord):
    schema_version: Literal["1.0"] = "1.0"
    request_key: str
    graph_fingerprint: str
    prompt_version: str
    validation_version: str
    provider: ProviderIdentity
    created_at: AwareDatetime

    draft: ExplanationDraft
    assessment: ExplanationAssessment
    generation_call: ProviderCall
    assessment_call: ProviderCall
    review: HumanReview | None = None


class SourceBundle(GraphRecord):
    """Original records remain available independently of generated prose."""

    graph: CanonicalProcedureGraph
    notices: tuple[Notice, ...]
    preservation: PreservationContract


class DisplayExplanation(GraphRecord):
    unit_id: str
    action_id: str
    content_id: str
    origin: Literal["generated", "source_copy"]
    text: str
    fact_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    citations: tuple[EvidenceQuote, ...]


class ExplanationResult(GraphRecord):
    schema_version: Literal["1.0"] = "1.0"

    request_key: str
    graph_fingerprint: str
    decision_id: str
    exposure_id: str
    configuration: ScaffoldConfiguration

    source_status: Literal["synthetic", "supplied_sources_unverified"]
    origin: Literal["generated", "fallback"]
    assurance: Literal[
        "automated_checks_only",
        "human_reviewed_against_supplied_sources",
        "source_preserving_copy",
    ]
    cache_hit: bool
    diagnostics: tuple[str, ...]

    source: SourceBundle
    explanations: tuple[DisplayExplanation, ...]
    artifact: CachedExplanation | None

class StandardExplanationResult(GraphRecord):
    """Neutral explanation output without a policy decision or exposure."""

    schema_version: Literal["c4-standard-explanations-1.0"] = (
        "c4-standard-explanations-1.0"
    )
    request_key: str
    graph_fingerprint: str
    source_status: Literal["synthetic", "supplied_sources_unverified"]
    origin: Literal["generated", "fallback"]
    assurance: Literal[
        "automated_checks_only",
        "human_reviewed_against_supplied_sources",
        "source_preserving_copy",
    ]
    cache_hit: bool
    diagnostics: tuple[str, ...]
    source: SourceBundle
    explanations: tuple[DisplayExplanation, ...]
    artifact: CachedExplanation | None
