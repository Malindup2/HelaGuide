"""Versioned user/session context for the independent C4 prototype."""

from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from app.models.procedure import ActionId, ServiceId
from app.models.procedure_graph import GraphRecord
from app.models.scaffolds import (
    AccessibilityConstraints,
    FeasibilityContext,
    FeasibilityResult,
    Fingerprint,
    PresentationLocks,
    PriorExposure,
    ScaffoldConfiguration,
)


FivePointRating = Annotated[int, Field(strict=True, ge=1, le=5)]
SessionId = Annotated[str, Field(pattern=r"^guest:[0-9a-f]{32}$")]
ExposureId = Annotated[str, Field(pattern=r"^exposure:[0-9a-f]{32}$")]
EventId = Annotated[str, Field(pattern=r"^event:[0-9a-f]{32}$")]

RECAP_WINDOW = 5

PREFERENCE_CHOICES = (
    ("presentation_mode", ("OVERVIEW", "GUIDED")),
    ("progressive_disclosure", (False, True)),
    ("previous_context_recap", (False, True)),
    (
        "relationship_visual",
        ("NONE", "BRANCH_MAP", "DEPENDENCY_MAP", "PARALLEL_MAP"),
    ),
    ("prerequisite_cue", (False, True)),
)


class SoftPreferences(PresentationLocks):
    """Optional preferences using the existing scaffold vocabulary.

    These fields never become hard constraints unless the user separately
    sets the corresponding PresentationLocks field.
    """


class FamiliarityReport(GraphRecord):
    service_id: ServiceId
    score: FivePointRating | None
    source: Literal["self_reported"] = "self_reported"


class UserSettings(GraphRecord):
    schema_version: Literal["1.0"] = "1.0"
    familiarity: tuple[FamiliarityReport, ...] = ()
    navigation_capability: FivePointRating | None = None
    navigation_source: Literal["self_reported"] = "self_reported"

    preferences: SoftPreferences = Field(default_factory=SoftPreferences)
    locks: PresentationLocks = Field(default_factory=PresentationLocks)
    accessibility: AccessibilityConstraints = Field(
        default_factory=AccessibilityConstraints
    )

    @model_validator(mode="after")
    def unique_familiarity_scopes(self) -> Self:
        identifiers = [item.service_id for item in self.familiarity]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("familiarity service IDs must be unique")
        return self

    def familiarity_for(self, service_id: str) -> int | None:
        for report in self.familiarity:
            if report.service_id == service_id:
                return report.score
        return None


class ContextUpdate(GraphRecord):
    """A partial update.

    Omitted fields are unchanged.
    navigation_capability=None explicitly restores unknown.
    Within preferences/locks, an explicit None clears that dimension.
    Within accessibility, omitted dimensions remain unchanged.

    Object groups cannot be null: use an explicit object describing the
    intended changes.
    """

    familiarity: FamiliarityReport | None = None
    navigation_capability: FivePointRating | None = None
    preferences: SoftPreferences | None = None
    locks: PresentationLocks | None = None
    accessibility: AccessibilityConstraints | None = None

    @model_validator(mode="after")
    def object_updates_are_explicit(self) -> Self:
        for name in ("familiarity", "preferences", "locks", "accessibility"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} must be an object when supplied")
        return self


class GuestSession(GraphRecord):
    schema_version: Literal["1.0"] = "1.0"
    session_id: SessionId
    created_at: AwareDatetime
    updated_at: AwareDatetime
    revision: int = Field(ge=0)
    settings: UserSettings


class ExposureSummary(GraphRecord):
    exposure_id: ExposureId
    sequence: int = Field(ge=1)
    acknowledged_at: AwareDatetime
    configuration_id: str
    displayed_action_ids: tuple[ActionId, ...]


class ContextSnapshot(GraphRecord):
    schema_version: Literal["1.0"] = "1.0"
    encoding_version: Literal["c4-user-context-1.0"] = "c4-user-context-1.0"

    session_id: SessionId
    revision: int = Field(ge=0)
    captured_at: AwareDatetime
    graph_fingerprint: Fingerprint
    requested_service_id: ServiceId
    settings: UserSettings

    matching_exposure_count: int = Field(ge=0)
    preference_change_count: int = Field(ge=0)
    recent_exposures: tuple[ExposureSummary, ...]
    recap_action_ids: tuple[ActionId, ...]

    def feasibility_context(self) -> FeasibilityContext:
        return FeasibilityContext(
            session_id=self.session_id,
            locks=self.settings.locks,
            accessibility=self.settings.accessibility,
            history=tuple(
                PriorExposure(
                    session_id=self.session_id,
                    graph_fingerprint=self.graph_fingerprint,
                    action_ids=event.displayed_action_ids,
                )
                for event in self.recent_exposures
                if event.displayed_action_ids
            ),
        )

    def encoding(self) -> tuple[tuple[str, float], ...]:
        """Fixed-order user-context inputs, without identifiers or time.

        Ratings use one-hot categories, avoiding an assumed equal-distance
        relationship between the five self-reported levels.
        """
        values: list[tuple[str, float]] = []

        ratings = (
            (
                "familiarity",
                self.settings.familiarity_for(self.requested_service_id),
            ),
            ("navigation_capability", self.settings.navigation_capability),
        )
        for name, rating in ratings:
            for level in range(1, 6):
                values.append((f"{name}.level_{level}", float(rating == level)))
            values.append((f"{name}.unknown", float(rating is None)))

        for prefix, settings in (
            ("preference", self.settings.preferences),
            ("lock", self.settings.locks),
        ):
            for dimension, choices in PREFERENCE_CHOICES:
                current = getattr(settings, dimension)
                for choice in choices:
                    if isinstance(choice, bool):
                        label = "on" if choice else "off"
                    else:
                        label = choice.lower()
                    values.append(
                        (
                            f"{prefix}.{dimension}.{label}",
                            float(current is not None and current == choice),
                        )
                    )
                values.append(
                    (
                        f"{prefix}.{dimension}.unset",
                        float(current is None),
                    )
                )

        for name in (
            "allow_relationship_visuals",
            "allow_collapsed_content",
            "allow_guided_navigation",
        ):
            values.append(
                (
                    f"accessibility.{name}",
                    float(getattr(self.settings.accessibility, name)),
                )
            )

        values.extend(
            (
                ("history.recap_available", float(bool(self.recap_action_ids))),
                (
                    "history.exposures_scaled",
                    self.matching_exposure_count
                    / (self.matching_exposure_count + 5.0),
                ),
                (
                    "history.recap_actions_scaled",
                    len(self.recap_action_ids)
                    / (len(self.recap_action_ids) + 10.0),
                ),
                (
                    "history.preference_changes_scaled",
                    self.preference_change_count
                    / (self.preference_change_count + 5.0),
                ),
            )
        )
        return tuple(values)


class ContextEvaluation(GraphRecord):
    snapshot: ContextSnapshot
    feasibility: FeasibilityResult


class PresentationOffer(GraphRecord):
    """A registered intended presentation; this is not an exposure event."""

    schema_version: Literal["1.0"] = "1.0"
    exposure_id: ExposureId
    session_id: SessionId
    offered_at: AwareDatetime
    graph_fingerprint: Fingerprint

    configuration: ScaffoldConfiguration
    intended_action_ids: tuple[ActionId, ...]
    context_snapshot: ContextSnapshot

    feasible_configuration_ids: tuple[str, ...]
    feasibility_rules_version: str
    structural_measurement_version: str
    structural_encoding: tuple[tuple[str, float], ...]


class PreferenceChange(GraphRecord):
    schema_version: Literal["1.0"] = "1.0"
    kind: Literal["preference_change"] = "preference_change"
    event_id: EventId
    session_id: SessionId
    sequence: int = Field(ge=1)
    occurred_at: AwareDatetime
    changed_fields: tuple[str, ...]
    before: UserSettings
    after: UserSettings


class PresentationExposure(GraphRecord):
    schema_version: Literal["1.0"] = "1.0"
    kind: Literal["presentation_exposure"] = "presentation_exposure"
    event_id: EventId
    session_id: SessionId
    sequence: int = Field(ge=1)
    acknowledged_at: AwareDatetime
    displayed_action_ids: tuple[ActionId, ...]
    offer: PresentationOffer


class ActionDisplay(GraphRecord):
    """A client acknowledgment that another action was displayed.

    event_id is generated by the client once per display occurrence.
    Repeating a request with that ID is a retry, not another visit.
    sequence and occurred_at describe server acceptance order.
    """

    schema_version: Literal["1.0"] = "1.0"
    kind: Literal["action_display"] = "action_display"
    event_id: EventId
    session_id: SessionId
    sequence: int = Field(ge=1)
    occurred_at: AwareDatetime

    exposure_id: ExposureId
    presentation_id: str = Field(min_length=1)
    configuration_id: str = Field(min_length=1)
    action_id: ActionId
    is_revisit: bool


ContextEvent = PreferenceChange | PresentationExposure | ActionDisplay