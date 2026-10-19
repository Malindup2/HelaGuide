"""Persistent local demonstration profiles.

These records are not user authentication or verified identity.

A profile owns one durable context session. Its personalization revision is
separate from the existing session/context revision and policy revision.
"""

from typing import Annotated, Literal, Self

from pydantic import (
    AwareDatetime,
    Field,
    field_validator,
    model_validator,
)

from app.models.procedure_graph import GraphRecord
from app.models.scaffolds import (
    AccessibilityConstraints,
    PresentationLocks,
)
from app.models.user_context import (
    EventId,
    FamiliarityReport,
    FivePointRating,
    GuestSession,
    SessionId,
    SoftPreferences,
)


ProfileId = Annotated[
    str,
    Field(pattern=r"^profile:[0-9a-f]{32}$"),
]


class InitialProfileContext(GraphRecord):
    """Optional self-reported answers collected during profile creation."""

    familiarity: list[FamiliarityReport] = Field(default_factory=list)
    navigation_capability: FivePointRating | None = None
    preferences: SoftPreferences = Field(default_factory=SoftPreferences)
    locks: PresentationLocks = Field(default_factory=PresentationLocks)
    accessibility: AccessibilityConstraints = Field(
        default_factory=AccessibilityConstraints
    )

    @model_validator(mode="after")
    def unique_services(self) -> Self:
        identifiers = [item.service_id for item in self.familiarity]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("familiarity service IDs must be unique")
        return self


class CreateDemoProfileRequest(GraphRecord):
    """The client keeps profile_id unchanged when retrying creation."""

    profile_id: ProfileId
    display_name: str = Field(min_length=1, max_length=60)
    personalization_enabled: bool = False
    initial_context: InitialProfileContext = Field(
        default_factory=InitialProfileContext
    )

    @field_validator("display_name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("display_name cannot be blank")
        return value


class PersonalizationRequest(GraphRecord):
    """One explicit setting operation, identified for safe retries."""

    request_id: EventId
    expected_revision: int = Field(ge=0)
    enabled: bool


class PersonalizationChange(GraphRecord):
    request_id: EventId
    expected_revision: int = Field(ge=0)
    enabled: bool
    occurred_at: AwareDatetime


class DemoProfile(GraphRecord):
    schema_version: Literal["c4-demo-profile-1.0"] = "c4-demo-profile-1.0"

    profile_id: ProfileId
    display_name: str = Field(min_length=1, max_length=60)
    session_id: SessionId

    created_at: AwareDatetime
    updated_at: AwareDatetime
    revision: int = Field(ge=0)

    initial_personalization_enabled: bool
    personalization_enabled: bool
    creation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    personalization_changes: tuple[PersonalizationChange, ...] = ()

    @model_validator(mode="after")
    def consistent_history(self) -> Self:
        if self.display_name != self.display_name.strip():
            raise ValueError("profile name must be normalized")

        if self.updated_at < self.created_at:
            raise ValueError("profile timestamps are out of order")

        if self.revision != len(self.personalization_changes):
            raise ValueError("profile revision differs from setting history")

        request_ids = set()
        previous_time = self.created_at
        enabled = self.initial_personalization_enabled

        for index, event in enumerate(self.personalization_changes):
            if event.request_id in request_ids:
                raise ValueError("duplicate personalization request ID")
            if event.expected_revision != index:
                raise ValueError("personalization revisions are not contiguous")
            if event.occurred_at < previous_time:
                raise ValueError("personalization timestamps are out of order")

            request_ids.add(event.request_id)
            previous_time = event.occurred_at
            enabled = event.enabled

        if self.personalization_enabled != enabled:
            raise ValueError("personalization state differs from its history")
        if self.updated_at != previous_time:
            raise ValueError("profile update time differs from its history")

        return self


class DemoProfileResponse(GraphRecord):
    profile: DemoProfile
    session: GuestSession

    @model_validator(mode="after")
    def matching_session(self) -> Self:
        if self.profile.session_id != self.session.session_id:
            raise ValueError("profile and context session differ")
        return self