"""Frozen runtime 1.1 records used for explicit migration.

Do not add correction fields or future event types to these records.
Class names intentionally match the previous persisted schema.
"""

from typing import Literal

from pydantic import AwareDatetime, Field

from app.models.policy import PolicyConfig, PolicyOffer, UpdateReceipt
from app.models.presentation import PresentationSpec
from app.models.procedure_graph import GraphRecord
from app.models.user_context import (
    ActionDisplay,
    GuestSession,
    PreferenceChange,
    PresentationExposure,
    PresentationOffer,
)


ContextEvent = PreferenceChange | PresentationExposure | ActionDisplay


class SessionState(GraphRecord):
    session: GuestSession
    events: tuple[ContextEvent, ...]
    offers: tuple[PresentationOffer, ...]


class PolicyState(GraphRecord):
    config: PolicyConfig
    policy_run_id: str
    feature_schema_version: str
    feature_schema_fingerprint: str
    feature_dimension: int = Field(gt=0)
    decision_sequence: int = Field(ge=0)
    posterior_revision: int = Field(ge=0)
    posterior_fingerprint: str
    rng_state_json: str
    offers: tuple[PolicyOffer, ...]
    receipts: tuple[UpdateReceipt, ...]


class AcceptedFeedback(GraphRecord):
    accepted_at: AwareDatetime
    receipt: UpdateReceipt


class RuntimeState(GraphRecord):
    format_version: Literal["c4-runtime-state-1.1"] = (
        "c4-runtime-state-1.1"
    )
    sessions: tuple[SessionState, ...]
    policy: PolicyState
    presentations: tuple[PresentationSpec, ...]
    feedback: tuple[AcceptedFeedback, ...]