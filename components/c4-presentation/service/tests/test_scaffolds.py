"""Hard feasibility and preservation tests through the real C4 pipeline."""

import copy
import json
from pathlib import Path

import pytest

from app.core.procedure_features import extract_structural_features
from app.core.procedure_graph import build_procedure_graph
from app.core.procedure_input import parse_procedure_input
from app.core.scaffolds import (
    enumerate_scaffolds,
    filter_scaffolds,
    graph_fingerprint,
    validate_visibility,
)
from app.models.scaffolds import (
    AccessibilityConstraints,
    ContentSafety,
    DisclosureReview,
    FeasibilityContext,
    Notice,
    PresentationItem,
    PresentationLocks,
    PriorExposure,
    VisibilityDeclaration,
)


FIXTURES = (
    Path(__file__).resolve().parents[2]
    / "research"
    / "data"
    / "fixtures"
    / "linear"
)


@pytest.fixture
def documents():
    return tuple(
        json.loads((FIXTURES / filename).read_text(encoding="utf-8-sig"))
        for filename in ("plan.json", "enrichment.json")
    )


def graph_from(documents):
    procedure = parse_procedure_input(
        json.dumps(documents[0]),
        json.dumps(documents[1]),
    )
    return build_procedure_graph(procedure)


def evaluate(documents, **kwargs):
    graph = graph_from(documents)
    return filter_scaffolds(
        graph, extract_structural_features(graph), **kwargs
    )


def candidate(result, **dimensions):
    return next(
        configuration
        for configuration in result.feasible_candidates()
        if all(
            getattr(configuration, name) == value
            for name, value in dimensions.items()
        )
    )


def add_supplement(enrichment):
    enrichment["content"].append(
        {
            "content_id": "content:extra_explanation",
            "role": "supplementary",
            "text": "This optional explanation describes the fictional demo.",
            "evidence_ids": ["evidence:collect_pack"],
            "fact_ids": [],
        }
    )
    enrichment["actions"][1]["supplementary_content_ids"] = [
        "content:extra_explanation"
    ]


def review_for(graph, *content_ids):
    return ContentSafety(
        disclosure_review=DisclosureReview(
            graph_fingerprint=graph_fingerprint(graph),
            safe_content_ids=tuple(content_ids),
        )
    )


def rich_documents(documents, selection="XOR"):
    plan, enrichment = copy.deepcopy(documents)
    enrichment["evidence"].append(
        {
            "evidence_id": "evidence:structure",
            "kind": "synthetic_authored",
            "source_url": "https://example.org/c4/scaffold-tests",
            "text": (
                "Fictional scenario: token request precedes three pack "
                "actions. The left option contains collect_pack and left; "
                "they may run concurrently when the left condition applies. "
                "The right option contains right when its condition applies. "
                f"The branch group uses {selection} selection."
            ),
            "retrieved_at": None,
        }
    )

    for name in ("left", "right"):
        action = copy.deepcopy(enrichment["actions"][1])
        action["action_id"] = f"action:{name}"
        enrichment["actions"].append(action)
        enrichment["prerequisites"].append(
            {
                "prerequisite_id": f"prerequisite:token_{name}",
                "kind": "requires_completion",
                "required_action_id": "action:request_token",
                "dependent_action_id": f"action:{name}",
                "evidence_ids": ["evidence:structure"],
            }
        )

    enrichment["conditions"] = [
        {
            "condition_id": f"condition:{name}",
            "text": f"The fictional {name} condition applies.",
            "evidence_ids": ["evidence:structure"],
        }
        for name in ("left", "right")
    ]
    enrichment["branch_groups"] = [
        {
            "group_id": "branch:choice",
            "service_id": "svc:demo_pack",
            "selection": selection,
            "options": [
                {
                    "option_id": "option:left",
                    "action_ids": ["action:collect_pack", "action:left"],
                    "condition_ids": ["condition:left"],
                },
                {
                    "option_id": "option:right",
                    "action_ids": ["action:right"],
                    "condition_ids": ["condition:right"],
                },
            ],
            "evidence_ids": ["evidence:structure"],
        }
    ]
    enrichment["parallel_groups"] = [
        {
            "group_id": "parallel:left",
            "service_id": "svc:demo_pack",
            "action_ids": ["action:collect_pack", "action:left"],
            "evidence_ids": ["evidence:structure"],
        }
    ]
    return plan, enrichment


def test_catalogue_is_the_exact_five_dimension_product():
    catalogue = enumerate_scaffolds()
    assert len(catalogue) == 64
    assert len({item.configuration_id for item in catalogue}) == 64
    assert len(set(catalogue)) == 64
    assert catalogue == enumerate_scaffolds()

    assert {item.presentation_mode for item in catalogue} == {
        "OVERVIEW", "GUIDED"
    }
    assert {item.relationship_visual for item in catalogue} == {
        "NONE", "BRANCH_MAP", "DEPENDENCY_MAP", "PARALLEL_MAP"
    }
    for field in (
        "progressive_disclosure",
        "previous_context_recap",
        "prerequisite_cue",
    ):
        assert {getattr(item, field) for item in catalogue} == {False, True}


def test_linear_feasibility_and_safe_baseline(documents):
    result = evaluate(documents)
    feasible = result.feasible_candidates()

    assert len(result.decisions) == 64
    assert len(feasible) == 8
    assert result.supported_dependency_layers == ("stage", "action")
    assert all(not item.progressive_disclosure for item in feasible)
    assert all(not item.previous_context_recap for item in feasible)
    assert {
        item.relationship_visual for item in feasible
    } == {"NONE", "DEPENDENCY_MAP"}

    baseline = result.baseline
    assert baseline is not None
    assert baseline.presentation_mode == "OVERVIEW"
    assert baseline.relationship_visual == "NONE"
    assert not baseline.progressive_disclosure
    assert not baseline.previous_context_recap
    assert not baseline.prerequisite_cue

    assert all(
        decision.satisfied if decision.accepted else decision.rejections
        for decision in result.decisions
    )


@pytest.mark.parametrize("selection", ["AND", "OR", "XOR"])
def test_explicit_branch_and_parallel_structures_enable_maps(
    documents, selection
):
    result = evaluate(rich_documents(documents, selection))
    assert {
        item.relationship_visual
        for item in result.feasible_candidates()
    } == {"NONE", "BRANCH_MAP", "DEPENDENCY_MAP", "PARALLEL_MAP"}

    protected = set(result.preservation.always_visible)
    assert PresentationItem(
        kind="branch_group", identifier="branch:choice"
    ) in protected
    assert PresentationItem(
        kind="condition", identifier="condition:left"
    ) in protected
    assert PresentationItem(
        kind="parallel_group", identifier="parallel:left"
    ) in protected


@pytest.mark.parametrize("state", ["partial", "unknown"])
def test_incomplete_structure_blocks_maps_without_becoming_known_zero(
    documents, state
):
    docs = rich_documents(documents)
    # Existing 1A correctly forbids asserted parallel groups with
    # incomplete prerequisite knowledge, so remove those claims first.
    docs[1]["parallel_groups"] = []
    for field in docs[1]["completeness"]:
        docs[1]["completeness"][field] = state

    graph = graph_from(docs)
    features = extract_structural_features(graph)
    assert features.branch_count.observed == 1
    assert features.branch_count.exact_value is None

    result = filter_scaffolds(graph, features)
    assert len(result.feasible_candidates()) == 1
    assert result.baseline.presentation_mode == "OVERVIEW"
    assert result.baseline.relationship_visual == "NONE"
    assert not result.baseline.prerequisite_cue
    assert any(
        notice.notice_id == "c4:incomplete_structure"
        for notice in result.notices
    )


def test_stage_only_dependency_support_is_identified(documents):
    documents[1]["actions"] = []
    documents[1]["prerequisites"] = []
    for field in documents[1]["completeness"]:
        if field != "service_dependencies":
            documents[1]["completeness"][field] = "unknown"

    result = evaluate(documents)

    assert result.supported_dependency_layers == ("stage",)
    assert any(
        item.relationship_visual == "DEPENDENCY_MAP"
        for item in result.feasible_candidates()
    )
    assert all(
        item.presentation_mode == "OVERVIEW"
        for item in result.feasible_candidates()
    )


def test_order_and_absent_edges_do_not_enable_relationship_scaffolds(
    documents,
):
    documents[0]["steps"][1]["depends_on"] = []
    documents[1]["prerequisites"] = []

    result = evaluate(documents)
    assert result.supported_dependency_layers == ()
    assert all(
        item.relationship_visual == "NONE"
        and not item.prerequisite_cue
        for item in result.feasible_candidates()
    )


def test_recap_requires_same_session_snapshot_and_known_exposure(documents):
    graph = graph_from(documents)
    features = extract_structural_features(graph)
    fingerprint = graph_fingerprint(graph)

    def context_for(session, snapshot):
        return FeasibilityContext(
            session_id="session:current",
            history=(
                PriorExposure(
                    session_id=session,
                    graph_fingerprint=snapshot,
                    action_ids=("action:request_token",),
                ),
            ),
        )

    for context in (
        FeasibilityContext(),
        context_for("session:other", fingerprint),
        context_for("session:current", "0" * 64),
    ):
        result = filter_scaffolds(graph, features, context=context)
        assert not result.recap_action_ids
        assert all(
            not item.previous_context_recap
            for item in result.feasible_candidates()
        )

    result = filter_scaffolds(
        graph,
        features,
        context=context_for("session:current", fingerprint),
    )
    assert result.recap_action_ids == ("action:request_token",)
    assert any(
        item.previous_context_recap
        for item in result.feasible_candidates()
    )

    invalid = FeasibilityContext(
        session_id="session:current",
        history=(
            PriorExposure(
                session_id="session:current",
                graph_fingerprint=fingerprint,
                action_ids=("action:missing",),
            ),
        ),
    )
    with pytest.raises(ValueError, match="unknown actions"):
        filter_scaffolds(graph, features, context=invalid)


def test_locks_and_accessibility_are_hard_constraints(documents):
    context = FeasibilityContext(
        locks=PresentationLocks(
            presentation_mode="GUIDED",
            progressive_disclosure=False,
            previous_context_recap=False,
            relationship_visual="NONE",
            prerequisite_cue=False,
        )
    )
    result = evaluate(documents, context=context)
    assert len(result.feasible_candidates()) == 1
    assert result.baseline.presentation_mode == "GUIDED"

    conflict = FeasibilityContext(
        locks=PresentationLocks(relationship_visual="DEPENDENCY_MAP"),
        accessibility=AccessibilityConstraints(
            allow_relationship_visuals=False
        ),
    )
    blocked = evaluate(documents, context=conflict)
    assert blocked.feasible_candidates() == ()
    assert blocked.baseline is None
    assert all(decision.rejections for decision in blocked.decisions)


def test_disclosure_requires_review_and_respects_accessibility(documents):
    add_supplement(documents[1])
    graph = graph_from(documents)
    features = extract_structural_features(graph)

    unreviewed = filter_scaffolds(graph, features)
    assert all(
        not item.progressive_disclosure
        for item in unreviewed.feasible_candidates()
    )

    safety = review_for(graph, "content:extra_explanation")
    reviewed = filter_scaffolds(graph, features, safety=safety)
    assert any(
        item.progressive_disclosure
        for item in reviewed.feasible_candidates()
    )

    constrained = filter_scaffolds(
        graph,
        features,
        safety=safety,
        context=FeasibilityContext(
            accessibility=AccessibilityConstraints(
                allow_collapsed_content=False,
                allow_guided_navigation=False,
            )
        ),
    )
    assert all(
        not item.progressive_disclosure
        and item.presentation_mode == "OVERVIEW"
        for item in constrained.feasible_candidates()
    )


def test_invalid_required_warning_and_fact_linked_reviews_are_rejected(
    documents,
):
    add_supplement(documents[1])
    graph = graph_from(documents)
    features = extract_structural_features(graph)

    with pytest.raises(ValueError, match="referenced supplementary"):
        filter_scaffolds(
            graph,
            features,
            safety=review_for(graph, "content:request_token"),
        )

    warning_review = ContentSafety(
        disclosure_review=review_for(
            graph, "content:extra_explanation"
        ).disclosure_review,
        warning_content_ids=("content:extra_explanation",),
    )
    with pytest.raises(ValueError, match="warning content"):
        filter_scaffolds(graph, features, safety=warning_review)

    documents[1]["content"][-1]["fact_ids"] = ["svc:demo_pack:fee"]
    graph = graph_from(documents)
    with pytest.raises(ValueError, match="fact-linked"):
        filter_scaffolds(
            graph,
            extract_structural_features(graph),
            safety=review_for(graph, "content:extra_explanation"),
        )


def test_visibility_protects_essential_items_even_with_disclosure(documents):
    docs = rich_documents(documents)
    add_supplement(docs[1])
    graph = graph_from(docs)

    safety = ContentSafety(
        disclosure_review=review_for(
            graph, "content:extra_explanation"
        ).disclosure_review,
        warnings=(
            Notice(
                notice_id="demo:warning",
                text="Fictional warning retained for this preservation test.",
            ),
        ),
    )
    result = filter_scaffolds(
        graph, extract_structural_features(graph), safety=safety
    )
    on = candidate(result, progressive_disclosure=True)
    off = candidate(result, progressive_disclosure=False)

    optional = PresentationItem(
        kind="content", identifier="content:extra_explanation"
    )
    protected = result.preservation.always_visible
    good = VisibilityDeclaration(visible=protected, collapsed=(optional,))
    assert validate_visibility(result, on, good) == ()
    assert validate_visibility(result, off, good)

    all_visible = VisibilityDeclaration(
        visible=result.preservation.inventory()
    )
    assert validate_visibility(result, off, all_visible) == ()

    for kind in (
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
    ):
        item = next(item for item in protected if item.kind == kind)
        unsafe = VisibilityDeclaration(
            visible=tuple(value for value in protected if value != item),
            collapsed=(optional, item),
        )
        codes = {
            reason.code for reason in validate_visibility(result, on, unsafe)
        }
        assert "PROTECTED_ITEMS_NOT_VISIBLE" in codes
        assert "FORBIDDEN_COLLAPSE" in codes

    omitted = VisibilityDeclaration(visible=protected)
    assert any(
        reason.code == "OMITTED_ITEMS"
        for reason in validate_visibility(result, on, omitted)
    )


def test_stale_features_and_stale_reviews_are_rejected(documents):
    add_supplement(documents[1])
    graph = graph_from(documents)
    features = extract_structural_features(graph)
    safety = review_for(graph, "content:extra_explanation")

    documents[1]["content"][0]["text"] += " Extra fictional explanation."
    changed_graph = graph_from(documents)

    with pytest.raises(ValueError, match="features do not match"):
        filter_scaffolds(changed_graph, features)

    with pytest.raises(ValueError, match="another graph snapshot"):
        filter_scaffolds(
            changed_graph,
            extract_structural_features(changed_graph),
            safety=safety,
        )


def test_results_are_deterministic_and_inputs_are_unchanged(documents):
    graph = graph_from(documents)
    features = extract_structural_features(graph)
    before_graph = graph.model_dump_json()
    before_features = features.model_dump_json()

    first = filter_scaffolds(graph, features)
    second = filter_scaffolds(graph, features)

    assert first.model_dump_json() == second.model_dump_json()
    assert graph.model_dump_json() == before_graph
    assert features.model_dump_json() == before_features
    assert any(
        notice.notice_id == "c4:source_status"
        and "Synthetic" in notice.text
        for notice in first.notices
    )