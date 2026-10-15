"""Optional support-fit diagnostics and explicitly applied soft preferences."""

from typing import Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from app.models.procedure_graph import GraphRecord
from app.models.user_context import (
    EventId,
    ExposureId,
    GuestSession,
    SessionId,
)


CorrectionCode = Literal[
    "prefer_overview",
    "prefer_guided",
    "expand_supplementary",
    "collapse_supplementary",
    "show_recap",
    "hide_recap",
    "show_branch_map",
    "show_dependency_map",
    "show_parallel_map",
    "hide_diagram",
    "show_prerequisite_cues",
    "hide_prerequisite_cues",
]

# Desired scaffold values. These are not numerical rewards.
CORRECTION_CHOICES = {
    "prefer_overview": (
        "presentation_mode",
        "OVERVIEW",
        "A full overview",
    ),
    "prefer_guided": (
        "presentation_mode",
        "GUIDED",
        "Step-by-step guidance",
    ),
    "expand_supplementary": (
        "progressive_disclosure",
        False,
        "Show supplementary explanations immediately",
    ),
    "collapse_supplementary": (
        "progressive_disclosure",
        True,
        "Keep supplementary explanations collapsed initially",
    ),
    "show_recap": (
        "previous_context_recap",
        True,
        "A recap of previously viewed guidance",
    ),
    "hide_recap": (
        "previous_context_recap",
        False,
        "No previous-context recap",
    ),
    "show_branch_map": (
        "relationship_visual",
        "BRANCH_MAP",
        "An alternatives diagram",
    ),
    "show_dependency_map": (
        "relationship_visual",
        "DEPENDENCY_MAP",
        "A dependency diagram",
    ),
    "show_parallel_map": (
        "relationship_visual",
        "PARALLEL_MAP",
        "A parallel-actions diagram",
    ),
    "hide_diagram": (
        "relationship_visual",
        "NONE",
        "No relationship diagram",
    ),
    "show_prerequisite_cues": (
        "prerequisite_cue",
        True,
        "Prerequisite reminders",
    ),
    "hide_prerequisite_cues": (
        "prerequisite_cue",
        False,
        "Fewer additional prerequisite reminders",
    ),
}


def preference_values(reasons) -> dict[str, str | bool]:
    """Convert correction codes to unambiguous scaffold preferences."""
    values = {}
    for code in reasons:
        dimension, value, _ = CORRECTION_CHOICES[code]
        if dimension in values:
            raise ValueError(
                "choose only one correction per scaffold dimension"
            )
        values[dimension] = value
    return values


class CorrectionRequest(GraphRecord):
    presentation_id: str = Field(min_length=1)
    configuration_id: str = Field(min_length=1)
    decision_id: str = Field(min_length=1)
    reasons: list[CorrectionCode] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def consistent_reasons(self) -> Self:
        preference_values(self.reasons)
        return self


class ApplyCorrectionRequest(GraphRecord):
    expected_revision: int = Field(ge=0)


class PreferenceApplication(GraphRecord):
    expected_revision: int = Field(ge=0)
    applied_at: AwareDatetime
    before: GuestSession
    after: GuestSession
    preference_event_id: EventId | None


class CorrectionRecord(GraphRecord):
    schema_version: Literal["c4-correction-1.0"] = "c4-correction-1.0"

    session_id: SessionId
    exposure_id: ExposureId
    presentation_id: str
    configuration_id: str
    decision_id: str
    graph_fingerprint: str

    rating: Literal["need_more", "too_much"]
    origin: Literal["simulation", "participant_report"]
    acknowledgment_event_id: EventId
    feedback_posterior_revision: int = Field(ge=1)

    recorded_at: AwareDatetime
    reasons: tuple[CorrectionCode, ...] = Field(
        min_length=1,
        max_length=5,
    )
    application: PreferenceApplication | None = None

    @model_validator(mode="after")
    def canonical_reasons(self) -> Self:
        preference_values(self.reasons)
        if self.reasons != tuple(sorted(self.reasons)):
            raise ValueError("stored correction reasons must be sorted")
        return self


class CorrectionOption(GraphRecord):
    code: CorrectionCode
    label: str
    dimension: str
    value: str | bool
    selected_in_original: bool
    available_for_future: bool
    unavailable_reason: str | None


class CorrectionOptions(GraphRecord):
    session_revision: int
    feedback_eligible: bool
    choices: tuple[CorrectionOption, ...]