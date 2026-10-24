"""Registered synthetic scenarios and their API integration."""

from copy import deepcopy
import json

import pytest
from fastapi.testclient import TestClient

from app.procedures.demo_procedures import (
    FIXTURES_ROOT,
    load_demo_procedures,
    reviewed_demo_safety,
)
from app.procedures.procedure_features import extract_structural_features
from app.procedures.procedure_graph import build_procedure_graph
from app.procedures.procedure_input import (
    load_procedure_input,
    parse_procedure_input,
)
from app.procedures.scaffolds import filter_scaffolds, graph_fingerprint
from app.dev_main import create_app
from tests.test_explanations import FakeProvider


def offline_provider():
    return FakeProvider(failure="offline_test")


def by_plan_id():
    graphs, safety = load_demo_procedures()
    return {graph.plan_id: graph for graph in graphs}, safety


@pytest.mark.parametrize(
    (
        "plan_id",
        "actions",
        "branches",
        "conditions",
        "dependencies",
        "depth",
        "parallels",
        "candidate_count",
        "visuals",
    ),
    [
        (
            "synthetic-linear-v1",
            2, 0, 0, 1, 1, 0, 8,
            {"NONE", "DEPENDENCY_MAP"},
        ),
        (
            "synthetic-conditional-v1",
            3, 1, 2, 2, 1, 0, 24,
            {"NONE", "DEPENDENCY_MAP", "BRANCH_MAP"},
        ),
        (
            "synthetic-parallel-v1",
            4, 0, 0, 4, 2, 1, 24,
            {"NONE", "DEPENDENCY_MAP", "PARALLEL_MAP"},
        ),
    ],
)
def test_registered_structure_and_feasibility(
    plan_id,
    actions,
    branches,
    conditions,
    dependencies,
    depth,
    parallels,
    candidate_count,
    visuals,
):
    graphs, safety = by_plan_id()
    graph = graphs[plan_id]
    features = extract_structural_features(graph)
    result = filter_scaffolds(
        graph,
        features,
        safety=safety[graph_fingerprint(graph)],
    )

    assert graph.synthetic
    assert all(item.kind == "synthetic_authored" for item in graph.evidence)
    assert all(item.retrieved_at is None for item in graph.evidence)

    assert features.step_count.exact_value == actions
    assert features.branch_count.exact_value == branches
    assert features.condition_count.exact_value == conditions
    assert features.dependency_count.exact_value == dependencies
    assert features.dependency_depth.exact_value == depth
    assert features.parallel_group_count.exact_value == parallels
    assert features.information_volume.exact_value > 0

    assert len(result.decisions) == 64
    candidates = result.feasible_candidates()
    assert len(candidates) == candidate_count
    assert {item.relationship_visual for item in candidates} == visuals
    assert not any(item.previous_context_recap for item in candidates)
    assert result.supported_dependency_layers == ("stage", "action")

    if plan_id == "synthetic-conditional-v1":
        group = graph.branch_groups[0]
        assert group.selection == "XOR"
        action_index = {item.action_id: item for item in graph.actions}
        for option in group.options:
            for action_id in option.action_ids:
                applicability = action_index[action_id].applicability
                assert applicability.branch_group_id == group.group_id
                assert applicability.branch_option_id == option.option_id
                assert applicability.condition_ids == option.condition_ids

        assert {
            (edge.source_id, edge.target_id)
            for edge in graph.action_prerequisites
        } == {
            ("action:register_collection", "action:counter_collection"),
            ("action:register_collection", "action:locker_collection"),
        }

    if plan_id == "synthetic-parallel-v1":
        assert set(graph.parallel_groups[0].action_ids) == {
            "action:prepare_form",
            "action:prepare_copy",
        }
        assert {
            (edge.source_id, edge.target_id)
            for edge in graph.action_prerequisites
        } == {
            ("action:register_application", "action:prepare_form"),
            ("action:register_application", "action:prepare_copy"),
            ("action:prepare_form", "action:submit_application"),
            ("action:prepare_copy", "action:submit_application"),
        }


def test_changed_supplementary_text_loses_disclosure_approval():
    directory = FIXTURES_ROOT / "conditional"
    plan_text = (directory / "plan.json").read_text(encoding="utf-8-sig")
    enrichment = json.loads(
        (directory / "enrichment.json").read_text(encoding="utf-8-sig")
    )
    changed = deepcopy(enrichment)
    block = next(
        item
        for item in changed["content"]
        if item["content_id"] == "content:collection_comparison"
    )
    block["text"] = "Changed text that has not received disclosure review."

    graph = build_procedure_graph(
        parse_procedure_input(plan_text, json.dumps(changed))
    )
    safety = reviewed_demo_safety(graph)
    assert safety.disclosure_review is None

    result = filter_scaffolds(
        graph,
        extract_structural_features(graph),
        safety=safety,
    )
    assert not result.preservation.collapsible_content_ids
    assert not any(
        candidate.progressive_disclosure
        for candidate in result.feasible_candidates()
    )


@pytest.mark.parametrize(
    ("plan_id", "visual", "relationship_field"),
    [
        ("synthetic-conditional-v1", "BRANCH_MAP", "branch_groups"),
        ("synthetic-parallel-v1", "PARALLEL_MAP", "parallel_groups"),
    ],
)
def test_api_renders_supported_diagram_and_protects_source_cards(
    plan_id,
    visual,
    relationship_field,
):
    application = create_app(provider=offline_provider())

    with TestClient(application) as client:
        response = client.get("/dev/v1/procedures")
        assert response.status_code == 200
        procedures = response.json()
        assert len(procedures) == 3
        assert procedures[0]["plan_id"] == "synthetic-linear-v1"

        procedure = next(item for item in procedures if item["plan_id"] == plan_id)
        assert procedure["title"]
        procedure_id = procedure["procedure_id"]

        graph_response = client.get(
            f"/dev/v1/procedures/{procedure_id}/graph"
        )
        assert graph_response.status_code == 200
        graph = graph_response.json()

        created = client.post("/dev/v1/sessions")
        assert created.status_code == 201
        session = created.json()
        base = f"/dev/v1/sessions/{session['session_id']}"

        updated = client.patch(
            base + "/context",
            json={
                "expected_revision": session["revision"],
                "update": {
                    "locks": {
                        "presentation_mode": "OVERVIEW",
                        "progressive_disclosure": True,
                        "relationship_visual": visual,
                        "prerequisite_cue": True,
                    }
                },
            },
        )
        assert updated.status_code == 200, updated.text
        session = updated.json()

        evaluation_response = client.get(
            f"{base}/feasibility/{procedure_id}"
        )
        assert evaluation_response.status_code == 200
        evaluation = evaluation_response.json()

        selected = client.post(
            base + "/presentations",
            json={
                "procedure_id": procedure_id,
                "expected_revision": session["revision"],
            },
        )
        assert selected.status_code == 201, selected.text
        spec = selected.json()["spec"]

        assert spec["configuration"]["relationship_visual"] == visual
        assert spec["diagram"]["kind"] == visual
        assert spec["diagram"][relationship_field] == graph[relationship_field]
        assert spec["explanation"]["origin"] == "fallback"
        assert spec["explanation"]["source"]["graph"] == graph

        preservation = evaluation["feasibility"]["preservation"]
        protected = {
            (item["kind"], item["identifier"])
            for item in preservation["always_visible"]
        }
        approved = set(preservation["collapsible_content_ids"])
        assert len(approved) == 1

        cards = {
            (card["source"]["kind"], card["source"]["identifier"]): card
            for card in spec["cards"]
        }
        assert set(cards) == protected | {
            ("content", content_id) for content_id in approved
        }

        for key in protected:
            assert not cards[key]["collapsed"]
        for content_id in approved:
            assert cards[("content", content_id)]["collapsed"]

        for block in graph["content"]:
            assert cards[("content", block["content_id"])]["lines"] == [
                block["text"]
            ]

        after = client.get(f"{base}/feasibility/{procedure_id}").json()
        assert after["snapshot"]["matching_exposure_count"] == 0
        assert application.state.runtime.policy.posterior_revision == 0


def test_custom_graphs_do_not_receive_implicit_catalogue_review():
    graphs, _ = by_plan_id()
    graph = graphs["synthetic-parallel-v1"]
    application = create_app(
        provider=offline_provider(),
        graphs=(graph,),
    )

    with TestClient(application) as client:
        session = client.post("/dev/v1/sessions").json()
        response = client.get(
            f"/dev/v1/sessions/{session['session_id']}"
            f"/feasibility/{graph_fingerprint(graph)}"
        )
        assert response.status_code == 200
        feasibility = response.json()["feasibility"]
        assert feasibility["preservation"]["collapsible_content_ids"] == []
        assert not any(
            decision["accepted"]
            and decision["configuration"]["progressive_disclosure"]
            for decision in feasibility["decisions"]
        )


def test_catalogue_expansion_preserves_existing_persisted_presentation(tmp_path):
    linear = build_procedure_graph(
        load_procedure_input(
            FIXTURES_ROOT / "linear" / "plan.json",
            FIXTURES_ROOT / "linear" / "enrichment.json",
        )
    )
    database = tmp_path / "catalogue-recovery.sqlite3"

    original_app = create_app(
        provider=offline_provider(),
        graphs=(linear,),
        database_path=database,
    )
    with TestClient(original_app) as client:
        session = client.post("/dev/v1/sessions").json()
        base = f"/dev/v1/sessions/{session['session_id']}"
        selected = client.post(
            base + "/presentations",
            json={
                "procedure_id": graph_fingerprint(linear),
                "expected_revision": session["revision"],
            },
        )
        assert selected.status_code == 201, selected.text
        original_spec = selected.json()["spec"]
        original_policy = client.get("/dev/v1/policy").json()

    expanded_app = create_app(
        provider=offline_provider(),
        database_path=database,
    )
    with TestClient(expanded_app) as client:
        procedures = client.get("/dev/v1/procedures").json()
        assert len(procedures) == 3
        assert procedures[0]["procedure_id"] == graph_fingerprint(linear)

        recovered = client.get(
            base + f"/presentations/{original_spec['exposure_id']}"
        )
        assert recovered.status_code == 200, recovered.text
        assert recovered.json()["spec"] == original_spec

        recovered_policy = client.get("/dev/v1/policy").json()
        for field in (
            "policy_run_id",
            "posterior_revision",
            "posterior_fingerprint",
        ):
            assert recovered_policy[field] == original_policy[field]