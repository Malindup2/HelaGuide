"""Versioned frontend API DTOs; revised policy selection is deliberately unavailable."""
from typing import Literal, Protocol, Any
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from app.guidance.catalogue import Configuration, Constraints, DIMENSIONS
from app.models.procedure_graph import (ProcedureFact, BranchGroupNode, StageNode, StageDependencyEdge,
    ActionPrerequisiteEdge, ParallelGroupNode, GraphCompleteness, EvidenceNode, ConditionNode, FactProvenance)
from app.v2.content import Join, Expression
from app.guidance.content import Phase
from app.models.user_context import FamiliarityReport
from app.models.scaffolds import AccessibilityConstraints

API_SCHEMA = "c4-guidance-api-1.0"

class DTO(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, populate_by_name=True)

class Revision(DTO):
    identity: int = Field(ge=0)
    revised: int = Field(ge=0)

class ContextPatch(DTO):
    request_id: str = Field(min_length=8, max_length=128)
    expected_revision: Revision
    preferences: dict[str,str] | None = None
    locks: dict[str,str] | None = None
    accessibility: Constraints | None = None
    legacy_lock_fingerprint: str | None = None

    @model_validator(mode="after")
    def values(self):
        for mapping in (self.preferences, self.locks):
            if mapping is not None and any(k not in DIMENSIONS or v not in DIMENSIONS[k] for k,v in mapping.items()):
                raise ValueError("unknown revised preference/lock")
        if self.accessibility and self.accessibility.locks:
            raise ValueError("use the separate locks field")
        return self

class RequestContext(DTO):
    familiarity: int | None = Field(default=None,ge=1,le=5,strict=True)
    confidence: int | None = Field(default=None,ge=1,le=5,strict=True)
    preferences: dict[str,str] | None = None
    constraints: Constraints = Field(default_factory=Constraints)

    @model_validator(mode="after")
    def values(self):
        if self.preferences is not None and any(k not in DIMENSIONS or v not in DIMENSIONS[k] for k,v in self.preferences.items()):
            raise ValueError("unknown revised preference")
        return self

class StartGuidance(DTO):
    request_id: str = Field(min_length=8,max_length=128)
    session_id: str = Field(min_length=1,max_length=128)
    procedure_id: str = Field(min_length=1,max_length=128)
    capability_token: str = Field(min_length=32,max_length=128,repr=False)
    language: str = Field(default="en",pattern=r"^[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")
    mode: Literal["standard","personalized"] = "standard"
    expected_context_revision: Revision | None = None
    context: RequestContext = Field(default_factory=RequestContext)

class PreviewGuidance(StartGuidance):
    mode: Literal["research_preview"] = "research_preview"
    configuration: Configuration

class AdjustView(DTO):
    request_id: str = Field(min_length=8,max_length=128)
    parent_view_id: str
    configuration: Configuration

class Interaction(DTO):
    event_id: str = Field(min_length=8,max_length=128)
    view_id: str
    type: Literal["view_displayed","step_visible","navigate","step_open","viewport_changed",
                  "explanation_open","explanation_close","route_focus","map_show","map_hide",
                  "map_expand","map_collapse","recap_open","recap_close","overview_peek","source_open"]
    action_id: str | None = None
    action_ids: list[str] = Field(default_factory=list,max_length=200)
    branch_id: str | None = None
    option_ids: list[str] = Field(default_factory=list,max_length=100)
    source_id: str | None = None
    client_timestamp: AwareDatetime | None = None
    visible_ratio: float | None = Field(default=None,ge=0,le=1)
    dwell_ms: int | None = Field(default=None,ge=0,le=3600000,strict=True)
    instrumentation_version: str | None = Field(default=None,max_length=128)

class Rating(DTO):
    event_id: str = Field(min_length=8,max_length=128)
    view_id: str
    rating: Literal["fits","does_not_fit"]
    reasons: list[Literal["too_much_explanation","not_enough_explanation","navigation_difficult","diagram_confusing","requirements_hard_to_find","other"]] = Field(default_factory=list,max_length=6)

class PolicyEvidence(DTO):
    """Real PP1 producer evidence; previews and standard guidance never populate it."""
    algorithm: Literal["shared_gaussian_lints"]
    action_schema: Literal["c4-scaffolds-v3.0","c4-scaffolds-v3.1"]
    encoder_schema: str
    model_manifest_fingerprint: str
    policy_run_id: str
    posterior_revision: int = Field(ge=0)
    decision_id: str
    training_provenance: Literal["fresh_prior","synthetic","participant","mixed_explicitly_versioned"]

class Selection(DTO):
    kind: Literal["standard","constraint_standard","research_preview","manual_adjustment","shared_gaussian_lints"]
    configuration: Configuration
    action_schema: Literal["c4-scaffolds-v3.0","c4-scaffolds-v3.1"] = "c4-scaffolds-v3.0"
    label: str
    scoring_status: Literal["not_run","executed"] = "not_run"
    policy: PolicyEvidence | None = None
    learning_eligible: bool = False
    explanation: str

    @model_validator(mode="after")
    def honest(self):
        learned = self.kind=="shared_gaussian_lints"
        if learned != (self.policy is not None) or learned != (self.scoring_status=="executed"):
            raise ValueError("policy evidence and executed scoring must match learned selection")
        if not learned and self.learning_eligible:
            raise ValueError("preview/standard/manual cannot be a learned reward observation")
        return self

class RevisedSelector(Protocol):
    """Producer interface for compatible revised policies; PP1 adapter is in guidance.policy."""
    def select(self, *, effective_context, procedure, prepared_content, feasible_configurations) -> Selection: ...

class SourcePassage(DTO):
    content_id: str
    text: str
    evidence_ids: list[str]

class ScopedFact(DTO):
    id: str
    fact_id: str
    fact: ProcedureFact
    scope: Literal["action","route","stage","service"]
    action_id: str | None = None
    stage_id: str | None = None
    service_id: str | None = None
    branch_id: str | None = None
    option_ids: list[str] = Field(default_factory=list)
    condition_ids: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    qualification: str | None = None
    conditions: list[str]
    status: Literal["draft","reviewed","source_fallback"]
    source_context: list[SourcePassage] = Field(default_factory=list)
    applicability_status: Literal["structured_conditions","consult_source_context"] = "consult_source_context"

class CandidateAvailability(DTO):
    id: str
    configuration: Configuration
    feasible: bool
    reasons: list[str]
    disclosable_action_ids: list[str]

class FrozenAvailability(DTO):
    action_schema: Literal["c4-scaffolds-v3.0","c4-scaffolds-v3.1"]
    feasibility_fingerprint: str | None = None
    nominal_count: Literal[96]
    feasible_count: int = Field(ge=0,le=96)
    candidates: list[CandidateAvailability]

class EffectiveContext(DTO):
    schema_version: Literal["c4-effective-guidance-context-1.0"]
    session_id: str
    profile_id: str | None
    personalization_enabled: bool
    service_id: str
    familiarity: int | None
    confidence: int | None
    preferences: dict[str,str]
    constraints: Constraints
    revision: Revision
    sources: dict[str,str]
    legacy: dict[str,Any]
    scoring_use: str

class SourceReview(DTO):
    reviewer: str
    reviewed_at: AwareDatetime
    scope_note: str
    independent_government_validation: Literal[False]

class PreparationMetadata(DTO):
    content_state: Literal["published","source_fallback"]
    preparation_state: Literal["published","draft","queued","pending","processing","failed","stale"]
    job_state: str | None
    job_id: str | None
    error_code: str | None
    generation_enabled: bool
    mode: Literal["demo","dynamic"]
    language: str
    fallback_language: str | None
    content_schema: Literal["c4-guidance-content-3.0","c4-guidance-content-3.1"]
    artifact_id: str | None
    review_kind: str | None
    source_kind: Literal["fictional","bounded_official_source_snapshot"]
    content_origin: str
    source_review: SourceReview | None

class AvailabilityResponse(FrozenAvailability):
    context: EffectiveContext
    preparation: PreparationMetadata

class NavigationEntry(DTO):
    action_id: str
    layer: int | None
    label: str | None
    branch_id: str | None
    option_id: str | None
    route_layer: int | None
    available_for_navigation: bool
    orientation_only: Literal[True]

class Navigation(DTO):
    mode: Literal["overview","guided"]
    entries: list[NavigationEntry]
    active_action_id: str | None
    browsing_action_ids: list[str]
    previous_action_id: str | None
    next_action_id: str | None
    browsing_position: int | None
    browsing_count: int
    unresolved_route_ids: list[str]
    numbering_enabled: bool
    order_semantics: str

class RelationCue(DTO):
    kind: str
    text: str
    evidence_ids: list[str]
    relation_id: str

class ProcessMap(DTO):
    labels: dict[str,str]
    edges: list[ActionPrerequisiteEdge]
    joins: list[Join]
    branches: list[BranchGroupNode]
    parallel: list[ParallelGroupNode]
    parallel_areas: list[list[Expression]]
    stages: list[StageNode]
    text_equivalent: list[str]

class RelationshipAid(DTO):
    mode: Literal["none","inline","map"]
    inline_by_action: dict[str,list[RelationCue]]
    map: ProcessMap | None
    essential_relationships_remain_in_instructions: Literal[True]

class RouteOption(DTO):
    option_id: str
    action_ids: list[str]
    condition_ids: list[str]
    conditions: list[str]
    label: str

class RouteChoice(DTO):
    branch_id: str
    selection: Literal["AND","OR","XOR"]
    evidence_ids: list[str]
    choice_is_not_eligibility_or_completion: Literal[True]
    options: list[RouteOption]

class Requirements(DTO):
    documents: list[ScopedFact]
    fees: list[ScopedFact]
    total: None
    no_total_reason: str
    placement: str

class VisitEvidence(DTO):
    event_id: str
    kind: Literal["navigate","step_open","step_visible"]
    view_id: str
    sequence: int

class RecapItem(DTO):
    action_id: str
    text: str
    evidence: VisitEvidence
    viewed_not_completed: Literal[True]

class RecapState(DTO):
    enabled: bool
    items: list[RecapItem]
    empty_reason: str | None
    label: str

class InteractionState(DTO):
    navigation: Navigation
    route_choices: dict[str,list[str]]
    map_visible: bool
    explanation_open_action_ids: list[str]
    display_acknowledged_view_ids: list[str]
    recap: RecapState
    event_count: int
    completion_tracked: Literal[False]

class Receipt(DTO):
    event_id: str
    sequence: int
    server_timestamp: AwareDatetime
    reward: Literal[0,1] | None
    policy_updated: bool
    learning_eligible: bool

    @model_validator(mode="after")
    def attribution(self):
        if not self.learning_eligible and (self.reward is not None or self.policy_updated):
            raise ValueError("ineligible interactions cannot carry a learning reward or update")
        if self.policy_updated and self.reward is None:
            raise ValueError("an actual posterior update requires an explicit eligible reward")
        return self

class RenderedAction(DTO):
    id: str
    heading: str
    essential: str
    conditions: list[str]
    actor: str | None
    destination: str | None
    facts: list[ScopedFact]
    explanation_visible: str | None
    explanation_hidden: str | None
    recap: None = None  # Only earned recap is returned in interaction.recap.items.
    branch: str | None
    option: str | None
    service_id: str
    agency: str
    condition_ids: list[str]
    source_content_ids: list[str]
    disclosure_available: bool
    wording_status: str
    source_wording: str | None = None
    supplement_role: str | None = None

class RenderedDocument(DTO):
    schema_id: Literal["c4-render-plan-3.0","c4-render-plan-3.1"] = Field(alias="schema")
    content_schema: Literal["c4-guidance-content-3.0","c4-guidance-content-3.1"] = "c4-guidance-content-3.0"
    configuration: Configuration
    synthetic: bool
    source_kind: Literal["fictional","bounded_official_source_snapshot"]
    source_limit: str
    source_graph_fingerprint: str
    relationship_fingerprint: str
    content_fingerprint: str | None
    actions: list[RenderedAction]
    facts: list[ScopedFact]
    branches: list[BranchGroupNode]
    stages: list[StageNode]
    stage_edges: list[StageDependencyEdge]
    edges: list[ActionPrerequisiteEdge]
    parallel: list[ParallelGroupNode]
    joins: list[Join]
    parallel_areas: list[list[Expression]]
    completeness: GraphCompleteness
    sources: list[EvidenceNode]
    conditions: list[ConditionNode]
    provenance: list[FactProvenance]
    map_labels: dict[str,str]
    phases: list[Phase]
    phase_order: list[str]
    supplementary: list[str]
    required_source_notes: list[str]
    relationship_aid: RelationshipAid
    navigation: Navigation
    routes: list[RouteChoice]
    requirements: Requirements

class GuidanceResponse(DTO):
    schema_version: Literal["c4-guidance-api-1.0"] = API_SCHEMA
    journey_id: str
    view_id: str
    parent_view_id: str | None
    session_id: str
    procedure_id: str
    procedure_title: str
    created_at: AwareDatetime
    selection: Selection
    preparation: PreparationMetadata
    effective_context: EffectiveContext
    availability: FrozenAvailability
    document: RenderedDocument
    interaction: InteractionState
    controls: dict[str,bool]


class ProfileContextPatch(DTO):
    request_id: str = Field(min_length=8,max_length=128)
    expected_identity_revision: int = Field(ge=0)
    familiarity: list[FamiliarityReport] | None = None
    confidence: int | None = Field(default=None,ge=1,le=5,strict=True)
    accessibility: AccessibilityConstraints | None = None
