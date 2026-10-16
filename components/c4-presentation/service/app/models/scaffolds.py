"""C4 scaffold catalogue and hard-feasibility vocabulary.

These records describe configuration choices and preservation contracts.
They do not implement rendering, session storage or policy learning.
"""

from typing import Annotated, Literal

from pydantic import Field, computed_field

from app.models.procedure import ActionId, ContentId, Text
from app.models.procedure_graph import GraphRecord


PresentationMode = Literal["OVERVIEW", "GUIDED"]
RelationshipVisual = Literal[
    "NONE", "BRANCH_MAP", "DEPENDENCY_MAP", "PARALLEL_MAP"
]
DependencyLayer = Literal["stage", "action"]
Fingerprint = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class ScaffoldConfiguration(GraphRecord):
    presentation_mode: PresentationMode
    progressive_disclosure: bool
    previous_context_recap: bool
    relationship_visual: RelationshipVisual
    prerequisite_cue: bool

    @computed_field
    @property
    def configuration_id(self) -> str:
        return (
            f"c4-scaffold-v1:{self.presentation_mode}"
            f":pd{int(self.progressive_disclosure)}"
            f":recap{int(self.previous_context_recap)}"
            f":{self.relationship_visual}"
            f":cue{int(self.prerequisite_cue)}"
        )


class PresentationLocks(GraphRecord):
    """None means unlocked. False is an explicit OFF lock."""

    presentation_mode: PresentationMode | None = None
    progressive_disclosure: bool | None = None
    previous_context_recap: bool | None = None
    relationship_visual: RelationshipVisual | None = None
    prerequisite_cue: bool | None = None


class AccessibilityConstraints(GraphRecord):
    """Explicit functional constraints, not inferred disability labels."""

    allow_relationship_visuals: bool = True
    allow_collapsed_content: bool = True
    allow_guided_navigation: bool = True


class PriorExposure(GraphRecord):
    """Previously displayed action context supplied by the session layer.

    This records exposure, not task completion or prerequisite satisfaction.
    """

    session_id: Text
    graph_fingerprint: Fingerprint
    action_ids: tuple[ActionId, ...] = Field(min_length=1)


class FeasibilityContext(GraphRecord):
    session_id: Text | None = None
    history: tuple[PriorExposure, ...] = ()
    locks: PresentationLocks = Field(default_factory=PresentationLocks)
    accessibility: AccessibilityConstraints = Field(
        default_factory=AccessibilityConstraints
    )


class Notice(GraphRecord):
    notice_id: Text
    text: Text


class DisclosureReview(GraphRecord):
    """Trusted content-author review tied to an exact graph snapshot.

    The author attests that these blocks contain only supplementary
    explanation, with no unique requirements, warnings, conditions,
    prerequisites or source information.

    This is not a user preference and is not inferred from prose.
    """

    graph_fingerprint: Fingerprint
    safe_content_ids: tuple[ContentId, ...]


class ContentSafety(GraphRecord):
    """Trusted content-safety inputs supplied independently of user locks."""

    disclosure_review: DisclosureReview | None = None
    warning_content_ids: tuple[ContentId, ...] = ()
    warnings: tuple[Notice, ...] = ()


ItemKind = Literal[
    "stage",
    "action",
    "content",
    "fact",
    "condition",
    "branch_group",
    "parallel_group",
    "stage_dependency",
    "action_prerequisite",
    "evidence",
    "provenance",
    "notice",
]


class PresentationItem(GraphRecord):
    kind: ItemKind
    identifier: Text


class PreservationContract(GraphRecord):
    """Coverage contract for the complete presentation document.

    always_visible items must not be removed or placed inside progressive
    disclosure. In guided navigation, their relevant information must be
    visible when its step is presented and remain reachable through normal
    navigation.

    Structural records require faithful text representations even when
    optional relationship diagrams or prerequisite cues are OFF.
    """

    always_visible: tuple[PresentationItem, ...]
    collapsible_content_ids: tuple[ContentId, ...]

    def inventory(self) -> tuple[PresentationItem, ...]:
        return self.always_visible + tuple(
            PresentationItem(kind="content", identifier=content_id)
            for content_id in self.collapsible_content_ids
        )


class Reason(GraphRecord):
    code: Text
    message: Text


class ConfigurationDecision(GraphRecord):
    configuration: ScaffoldConfiguration
    satisfied: tuple[Reason, ...]
    rejections: tuple[Reason, ...]

    @computed_field
    @property
    def accepted(self) -> bool:
        return not self.rejections


class FeasibilityResult(GraphRecord):
    rules_version: Literal["c4-feasibility-1.0"] = "c4-feasibility-1.0"
    graph_fingerprint: Fingerprint
    decisions: tuple[ConfigurationDecision, ...]
    baseline: ScaffoldConfiguration | None
    baseline_reason: Text

    supported_dependency_layers: tuple[DependencyLayer, ...]
    recap_action_ids: tuple[ActionId, ...]
    notices: tuple[Notice, ...]
    preservation: PreservationContract

    def feasible_candidates(self) -> tuple[ScaffoldConfiguration, ...]:
        """Candidates available to the future selection policy."""
        return tuple(
            decision.configuration
            for decision in self.decisions
            if decision.accepted
        )


class VisibilityDeclaration(GraphRecord):
    """Declared coverage across a complete presentation, not one viewport.

    A collapsed item still exists behind a disclosure control. An omitted
    item appears in neither collection.
    """

    visible: tuple[PresentationItem, ...]
    collapsed: tuple[PresentationItem, ...] = ()