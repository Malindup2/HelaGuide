"""Immutable canonical records for C4's internal procedure graph.

Create validated graph snapshots through build_procedure_graph().
These records describe presentation structure, not C2's knowledge graph.
"""

from typing import Annotated, Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from app.models.procedure import (
    ActionId,
    BranchId,
    Completeness,
    ConditionId,
    ContentId,
    EvidenceId,
    FactId,
    OptionId,
    ParallelId,
    PrerequisiteId,
    ServiceId,
    Text,
)


class GraphRecord(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
    )


class GraphCompleteness(GraphRecord):
    service_dependencies: Completeness
    actions: Completeness
    content: Completeness
    conditions: Completeness
    branch_groups: Completeness
    prerequisites: Completeness
    parallel_groups: Completeness


class FeeFact(GraphRecord):
    kind: Literal["fee"] = "fee"
    fact_id: FactId
    value: float = Field(ge=0)
    currency: str


class DocumentFact(GraphRecord):
    kind: Literal["document"] = "document"
    fact_id: FactId
    name: str


ProcedureFact = Annotated[
    FeeFact | DocumentFact,
    Field(discriminator="kind"),
]


class FactProvenance(GraphRecord):
    fact_id: FactId
    source_url: str
    retrieved_at: AwareDatetime


class ContentNode(GraphRecord):
    content_id: ContentId
    role: Literal["required", "supplementary"]
    text: Text
    evidence_ids: tuple[EvidenceId, ...]
    fact_ids: tuple[FactId, ...]


class EvidenceNode(GraphRecord):
    evidence_id: EvidenceId
    kind: Literal["synthetic_authored", "source_passage"]
    source_url: Text
    text: Text
    retrieved_at: AwareDatetime | None


class ConditionNode(GraphRecord):
    condition_id: ConditionId
    text: Text
    evidence_ids: tuple[EvidenceId, ...]


class StageNode(GraphRecord):
    service_id: ServiceId
    display_order: int = Field(ge=1)
    name: str
    agency: str
    fee_fact_id: FactId
    document_fact_ids: tuple[FactId, ...]


class ActionApplicability(GraphRecord):
    """Known conjunctive conditions and explicit selection membership.

    An empty condition tuple means no supplied conditions.
    Interpret it together with graph completeness.
    """

    condition_ids: tuple[ConditionId, ...]
    branch_group_id: BranchId | None
    branch_option_id: OptionId | None

    @model_validator(mode="after")
    def membership_is_paired(self) -> Self:
        if (self.branch_group_id is None) != (
            self.branch_option_id is None
        ):
            raise ValueError(
                "branch_group_id and branch_option_id must both "
                "be present or both be absent"
            )
        return self


class ActionNode(GraphRecord):
    action_id: ActionId
    service_id: ServiceId
    required_content_ids: tuple[ContentId, ...]
    supplementary_content_ids: tuple[ContentId, ...]
    direct_condition_ids: tuple[ConditionId, ...]
    applicability: ActionApplicability


class StageDependencyEdge(GraphRecord):
    edge_id: Text
    kind: Literal["stage_dependency"] = "stage_dependency"
    source_id: ServiceId
    target_id: ServiceId


class ActionPrerequisiteEdge(GraphRecord):
    edge_id: PrerequisiteId
    kind: Literal["requires_completion"] = "requires_completion"
    source_id: ActionId
    target_id: ActionId
    evidence_ids: tuple[EvidenceId, ...]


class BranchOptionNode(GraphRecord):
    option_id: OptionId
    action_ids: tuple[ActionId, ...]
    condition_ids: tuple[ConditionId, ...]


class BranchGroupNode(GraphRecord):
    group_id: BranchId
    service_id: ServiceId
    selection: Literal["AND", "OR", "XOR"]
    options: tuple[BranchOptionNode, ...]
    evidence_ids: tuple[EvidenceId, ...]


class ParallelGroupNode(GraphRecord):
    group_id: ParallelId
    service_id: ServiceId
    action_ids: tuple[ActionId, ...]
    evidence_ids: tuple[EvidenceId, ...]


class CanonicalProcedureGraph(GraphRecord):
    graph_schema_version: Literal["1.0"] = "1.0"
    enrichment_schema_version: Literal["1.0"]

    plan_id: str
    requested_service_id: ServiceId
    generated_at: AwareDatetime
    synthetic: bool
    disclaimer: Text

    stages: tuple[StageNode, ...] = Field(min_length=1)
    actions: tuple[ActionNode, ...]
    stage_dependencies: tuple[StageDependencyEdge, ...]
    action_prerequisites: tuple[ActionPrerequisiteEdge, ...]

    conditions: tuple[ConditionNode, ...]
    branch_groups: tuple[BranchGroupNode, ...]
    parallel_groups: tuple[ParallelGroupNode, ...]

    content: tuple[ContentNode, ...]
    evidence: tuple[EvidenceNode, ...]
    facts: tuple[ProcedureFact, ...]
    provenance: tuple[FactProvenance, ...]
    completeness: GraphCompleteness

    @model_validator(mode="after")
    def record_identifiers_are_unique(self) -> Self:
        tables = (
            ("stages", "service_id"),
            ("actions", "action_id"),
            ("stage_dependencies", "edge_id"),
            ("action_prerequisites", "edge_id"),
            ("conditions", "condition_id"),
            ("branch_groups", "group_id"),
            ("parallel_groups", "group_id"),
            ("content", "content_id"),
            ("evidence", "evidence_id"),
            ("facts", "fact_id"),
            ("provenance", "fact_id"),
        )
        for table_name, id_field in tables:
            seen = set()
            for item in getattr(self, table_name):
                identifier = getattr(item, id_field)
                if identifier in seen:
                    raise ValueError(
                        f"{table_name}: duplicate identifier '{identifier}'"
                    )
                seen.add(identifier)

        option_ids = [
            option.option_id
            for group in self.branch_groups
            for option in group.options
        ]
        if len(option_ids) != len(set(option_ids)):
            raise ValueError("branch option IDs must be globally unique")

        return self