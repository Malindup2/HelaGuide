"""Deterministic PresentationSpec composition without network or mutations."""

import hashlib
import json

from app.core.explanations import (
    prepare_source_packet,
    validate_assessment,
    validate_draft,
)
from app.core.procedure_graph import dependency_index
from app.core.scaffolds import validate_visibility
from app.models.explanations import DisplayExplanation, ExplanationResult
from app.models.policy import PolicyOffer
from app.models.presentation import (
    ActionPage,
    PresentationSpec,
    Recap,
    RelationshipDiagram,
    SourceCard,
)
from app.models.procedure_graph import CanonicalProcedureGraph
from app.models.scaffolds import (
    ContentSafety,
    PresentationItem,
    VisibilityDeclaration,
)


class PresentationError(ValueError):
    """The inputs cannot produce a consistent attributed presentation."""


def item(kind: str, identifier: str) -> PresentationItem:
    return PresentationItem(kind=kind, identifier=identifier)


def action_navigation_order(
    graph: CanonicalProcedureGraph,
) -> tuple[str, ...]:
    """Stable browsing order respecting the two explicit dependency layers.

    This is not an inferred execution plan. Alternative and conditional
    actions remain represented and retain their applicability information.
    """
    stage_order = dependency_index(graph, "stage").topological_order
    action_order = dependency_index(graph, "action").topological_order
    by_id = {action.action_id: action for action in graph.actions}
    return tuple(
        action_id
        for service_id in stage_order
        for action_id in action_order
        if by_id[action_id].service_id == service_id
    )


def _check_explanation(
    graph: CanonicalProcedureGraph,
    selected: PolicyOffer,
    result: ExplanationResult,
    safety: ContentSafety | None,
) -> None:
    packet, source = prepare_source_packet(graph, selected, safety=safety)

    if (
        result.source != source
        or result.graph_fingerprint != selected.offer.graph_fingerprint
        or result.exposure_id != selected.offer.exposure_id
        or result.decision_id != selected.decision.decision_id
        or result.configuration != selected.offer.configuration
        or result.source_status != packet["source_status"]
    ):
        raise PresentationError("explanation_source_or_attribution_mismatch")

    expected = []
    if result.origin == "generated":
        artifact = result.artifact
        if artifact is None:
            raise PresentationError("generated_explanation_requires_artifact")
        if (
            artifact.graph_fingerprint != result.graph_fingerprint
            or artifact.request_key != result.request_key
        ):
            raise PresentationError("generated_artifact_identity_mismatch")

        validate_draft(packet, artifact.draft)
        validate_assessment(packet, artifact.assessment)

        expected_assurance = (
            "human_reviewed_against_supplied_sources"
            if artifact.review is not None
            else "automated_checks_only"
        )
        if result.assurance != expected_assurance:
            raise PresentationError("generated_assurance_mismatch")

        for unit, draft in zip(packet["units"], artifact.draft.items):
            expected.append(
                DisplayExplanation(
                    unit_id=unit["unit_id"],
                    action_id=unit["action_id"],
                    content_id=unit["content_id"],
                    origin="generated",
                    text=draft.text,
                    fact_ids=draft.fact_ids,
                    evidence_ids=tuple(
                        citation.evidence_id for citation in draft.citations
                    ),
                    citations=draft.citations,
                )
            )
    else:
        if (
            result.artifact is not None
            or result.assurance != "source_preserving_copy"
        ):
            raise PresentationError("fallback_metadata_mismatch")

        for unit in packet["units"]:
            expected.append(
                DisplayExplanation(
                    unit_id=unit["unit_id"],
                    action_id=unit["action_id"],
                    content_id=unit["content_id"],
                    origin="source_copy",
                    text=unit["source_content"],
                    fact_ids=tuple(unit["fact_ids"]),
                    evidence_ids=tuple(
                        evidence["evidence_id"] for evidence in unit["evidence"]
                    ),
                    citations=(),
                )
            )

    if result.explanations != tuple(expected):
        raise PresentationError("display_explanations_differ_from_validated_result")


def _source_cards(graph, result, configuration) -> tuple[SourceCard, ...]:
    cards = []
    collapsible = set(result.source.preservation.collapsible_content_ids)

    def add(kind, identifier, title, *lines):
        cards.append(
            SourceCard(
                source=item(kind, identifier),
                title=title,
                lines=tuple(lines),
                collapsed=(
                    configuration.progressive_disclosure
                    and kind == "content"
                    and identifier in collapsible
                ),
            )
        )

    for stage in graph.stages:
        add(
            "stage",
            stage.service_id,
            stage.name,
            f"Service: {stage.service_id}",
            f"Agency: {stage.agency}",
            f"Supplied display order: {stage.display_order}",
            f"Fee reference: {stage.fee_fact_id}",
            "Document references: "
            + (", ".join(stage.document_fact_ids) or "None supplied."),
        )

    for action in graph.actions:
        lines = [
            f"Action: {action.action_id}",
            f"Parent service: {action.service_id}",
            "Required content references: "
            + ", ".join(action.required_content_ids),
            "Supplementary content references: "
            + (", ".join(action.supplementary_content_ids) or "None supplied."),
            "Supplied applicability conditions: "
            + (
                ", ".join(action.applicability.condition_ids)
                or "None supplied; consult completeness information."
            ),
        ]
        if action.applicability.branch_group_id is not None:
            lines.append(
                "Alternative membership: "
                f"{action.applicability.branch_group_id}, "
                f"{action.applicability.branch_option_id}. "
                "This does not determine which option applies to the citizen."
            )
        add("action", action.action_id, "Procedure action", *lines)

    for block in graph.content:
        add("content", block.content_id, block.role.capitalize() + " source text",
            block.text)

    for fact in graph.facts:
        if fact.kind == "fee":
            add(
                "fact",
                fact.fact_id,
                "Supplied fee",
                f"{fact.currency} {fact.value:g}",
                f"Fact reference: {fact.fact_id}",
            )
        else:
            add(
                "fact",
                fact.fact_id,
                "Required document",
                fact.name,
                f"Fact reference: {fact.fact_id}",
            )

    for condition in graph.conditions:
        add(
            "condition",
            condition.condition_id,
            "Supplied condition",
            condition.text,
            "Evidence references: " + ", ".join(condition.evidence_ids),
        )

    for edge in graph.stage_dependencies:
        add(
            "stage_dependency",
            edge.edge_id,
            "Explicit service dependency",
            f"{edge.target_id} depends on {edge.source_id}.",
            "No additional AND/OR interpretation is inferred.",
        )

    for edge in graph.action_prerequisites:
        add(
            "action_prerequisite",
            edge.edge_id,
            "Explicit action prerequisite",
            f"{edge.source_id} must be completed before {edge.target_id}.",
            "The presentation does not establish that completion has occurred.",
            "Evidence references: " + ", ".join(edge.evidence_ids),
        )

    meanings = {
        "AND": "All options in this group are selected under the supplied applicability.",
        "OR": "One or more applicable options may be selected.",
        "XOR": "Exactly one applicable option is selected.",
    }
    for group in graph.branch_groups:
        lines = [
            f"Service: {group.service_id}",
            f"Selection semantics: {group.selection}. {meanings[group.selection]}",
            "The backend does not decide citizen eligibility or select an option.",
        ]
        for option in group.options:
            lines.append(
                f"{option.option_id}: actions {', '.join(option.action_ids)}; "
                "supplied conditions: "
                + (
                    ", ".join(option.condition_ids)
                    or "None supplied; consult completeness information."
                )
            )
        lines.append("Evidence references: " + ", ".join(group.evidence_ids))
        add("branch_group", group.group_id, "Explicit alternative group", *lines)

    for group in graph.parallel_groups:
        add(
            "parallel_group",
            group.group_id,
            "Explicit parallel group",
            f"Service: {group.service_id}",
            "Actions: " + ", ".join(group.action_ids),
            "These actions are explicitly represented as parallel under their "
            "supplied applicability and prerequisites.",
            "Evidence references: " + ", ".join(group.evidence_ids),
        )

    for evidence in graph.evidence:
        add(
            "evidence",
            evidence.evidence_id,
            "Supplied evidence",
            f"Classification: {evidence.kind}",
            evidence.text,
            f"Source URL: {evidence.source_url}",
            "Retrieval timestamp: "
            + (
                evidence.retrieved_at.isoformat()
                if evidence.retrieved_at is not None
                else "Not supplied."
            ),
        )

    for provenance in graph.provenance:
        add(
            "provenance",
            provenance.fact_id,
            "Fact provenance",
            f"Fact reference: {provenance.fact_id}",
            f"Source URL: {provenance.source_url}",
            f"Supplied retrieval timestamp: {provenance.retrieved_at.isoformat()}",
            "A source URL alone is not an exact supporting quotation.",
        )

    for notice in result.source.notices:
        add("notice", notice.notice_id, "Important source information", notice.text)

    return tuple(
        sorted(cards, key=lambda card: (card.source.kind, card.source.identifier))
    )


def _diagram(graph, selected) -> RelationshipDiagram:
    kind = selected.offer.configuration.relationship_visual
    supported = selected.decision.evaluation.feasibility.supported_dependency_layers

    if kind == "NONE":
        return RelationshipDiagram(kind="NONE")

    if kind == "DEPENDENCY_MAP":
        return RelationshipDiagram(
            kind=kind,
            stages=graph.stages if "stage" in supported else (),
            actions=graph.actions if "action" in supported else (),
            stage_dependencies=(
                graph.stage_dependencies if "stage" in supported else ()
            ),
            action_prerequisites=(
                graph.action_prerequisites if "action" in supported else ()
            ),
        )

    if kind == "BRANCH_MAP":
        return RelationshipDiagram(
            kind=kind,
            stages=graph.stages,
            actions=graph.actions,
            branch_groups=graph.branch_groups,
        )

    return RelationshipDiagram(
        kind=kind,
        stages=graph.stages,
        actions=graph.actions,
        parallel_groups=graph.parallel_groups,
    )


def build_presentation_spec(
    graph: CanonicalProcedureGraph,
    selected: PolicyOffer,
    explanation: ExplanationResult,
    *,
    focus_action_id: str | None = None,
    safety: ContentSafety | None = None,
) -> PresentationSpec:
    """Compose a complete document without recording exposure or learning."""
    _check_explanation(graph, selected, explanation, safety)

    order = action_navigation_order(graph)
    if not order:
        raise PresentationError(
            "current policy integration requires at least one detailed action"
        )
    if set(selected.offer.intended_action_ids) != set(order):
        raise PresentationError(
            "a complete PresentationSpec requires an offer covering all graph actions"
        )
    if focus_action_id is not None and focus_action_id not in order:
        raise PresentationError("unknown focus action")

    configuration = selected.offer.configuration
    feasibility = selected.decision.evaluation.feasibility
    cards = _source_cards(graph, explanation, configuration)
    visibility = VisibilityDeclaration(
        visible=tuple(card.source for card in cards if not card.collapsed),
        collapsed=tuple(card.source for card in cards if card.collapsed),
    )
    errors = validate_visibility(feasibility, configuration, visibility)
    if errors:
        raise PresentationError(
            "invalid source coverage: " + ", ".join(error.code for error in errors)
        )

    actions = {action.action_id: action for action in graph.actions}
    pages = []
    for action_id in order:
        action = actions[action_id]
        cues = []
        if configuration.prerequisite_cue:
            if "stage" in feasibility.supported_dependency_layers:
                cues.extend(
                    item("stage_dependency", edge.edge_id)
                    for edge in graph.stage_dependencies
                    if edge.target_id == action.service_id
                )
            if "action" in feasibility.supported_dependency_layers:
                cues.extend(
                    item("action_prerequisite", edge.edge_id)
                    for edge in graph.action_prerequisites
                    if edge.target_id == action_id
                )

        pages.append(
            ActionPage(
                action_id=action_id,
                service_id=action.service_id,
                items=(item("action", action_id),)
                + tuple(
                    item("content", content_id)
                    for content_id in (
                        action.required_content_ids
                        + action.supplementary_content_ids
                    )
                ),
                condition_ids=action.applicability.condition_ids,
                branch_group_id=action.applicability.branch_group_id,
                branch_option_id=action.applicability.branch_option_id,
                prerequisite_cues=tuple(cues),
            )
        )

    located = {reference for page in pages for reference in page.items}
    global_items = tuple(
        card.source for card in cards if card.source not in located
    )

    recap = None
    if configuration.previous_context_recap:
        snapshot = selected.offer.context_snapshot
        recap = Recap(
            action_ids=snapshot.recap_action_ids,
            exposure_ids=tuple(
                event.exposure_id
                for event in snapshot.recent_exposures
                if event.displayed_action_ids
            ),
        )

    initial = (
        focus_action_id or order[0]
        if configuration.presentation_mode == "GUIDED"
        else None
    )

    values = {
        "session_id": selected.offer.session_id,
        "exposure_id": selected.offer.exposure_id,
        "decision_id": selected.decision.decision_id,
        "graph_fingerprint": selected.offer.graph_fingerprint,
        "context_revision": selected.offer.context_snapshot.revision,
        "configuration": configuration,
        "explanation": explanation,
        "cards": cards,
        "global_items": global_items,
        "pages": tuple(pages),
        "initial_action_id": initial,
        "diagram": _diagram(graph, selected),
        "recap": recap,
        "visibility": visibility,
        "acknowledgment_action_ids": (initial,) if initial is not None else order,
    }

    document = PresentationSpec(
        presentation_id="pending",
        **values,
    )
    canonical = json.dumps(
        document.model_dump(mode="json", exclude={"presentation_id"}),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    identifier = "presentation:" + hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()

    return PresentationSpec(presentation_id=identifier, **values)