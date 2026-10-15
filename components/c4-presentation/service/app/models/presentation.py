"""Declarative C4 presentation documents.

Source cards contain deterministic source-preserving text.
Generated explanations are supplementary annotations, never replacements.

This document describes intended rendering. It does not prove that a
browser displayed it, that a citizen read it, or that an action is complete.
"""

from typing import Literal, Self

from pydantic import Field, model_validator

from app.models.explanations import ExplanationResult
from app.models.procedure import ActionId, ServiceId
from app.models.procedure_graph import (
    ActionNode,
    ActionPrerequisiteEdge,
    BranchGroupNode,
    GraphRecord,
    ParallelGroupNode,
    StageDependencyEdge,
    StageNode,
)
from app.models.scaffolds import (
    PresentationItem,
    RelationshipVisual,
    ScaffoldConfiguration,
    VisibilityDeclaration,
)
from app.models.user_context import ExposureId, SessionId


class SourceCard(GraphRecord):
    source: PresentationItem
    title: str
    lines: tuple[str, ...] = Field(min_length=1)
    collapsed: bool = False


class ActionPage(GraphRecord):
    action_id: ActionId
    service_id: ServiceId
    items: tuple[PresentationItem, ...]
    condition_ids: tuple[str, ...]
    branch_group_id: str | None
    branch_option_id: str | None
    prerequisite_cues: tuple[PresentationItem, ...]


class RelationshipDiagram(GraphRecord):
    kind: RelationshipVisual
    stages: tuple[StageNode, ...] = ()
    actions: tuple[ActionNode, ...] = ()
    stage_dependencies: tuple[StageDependencyEdge, ...] = ()
    action_prerequisites: tuple[ActionPrerequisiteEdge, ...] = ()
    branch_groups: tuple[BranchGroupNode, ...] = ()
    parallel_groups: tuple[ParallelGroupNode, ...] = ()

    @model_validator(mode="after")
    def matching_diagram_payload(self) -> Self:
        if self.kind == "NONE":
            if any(
                (
                    self.stages,
                    self.actions,
                    self.stage_dependencies,
                    self.action_prerequisites,
                    self.branch_groups,
                    self.parallel_groups,
                )
            ):
                raise ValueError("NONE must not contain a diagram payload")
        elif self.kind == "DEPENDENCY_MAP":
            if self.branch_groups or self.parallel_groups:
                raise ValueError("dependency diagram contains another diagram type")
            if not (self.stage_dependencies or self.action_prerequisites):
                raise ValueError("dependency diagram requires explicit edges")
        elif self.kind == "BRANCH_MAP":
            if (
                not self.branch_groups
                or self.stage_dependencies
                or self.action_prerequisites
                or self.parallel_groups
            ):
                raise ValueError("branch diagram requires only explicit branch groups")
        elif self.kind == "PARALLEL_MAP":
            if (
                not self.parallel_groups
                or self.stage_dependencies
                or self.action_prerequisites
                or self.branch_groups
            ):
                raise ValueError("parallel diagram requires only explicit parallel groups")
        return self


class Recap(GraphRecord):
    action_ids: tuple[ActionId, ...]
    exposure_ids: tuple[ExposureId, ...]
    meaning: Literal["previously_displayed_not_completed"] = (
        "previously_displayed_not_completed"
    )


class PresentationSpec(GraphRecord):
    schema_version: Literal["c4-presentation-1.0"] = "c4-presentation-1.0"

    presentation_id: str
    session_id: SessionId
    exposure_id: ExposureId
    decision_id: str
    graph_fingerprint: str
    context_revision: int = Field(ge=0)

    configuration: ScaffoldConfiguration
    explanation: ExplanationResult

    cards: tuple[SourceCard, ...]
    global_items: tuple[PresentationItem, ...]
    pages: tuple[ActionPage, ...]
    initial_action_id: ActionId | None

    diagram: RelationshipDiagram
    recap: Recap | None
    visibility: VisibilityDeclaration

    acknowledgment_action_ids: tuple[ActionId, ...]
    navigation_semantics: Literal[
        "browsing_order_not_completion_or_eligibility"
    ] = "browsing_order_not_completion_or_eligibility"
    text_format: Literal["plain_text"] = "plain_text"

    @model_validator(mode="after")
    def document_invariants(self) -> Self:
        result = self.explanation
        if (
            self.exposure_id != result.exposure_id
            or self.decision_id != result.decision_id
            or self.graph_fingerprint != result.graph_fingerprint
            or self.configuration != result.configuration
        ):
            raise ValueError("presentation and explanation attribution differ")

        graph = result.source.graph
        graph_actions = {item.action_id for item in graph.actions}
        page_ids = [page.action_id for page in self.pages]
        if len(page_ids) != len(set(page_ids)) or set(page_ids) != graph_actions:
            raise ValueError("pages must cover every action exactly once")

        card_items = [card.source for card in self.cards]
        if len(card_items) != len(set(card_items)):
            raise ValueError("duplicate source cards")

        inventory = set(result.source.preservation.inventory())
        if set(card_items) != inventory:
            raise ValueError("source cards must cover the complete source inventory")

        visible = tuple(card.source for card in self.cards if not card.collapsed)
        collapsed = tuple(card.source for card in self.cards if card.collapsed)
        if self.visibility != VisibilityDeclaration(
            visible=visible, collapsed=collapsed
        ):
            raise ValueError("visibility must describe actual source cards")

        protected = set(result.source.preservation.always_visible)
        if not protected <= set(visible):
            raise ValueError("mandatory source information must remain visible")

        permitted = {
            PresentationItem(kind="content", identifier=content_id)
            for content_id in result.source.preservation.collapsible_content_ids
        }
        if not set(collapsed) <= permitted:
            raise ValueError("only reviewed supplementary content may collapse")
        if collapsed and not self.configuration.progressive_disclosure:
            raise ValueError("collapsed content requires progressive disclosure")

        if len(self.global_items) != len(set(self.global_items)):
            raise ValueError("duplicate global items")
        locations = set(self.global_items)
        for page in self.pages:
            if len(page.items) != len(set(page.items)):
                raise ValueError("duplicate items within an action page")
            locations.update(page.items)
            if not set(page.prerequisite_cues) <= inventory:
                raise ValueError("unknown prerequisite cue")
            if page.prerequisite_cues and not self.configuration.prerequisite_cue:
                raise ValueError("prerequisite cues are disabled")
        if locations != inventory:
            raise ValueError("layout must locate every source card")

        if self.diagram.kind != self.configuration.relationship_visual:
            raise ValueError("diagram does not match the selected scaffold")

        if self.configuration.previous_context_recap:
            if self.recap is None or not self.recap.action_ids:
                raise ValueError("enabled recap requires acknowledged history")
            if not set(self.recap.action_ids) <= graph_actions:
                raise ValueError("recap references unknown actions")
        elif self.recap is not None:
            raise ValueError("recap must be absent when disabled")

        if self.configuration.presentation_mode == "GUIDED":
            if self.initial_action_id not in graph_actions:
                raise ValueError("guided presentation requires a valid initial action")
            if self.acknowledgment_action_ids != (self.initial_action_id,):
                raise ValueError("guided acknowledgment must describe its focused action")
        else:
            if self.initial_action_id is not None:
                raise ValueError("overview has no focused action")
            if self.acknowledgment_action_ids != tuple(page_ids):
                raise ValueError("overview acknowledgment scope must match its pages")

        return self