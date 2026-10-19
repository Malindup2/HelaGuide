"""Frontend guidance contracts with explicit standard/adaptive attribution."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from app.models.explanations import StandardExplanationResult
from app.models.presentation import ActionPage, PresentationSpec, SourceCard
from app.models.procedure import ActionId
from app.models.procedure_graph import GraphRecord
from app.models.scaffolds import PresentationItem, VisibilityDeclaration
from app.models.user_context import SessionId


class GuidanceRequest(GraphRecord):
    procedure_id: str = Field(min_length=1)
    expected_revision: int = Field(ge=0)
    expected_profile_revision: int | None = Field(default=None, ge=0)
    focus_action_id: ActionId | None = None
    standard_writing_style: Literal["plain", "extra_plain", "concise"] = "plain"


class StandardGuidance(GraphRecord):
    schema_version: Literal["c4-standard-guidance-1.0"] = (
        "c4-standard-guidance-1.0"
    )
    standard_id: str
    graph_fingerprint: str
    presentation_mode: Literal["OVERVIEW"] = "OVERVIEW"
    personalization_applied: Literal[False] = False
    exposure_acknowledgment_required: Literal[False] = False
    learning_eligible: Literal[False] = False
    writing_style: Literal["plain", "extra_plain", "concise"]
    explanation: StandardExplanationResult
    cards: tuple[SourceCard, ...]
    global_items: tuple[PresentationItem, ...]
    pages: tuple[ActionPage, ...]
    visibility: VisibilityDeclaration
    navigation_semantics: Literal[
        "browsing_order_not_completion_or_eligibility"
    ] = "browsing_order_not_completion_or_eligibility"

    @model_validator(mode="after")
    def source_coverage(self) -> Self:
        source = self.explanation.source
        if self.graph_fingerprint != self.explanation.graph_fingerprint:
            raise ValueError("standard guidance graph attribution differs")
        card_items = [card.source for card in self.cards]
        inventory = set(source.preservation.inventory())
        if len(card_items) != len(set(card_items)) or set(card_items) != inventory:
            raise ValueError("standard guidance must retain every source item")
        if any(card.collapsed for card in self.cards):
            raise ValueError("standard guidance never collapses source cards")
        if self.visibility != VisibilityDeclaration(visible=tuple(card_items)):
            raise ValueError("standard visibility differs from source cards")
        page_ids = [page.action_id for page in self.pages]
        if (
            len(page_ids) != len(set(page_ids))
            or set(page_ids) != {action.action_id for action in source.graph.actions}
        ):
            raise ValueError("standard pages must cover all actions")
        located = set(self.global_items)
        for page in self.pages:
            located.update(page.items)
            if page.prerequisite_cues:
                raise ValueError("standard guidance has no adaptive cue scaffold")
        if located != inventory:
            raise ValueError("standard layout must locate every source item")
        return self


class GuidanceStatus(GraphRecord):
    session_id: SessionId
    session_revision: int
    profile_id: str | None
    profile_revision: int | None
    personalization_enabled: bool


class StandardGuidanceResponse(GuidanceStatus):
    mode: Literal["standard"] = "standard"
    guidance: StandardGuidance


class AdaptiveGuidanceResponse(GuidanceStatus):
    mode: Literal["adaptive"] = "adaptive"
    spec: PresentationSpec
    stale_for_display: bool


GuidanceResponse = Annotated[
    StandardGuidanceResponse | AdaptiveGuidanceResponse,
    Field(discriminator="mode"),
]
