"""Immutable records for C4's shared contextual LinTS policy."""

from typing import Literal

from pydantic import Field, model_validator

from app.models.prior import PriorSpec

from app.models.procedure_features import StructuralFeatures
from app.models.procedure_graph import GraphRecord
from app.models.scaffolds import ScaffoldConfiguration
from app.models.user_context import (
    ContextEvaluation,
    ExposureId,
    PresentationOffer,
)


class PolicyConfig(GraphRecord):
    model_version: Literal["c4-shared-lints-1.0"] = "c4-shared-lints-1.0"

    prior_precision: float = Field(default=1.0, gt=0)
    observation_noise: float = Field(default=1.0, gt=0)
    exploration_scale: float = Field(default=1.0, gt=0)

    cold_start_updates: int = Field(default=1, ge=0)
    seed: int = Field(default=0, ge=0, le=2**63 - 1)

    feedback_mode: Literal["simulation", "participant"] = "simulation"
    prior: PriorSpec | None = None

    @model_validator(mode="after")
    def prior_uses_policy_immediately(self):
        if self.prior is not None and self.cold_start_updates != 0:
            raise ValueError("a configured prior requires cold_start_updates=0")
        return self


class CandidateScore(GraphRecord):
    configuration: ScaffoldConfiguration
    posterior_mean: float
    posterior_std: float = Field(ge=0)
    sampling_std: float = Field(ge=0)
    sampled_score: float | None


class PolicyDecision(GraphRecord):
    decision_id: str
    policy_run_id: str
    decision_sequence: int = Field(ge=1)
    posterior_revision: int = Field(ge=0)

    config: PolicyConfig
    feature_schema_version: Literal["c4-context-action-1.0"] = (
        "c4-context-action-1.0"
    )
    feature_schema_fingerprint: str
    feature_dimension: int = Field(gt=0)
    numerical_versions: tuple[tuple[str, str], ...]

    selection_mode: Literal["cold_start_baseline", "thompson", "forced"]
    selection_reason: str
    draw_seed: int | None

    evaluation: ContextEvaluation
    structural_features: StructuralFeatures

    configuration: ScaffoldConfiguration
    selected_features: tuple[float, ...]
    candidate_scores: tuple[CandidateScore, ...]
    sampled_parameters: tuple[float, ...] | None


class PolicyOffer(GraphRecord):
    """Join the policy decision to the existing Milestone 2 offer."""

    decision: PolicyDecision
    offer: PresentationOffer


class SupportFitFeedback(GraphRecord):
    """Trusted internal input; not an unauthenticated HTTP request model."""

    exposure_id: ExposureId
    rating: Literal["about_right", "need_more", "too_much"]
    origin: Literal["simulation", "participant_report"]


class UpdateReceipt(GraphRecord):
    feedback: SupportFitFeedback
    policy_run_id: str
    decision_id: str
    acknowledgment_event_id: str

    reward: Literal[0, 1]
    procedure_synthetic: bool
    selection_posterior_revision: int = Field(ge=0)
    resulting_posterior_revision: int = Field(ge=1)
