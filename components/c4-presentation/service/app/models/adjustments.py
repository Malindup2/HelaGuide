"""User-controlled view lineage is separate from sampled policy decisions."""
from typing import Literal
from pydantic import AwareDatetime, Field
from app.models.procedure_graph import GraphRecord
from app.models.presentation import PresentationSpec
from app.models.scaffolds import ScaffoldConfiguration
from app.models.user_context import EventId


class ViewRecord(GraphRecord):
    expected_revision: int = Field(ge=0)
    view_id: str
    parent_view_id: str
    operation: Literal["adjust", "undo"]
    configuration: ScaffoldConfiguration
    focus_action_id: str
    created_at: AwareDatetime
    undo_target_id: str | None = None


class ViewDisplay(GraphRecord):
    expected_revision: int = Field(ge=0)
    event_id: EventId
    view_id: str
    action_id: str
    recorded_at: AwareDatetime


class ViewRating(GraphRecord):
    expected_revision: int = Field(ge=0)
    event_id: EventId
    view_id: str
    rating: Literal["about_right", "need_more", "too_much"]
    recorded_at: AwareDatetime
    origin: Literal["simulation", "participant_report"]
    learning_eligible: Literal[False] = False


class ViewLedger(GraphRecord):
    schema_version: Literal["c4-adjustments-1.0"] = "c4-adjustments-1.0"
    session_id: str
    exposure_id: str
    presentation_id: str
    policy_run_id: str
    revision: int = Field(default=0, ge=0)
    views: tuple[ViewRecord, ...] = ()
    displays: tuple[ViewDisplay, ...] = ()
    ratings: tuple[ViewRating, ...] = ()


class ViewRequest(GraphRecord):
    request_id: EventId
    expected_revision: int = Field(ge=0)
    parent_view_id: str
    operation: Literal["adjust", "undo"]
    configuration: ScaffoldConfiguration | None = None
    focus_action_id: str


class ViewDisplayRequest(GraphRecord):
    event_id: EventId
    expected_revision: int = Field(ge=0)
    view_id: str
    action_id: str


class ViewRatingRequest(GraphRecord):
    event_id: EventId
    expected_revision: int = Field(ge=0)
    view_id: str
    rating: Literal["about_right", "need_more", "too_much"]


class ViewPreferenceRequest(GraphRecord):
    request_id: EventId
    view_id: str
    expected_session_revision: int = Field(ge=0)


class AdjustmentState(GraphRecord):
    schema_version: Literal["c4-adjustment-state-1.0"] = "c4-adjustment-state-1.0"
    ledger: ViewLedger
    active_view_id: str
    original_view: bool
    spec: PresentationSpec
    focus_action_id: str
    displayed_action_ids: tuple[str, ...]
    feasible_configurations: tuple[ScaffoldConfiguration, ...]
    can_undo: bool
    stale_for_display: bool
    learning_eligible: bool
