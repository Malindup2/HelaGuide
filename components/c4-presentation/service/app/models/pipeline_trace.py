"""Read-only research projections; these models are not persisted runtime state."""

from typing import Literal

from pydantic import AwareDatetime, Field

from app.models.corrections import CorrectionRecord
from app.models.guidance import GuidanceStatus
from app.models.policy import CandidateScore, PolicyOffer
from app.models.prepared_wording import WordingArtifact, WordingResolution, WordingStyle
from app.models.presentation import PresentationSpec
from app.models.procedure_features import FeatureMeasurement
from app.models.procedure_graph import GraphRecord
from app.models.runtime_state import AcceptedFeedback
from app.models.scaffolds import Reason, ScaffoldConfiguration
from app.models.user_context import ActionDisplay, PresentationExposure, UserSettings


class EvidenceBoundary(GraphRecord):
    section: str
    kind: Literal["recorded", "derived", "unavailable"]
    location: str
    explanation: str


class RecordedTrace(GraphRecord):
    policy_offer: PolicyOffer
    presentation: PresentationSpec
    wording: WordingResolution | None
    wording_artifact: WordingArtifact | None
    wording_style: WordingStyle | None
    acknowledgment: PresentationExposure | None
    navigation_events: tuple[ActionDisplay, ...]
    feedback: AcceptedFeedback | None
    correction: CorrectionRecord | None


class TraceFeature(GraphRecord):
    name: str
    measurement: FeatureMeasurement


class TraceCandidate(GraphRecord):
    configuration: ScaffoldConfiguration
    feasible: bool
    selected: bool
    satisfied: tuple[Reason, ...]
    rejections: tuple[Reason, ...]
    score_status: Literal["not_scored", "recorded_moments_not_sampled", "recorded_thompson_score"]
    score: CandidateScore | None


class InputSummary(GraphRecord):
    graph_fingerprint: str
    fingerprint_matches_saved_graph: bool
    graph_counts: dict[str, int]
    raw_plan_payload: Literal["not_stored"] = "not_stored"
    raw_enrichment_payload: Literal["not_stored"] = "not_stored"
    historical_validation_event: Literal["not_recorded"] = "not_recorded"
    source_authenticity: Literal["synthetic", "supplied_sources_unverified"]


class ContentSummary(GraphRecord):
    explanation_origin: Literal["generated", "fallback"]
    assurance: str
    recorded_cache_hit: bool
    diagnostics: tuple[str, ...]
    generated_item_count: int = Field(ge=0)
    source_copy_item_count: int = Field(ge=0)
    wording_status: Literal["snapshot_not_available", "snapshot_source_fallback", "reviewed_snapshot"]
    wording_origins: tuple[str, ...]
    wording_diagnostics: tuple[str, ...]
    wording_digest: str | None


class SelectionSummary(GraphRecord):
    policy_run_id: str
    prior_version: str
    prior_status: str
    prior_digest: str | None
    selection_mode: Literal["cold_start_baseline", "thompson", "forced"]
    selection_reason: str
    selection_posterior_revision: int = Field(ge=0)
    feasible_count: int = Field(ge=1)
    rejected_count: int = Field(ge=0)
    sampled_candidate_count: int = Field(ge=0)
    feature_names: tuple[str, ...]
    context_encoding: tuple[tuple[str, float], ...]
    score_interpretation: Literal["linear_surrogate_not_probability"] = "linear_surrogate_not_probability"


class DisplaySummary(GraphRecord):
    status: Literal["not_acknowledged", "acknowledged"]
    displayed_action_ids: tuple[str, ...]
    current_action_id: str | None
    navigation_event_count: int = Field(ge=0)
    interpretation: Literal["client_display_acknowledgment_not_reading_or_completion"] = (
        "client_display_acknowledgment_not_reading_or_completion"
    )


class FeedbackSummary(GraphRecord):
    status: Literal["awaiting_display_acknowledgment", "no_accepted_feedback", "accepted"]
    reward: Literal[0, 1] | None
    selection_posterior_revision: int = Field(ge=0)
    revision_immediately_before_update: int | None
    resulting_posterior_revision: int | None
    precision_rank_one_scale: float | None
    centered_reward: float | None
    linear_delta_b: tuple[float, ...] | None
    effect_basis: Literal["derived_from_original_phi_and_recorded_receipt"] = (
        "derived_from_original_phi_and_recorded_receipt"
    )
    historical_post_update_parameters: Literal["not_separately_stored"] = "not_separately_stored"
    diagnostics_are_another_reward: Literal[False] = False


class CurrentTraceStatus(GraphRecord):
    guidance: GuidanceStatus
    user_settings: UserSettings
    shared_policy_run_id: str
    shared_posterior_revision: int = Field(ge=0)
    shared_posterior_fingerprint: str
    accepted_feedback_count: int = Field(ge=0)
    stale_for_display: bool


class PipelineTrace(GraphRecord):
    schema_version: Literal["c4-pipeline-trace-1.0"] = "c4-pipeline-trace-1.0"
    scope: Literal["saved_adaptive_presentation"] = "saved_adaptive_presentation"
    records: RecordedTrace
    input: InputSummary
    structural_features: tuple[TraceFeature, ...]
    content: ContentSummary
    candidates: tuple[TraceCandidate, ...]
    selection: SelectionSummary
    display: DisplaySummary
    learning: FeedbackSummary
    current: CurrentTraceStatus
    evidence_boundaries: tuple[EvidenceBoundary, ...]


class TraceListEntry(GraphRecord):
    exposure_id: str
    presentation_id: str
    decision_id: str
    graph_fingerprint: str
    offered_at: AwareDatetime
    configuration: ScaffoldConfiguration
    selection_posterior_revision: int
    acknowledged: bool
    feedback_accepted: bool


class PipelineTraceIndex(GraphRecord):
    schema_version: Literal["c4-pipeline-trace-index-1.0"] = "c4-pipeline-trace-index-1.0"
    current_guidance: GuidanceStatus
    current_request_routing: Literal["standard", "adaptive"]
    standard_guidance_history: Literal["not_persisted_no_policy_or_learning_record"] = (
        "not_persisted_no_policy_or_learning_record"
    )
    presentations: tuple[TraceListEntry, ...]
    explanation: str
