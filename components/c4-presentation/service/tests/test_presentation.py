"""Presentation composition tests using the existing synthetic scenarios."""

import json

import pytest
from pydantic import ValidationError

from app.core.explanations import ExplanationService
from app.core.policy import SharedLinTSPolicy
from app.core.presentation import (
    PresentationError,
    action_navigation_order,
    build_presentation_spec,
)
from app.core.procedure_features import extract_structural_features
from app.core.scaffolds import graph_fingerprint
from app.core.user_context import InMemoryContextService
from app.models.presentation import PresentationSpec
from app.models.scaffolds import (
    ContentSafety,
    DisclosureReview,
    PresentationLocks,
)
from app.models.user_context import ContextUpdate

from tests.test_explanations import FakeProvider
from tests.test_scaffolds import (
    FIXTURES,
    add_supplement,
    graph_from,
    rich_documents,
)


def documents():
    return tuple(
        json.loads((FIXTURES / name).read_text(encoding="utf-8-sig"))
        for name in ("plan.json", "enrichment.json")
    )


def pipeline(graph, *, locks=None, safety=None, provider=None):
    contexts = InMemoryContextService()
    session = contexts.create_session()
    if locks is not None:
        session = contexts.update_context(
            session.session_id,
            ContextUpdate(locks=locks),
            expected_revision=session.revision,
        )
    policy = SharedLinTSPolicy(contexts)
    selected = policy.select_and_offer(
        session.session_id,
        graph,
        extract_structural_features(graph),
        intended_action_ids=action_navigation_order(graph),
        safety=safety,
    )
    explanations = ExplanationService(
        provider if provider is not None else FakeProvider(failure="offline_test")
    )
    result = explanations.explain(graph, selected, safety=safety)
    return contexts, session, policy, selected, explanations, result


def test_fallback_preserves_source_cards_and_does_not_acknowledge():
    graph = graph_from(documents())
    before = graph.model_dump_json()
    contexts, session, policy, selected, service, result = pipeline(graph)

    spec = build_presentation_spec(graph, selected, result)
    assert spec.explanation.origin == "fallback"
    assert spec.explanation.source.graph == graph
    assert spec.configuration.presentation_mode == "OVERVIEW"
    assert spec.initial_action_id is None
    assert spec.acknowledgment_action_ids == (
        "action:request_token",
        "action:collect_pack",
    )
    assert set(card.source for card in spec.cards) == set(
        result.source.preservation.inventory()
    )
    for content in graph.content:
        card = next(
            card
            for card in spec.cards
            if card.source.kind == "content"
            and card.source.identifier == content.content_id
        )
        assert card.lines == (content.text,)
        assert not card.collapsed

    assert any(card.source.kind == "fact" for card in spec.cards)
    assert any(card.source.kind == "provenance" for card in spec.cards)
    assert contexts.event_history(session.session_id) == ()
    assert policy.posterior_revision == 0
    assert graph.model_dump_json() == before
    assert spec == build_presentation_spec(graph, selected, result)
    assert PresentationSpec.model_validate_json(
        spec.model_dump_json(round_trip=True)
    ) == spec


def test_generated_explanations_supplement_unchanged_sources():
    graph = graph_from(documents())
    provider = FakeProvider()
    contexts, session, policy, selected, service, result = pipeline(
        graph, provider=provider
    )
    spec = build_presentation_spec(graph, selected, result)
    assert result.origin == "generated"
    assert spec.explanation.assurance == "automated_checks_only"
    assert len(provider.calls) == 2
    assert spec.explanation.source.graph == graph
    for block in graph.content:
        assert any(card.lines == (block.text,) for card in spec.cards)
    assert contexts.event_history(session.session_id) == ()


def test_guided_focus_and_explicit_prerequisite_cues():
    graph = graph_from(documents())
    values = pipeline(
        graph,
        locks=PresentationLocks(
            presentation_mode="GUIDED",
            relationship_visual="DEPENDENCY_MAP",
            prerequisite_cue=True,
        ),
    )
    selected, result = values[3], values[5]
    spec = build_presentation_spec(
        graph,
        selected,
        result,
        focus_action_id="action:collect_pack",
    )
    assert spec.initial_action_id == "action:collect_pack"
    assert spec.acknowledgment_action_ids == ("action:collect_pack",)
    assert len(spec.pages) == 2
    page = next(p for p in spec.pages if p.action_id == "action:collect_pack")
    assert {cue.kind for cue in page.prerequisite_cues} == {
        "stage_dependency",
        "action_prerequisite",
    }
    assert spec.diagram.stage_dependencies == graph.stage_dependencies
    assert spec.diagram.action_prerequisites == graph.action_prerequisites

    with pytest.raises(PresentationError, match="unknown focus"):
        build_presentation_spec(
            graph, selected, result, focus_action_id="action:missing"
        )


def test_only_reviewed_supplementary_content_is_collapsed():
    docs = documents()
    add_supplement(docs[1])
    graph = graph_from(docs)
    safety = ContentSafety(
        disclosure_review=DisclosureReview(
            graph_fingerprint=graph_fingerprint(graph),
            safe_content_ids=("content:extra_explanation",),
        )
    )
    values = pipeline(
        graph,
        safety=safety,
        locks=PresentationLocks(progressive_disclosure=True),
    )
    spec = build_presentation_spec(
        graph, values[3], values[5], safety=safety
    )
    assert [
        card.source.identifier for card in spec.cards if card.collapsed
    ] == ["content:extra_explanation"]
    assert all(
        not card.collapsed
        for card in spec.cards
        if card.source.kind in {
            "fact", "evidence", "provenance", "condition",
            "action_prerequisite", "stage_dependency", "notice",
        }
    )


@pytest.mark.parametrize("selection", ["AND", "OR", "XOR"])
def test_branch_visual_preserves_explicit_selection_semantics(selection):
    graph = graph_from(rich_documents(documents(), selection))
    values = pipeline(
        graph,
        locks=PresentationLocks(relationship_visual="BRANCH_MAP"),
    )
    spec = build_presentation_spec(graph, values[3], values[5])
    assert spec.diagram.branch_groups == graph.branch_groups
    assert spec.diagram.branch_groups[0].selection == selection
    assert not spec.diagram.stage_dependencies
    assert not spec.diagram.action_prerequisites
    assert all(
        page.branch_group_id is not None
        for page in spec.pages
        if page.action_id != "action:request_token"
    )


def test_parallel_visual_contains_only_explicit_parallel_groups():
    graph = graph_from(rich_documents(documents()))
    values = pipeline(
        graph,
        locks=PresentationLocks(relationship_visual="PARALLEL_MAP"),
    )
    spec = build_presentation_spec(graph, values[3], values[5])
    assert spec.diagram.parallel_groups == graph.parallel_groups
    assert not spec.diagram.action_prerequisites
    assert not spec.diagram.stage_dependencies


def test_unknown_structure_remains_unknown_with_safe_overview():
    docs = documents()
    for key in docs[1]["completeness"]:
        docs[1]["completeness"][key] = "unknown"
    graph = graph_from(docs)
    values = pipeline(graph)
    spec = build_presentation_spec(graph, values[3], values[5])
    assert spec.configuration.presentation_mode == "OVERVIEW"
    assert spec.diagram.kind == "NONE"
    assert spec.explanation.source.graph.completeness == graph.completeness
    assert any(
        card.source.identifier == "c4:incomplete_structure"
        for card in spec.cards
    )


def test_recap_uses_acknowledged_chronological_history_not_completion():
    graph = graph_from(documents())
    contexts, session, policy, selected, service, result = pipeline(graph)

    contexts.acknowledge_exposure(
        session.session_id,
        selected.offer.exposure_id,
        configuration_id=selected.offer.configuration.configuration_id,
        displayed_action_ids=("action:request_token",),
    )
    current = contexts.get_session(session.session_id)
    contexts.update_context(
        session.session_id,
        ContextUpdate(
            locks=PresentationLocks(previous_context_recap=True)
        ),
        expected_revision=current.revision,
    )
    next_offer = policy.select_and_offer(
        session.session_id,
        graph,
        extract_structural_features(graph),
        intended_action_ids=action_navigation_order(graph),
    )
    next_result = service.explain(graph, next_offer)
    spec = build_presentation_spec(graph, next_offer, next_result)
    assert spec.recap.action_ids == ("action:request_token",)
    assert spec.recap.exposure_ids == (selected.offer.exposure_id,)
    assert spec.recap.meaning == "previously_displayed_not_completed"
    assert policy.posterior_revision == 0


def test_wrong_attribution_or_altered_fallback_is_rejected():
    graph = graph_from(documents())
    values = pipeline(graph)
    selected, result = values[3], values[5]

    wrong = result.model_copy(update={"exposure_id": "exposure:" + "0" * 32})
    with pytest.raises(PresentationError, match="attribution"):
        build_presentation_spec(graph, selected, wrong)

    altered = result.explanations[0].model_copy(
        update={"text": "Invented procedural requirement."}
    )
    wrong = result.model_copy(
        update={"explanations": (altered,) + result.explanations[1:]}
    )
    with pytest.raises(PresentationError, match="validated_result"):
        build_presentation_spec(graph, selected, wrong)


def test_document_schema_rejects_missing_or_collapsed_mandatory_cards():
    graph = graph_from(documents())
    values = pipeline(graph)
    spec = build_presentation_spec(graph, values[3], values[5])

    raw = json.loads(spec.model_dump_json(round_trip=True))
    raw["cards"].pop()
    with pytest.raises(ValidationError, match="complete source inventory"):
        PresentationSpec.model_validate_json(json.dumps(raw))

    raw = json.loads(spec.model_dump_json(round_trip=True))
    card = next(card for card in raw["cards"] if card["source"]["kind"] == "fact")
    card["collapsed"] = True
    raw["visibility"]["visible"].remove(card["source"])
    raw["visibility"]["collapsed"].append(card["source"])
    with pytest.raises(ValidationError, match="mandatory source"):
        PresentationSpec.model_validate_json(json.dumps(raw))