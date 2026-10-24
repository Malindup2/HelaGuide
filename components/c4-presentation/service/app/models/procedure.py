"""C4 procedure input vocabulary.

Construct research inputs through app.procedures.procedure_input so both
typed and semantic validation are performed.
"""

from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from helaguide_common.contracts import FACT_ID, SERVICE_ID, Plan


Text = Annotated[str, Field(min_length=1, pattern=r"\S")]
ServiceId = Annotated[str, Field(pattern=SERVICE_ID)]
FactId = Annotated[str, Field(pattern=FACT_ID)]
ActionId = Annotated[str, Field(pattern=r"^action:[a-z0-9_]+$")]
ContentId = Annotated[str, Field(pattern=r"^content:[a-z0-9_]+$")]
EvidenceId = Annotated[str, Field(pattern=r"^evidence:[a-z0-9_]+$")]
ConditionId = Annotated[str, Field(pattern=r"^condition:[a-z0-9_]+$")]
PrerequisiteId = Annotated[
    str, Field(pattern=r"^prerequisite:[a-z0-9_]+$")
]
BranchId = Annotated[str, Field(pattern=r"^branch:[a-z0-9_]+$")]
OptionId = Annotated[str, Field(pattern=r"^option:[a-z0-9_]+$")]
ParallelId = Annotated[str, Field(pattern=r"^parallel:[a-z0-9_]+$")]

Completeness = Literal["complete", "partial", "unknown"]


class InputModel(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        allow_inf_nan=False,
    )


class Evidence(InputModel):
    evidence_id: EvidenceId
    kind: Literal["synthetic_authored", "source_passage"]
    source_url: Text
    text: Text
    retrieved_at: AwareDatetime | None


class Content(InputModel):
    content_id: ContentId
    role: Literal["required", "supplementary"]
    text: Text
    evidence_ids: list[EvidenceId] = Field(min_length=1)
    fact_ids: list[FactId]


class Action(InputModel):
    action_id: ActionId
    service_id: ServiceId
    required_content_ids: list[ContentId] = Field(min_length=1)
    supplementary_content_ids: list[ContentId]
    condition_ids: list[ConditionId]


class Condition(InputModel):
    condition_id: ConditionId
    text: Text
    evidence_ids: list[EvidenceId] = Field(min_length=1)


class Prerequisite(InputModel):
    prerequisite_id: PrerequisiteId
    kind: Literal["requires_completion"]
    required_action_id: ActionId
    dependent_action_id: ActionId
    evidence_ids: list[EvidenceId] = Field(min_length=1)


class BranchOption(InputModel):
    option_id: OptionId
    action_ids: list[ActionId] = Field(min_length=1)
    condition_ids: list[ConditionId]


class BranchGroup(InputModel):
    group_id: BranchId
    service_id: ServiceId
    selection: Literal["AND", "OR", "XOR"]
    options: list[BranchOption] = Field(min_length=2)
    evidence_ids: list[EvidenceId] = Field(min_length=1)


class ParallelGroup(InputModel):
    group_id: ParallelId
    service_id: ServiceId
    action_ids: list[ActionId] = Field(min_length=2)
    evidence_ids: list[EvidenceId] = Field(min_length=1)


class StructuralCompleteness(InputModel):
    service_dependencies: Completeness
    actions: Completeness
    content: Completeness
    conditions: Completeness
    branch_groups: Completeness
    prerequisites: Completeness
    parallel_groups: Completeness


class ProcedureEnrichment(InputModel):
    schema_version: Literal["1.0"]
    plan_id: Text
    base_generated_at: AwareDatetime
    synthetic: bool
    disclaimer: Text
    actions: list[Action]
    content: list[Content]
    evidence: list[Evidence]
    conditions: list[Condition]
    prerequisites: list[Prerequisite]
    branch_groups: list[BranchGroup]
    parallel_groups: list[ParallelGroup]
    completeness: StructuralCompleteness


class ProcedureInput(InputModel):
    """Validated on entry through the public input-processing functions."""

    plan: Plan
    enrichment: ProcedureEnrichment