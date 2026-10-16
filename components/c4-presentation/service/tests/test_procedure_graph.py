"""Tests for C4's canonical procedure graph."""

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.procedure_graph import (
    build_procedure_graph,
    dependency_index,
)
from app.core.procedure_input import (
    ProcedureInputError,
    load_procedure_input,
    parse_procedure_input,
)
from app.models.procedure_graph import CanonicalProcedureGraph


FIXTURES = (
    Path(__file__).resolve().parents[2]
    / "research"
    / "data"
    / "fixtures"
    / "linear"
)


@pytest.fixture
def documents():
    return (
        json.loads((FIXTURES / "plan.json").read_text(encoding="utf-8")),
        json.loads(
            (FIXTURES / "enrichment.json").read_text(encoding="utf-8")
        ),
    )


def parse(documents):
    return parse_procedure_input(
        json.dumps(documents[0]),
        json.dumps(documents[1]),
    )


def by_id(items, field):
    return {getattr(item, field): item for item in items}


def add_action(enrichment, name):
    action_id = f"action:{name}"
    content_id = f"content:{name}"
    evidence_id = f"evidence:{name}"

    enrichment["evidence"].append(
        {
            "evidence_id": evidence_id,
            "kind": "synthetic_authored",
            "source_url": f"https://example.org/c4/graph-tests/{name}",
            "text": f"In this fictional scenario, perform action {name}.",
            "retrieved_at": None,
        }
    )
    enrichment["content"].append(
        {
            "content_id": content_id,
            "role": "required",
            "text": f"Perform fictional action {name}.",
            "evidence_ids": [evidence_id],
            "fact_ids": ["svc:demo_pack:document:token"],
        }
    )
    enrichment["actions"].append(
        {
            "action_id": action_id,
            "service_id": "svc:demo_pack",
            "required_content_ids": [content_id],
            "supplementary_content_ids": [],
            "condition_ids": [],
        }
    )
    return action_id


def rich_documents(documents, selection="XOR"):
    plan, enrichment = copy.deepcopy(documents)

    enrichment["evidence"].append(
        {
            "evidence_id": "evidence:structure",
            "kind": "synthetic_authored",
            "source_url": "https://example.org/c4/graph-tests/structure",
            "text": (
                "This authored scenario has a common eligibility condition "
                "and separate left and right option conditions. All added "
                "actions follow pack collection. The left option contains "
                "two actions that may proceed concurrently. The right "
                f"option contains one action. Selection uses {selection}."
            ),
            "retrieved_at": None,
        }
    )

    for name in ("eligible", "left_applies", "right_applies"):
        enrichment["conditions"].append(
            {
                "condition_id": f"condition:{name}",
                "text": f"Fictional condition {name} applies.",
                "evidence_ids": ["evidence:structure"],
            }
        )

    left_a = add_action(enrichment, "left_a")
    left_b = add_action(enrichment, "left_b")
    right = add_action(enrichment, "right")

    for action in enrichment["actions"][-3:]:
        action["condition_ids"] = ["condition:eligible"]
        enrichment["prerequisites"].append(
            {
                "prerequisite_id": (
                    "prerequisite:collect_before_"
                    + action["action_id"].split(":")[1]
                ),
                "kind": "requires_completion",
                "required_action_id": "action:collect_pack",
                "dependent_action_id": action["action_id"],
                "evidence_ids": ["evidence:structure"],
            }
        )

    enrichment["content"].append(
        {
            "content_id": "content:left_note",
            "role": "supplementary",
            "text": "This left-option explanation is synthetic.",
            "evidence_ids": ["evidence:structure"],
            "fact_ids": [],
        }
    )
    enrichment["actions"][-3]["supplementary_content_ids"] = [
        "content:left_note"
    ]

    enrichment["branch_groups"] = [
        {
            "group_id": "branch:choice",
            "service_id": "svc:demo_pack",
            "selection": selection,
            "options": [
                {
                    "option_id": "option:left",
                    "action_ids": [left_b, left_a],
                    "condition_ids": ["condition:left_applies"],
                },
                {
                    "option_id": "option:right",
                    "action_ids": [right],
                    "condition_ids": ["condition:right_applies"],
                },
            ],
            "evidence_ids": ["evidence:structure"],
        }
    ]
    enrichment["parallel_groups"] = [
        {
            "group_id": "parallel:left",
            "service_id": "svc:demo_pack",
            "action_ids": [left_b, left_a],
            "evidence_ids": ["evidence:structure"],
        }
    ]

    return plan, enrichment


def test_linear_graph_has_typed_nodes_and_explicit_edges():
    procedure = load_procedure_input(
        FIXTURES / "plan.json",
        FIXTURES / "enrichment.json",
    )
    graph = build_procedure_graph(procedure)

    assert graph.plan_id == "synthetic-linear-v1"
    assert graph.synthetic is True
    assert graph.requested_service_id == "svc:demo_pack"
    assert [stage.service_id for stage in graph.stages] == [
        "svc:demo_token",
        "svc:demo_pack",
    ]

    assert len(graph.actions) == 2
    assert len(graph.stage_dependencies) == 1
    assert len(graph.action_prerequisites) == 1

    stage_edge = graph.stage_dependencies[0]
    assert stage_edge.edge_id == (
        "stage_dependency:svc:demo_token->svc:demo_pack"
    )
    assert stage_edge.source_id == "svc:demo_token"
    assert stage_edge.target_id == "svc:demo_pack"

    action_edge = graph.action_prerequisites[0]
    assert action_edge.edge_id == "prerequisite:token_before_pack"
    assert action_edge.source_id == "action:request_token"
    assert action_edge.target_id == "action:collect_pack"
    assert action_edge.evidence_ids == ("evidence:collect_pack",)

    assert graph.branch_groups == ()
    assert graph.parallel_groups == ()


def test_fact_content_and_provenance_links_are_preserved(documents):
    graph = build_procedure_graph(parse(documents))
    stages = by_id(graph.stages, "service_id")
    facts = by_id(graph.facts, "fact_id")
    content = by_id(graph.content, "content_id")
    evidence = by_id(graph.evidence, "evidence_id")
    provenance = by_id(graph.provenance, "fact_id")

    assert stages["svc:demo_pack"].fee_fact_id == "svc:demo_pack:fee"
    assert stages["svc:demo_pack"].document_fact_ids == (
        "svc:demo_pack:document:token",
    )
    assert facts["svc:demo_pack:fee"].kind == "fee"
    assert facts["svc:demo_pack:fee"].value == 0
    assert facts["svc:demo_pack:document:token"].kind == "document"
    assert facts["svc:demo_pack:document:token"].name == "Fictional demo token"

    block = content["content:collect_pack"]
    assert block.fact_ids == ("svc:demo_pack:document:token",)
    assert block.evidence_ids == ("evidence:collect_pack",)
    assert evidence[block.evidence_ids[0]].kind == "synthetic_authored"
    assert evidence[block.evidence_ids[0]].retrieved_at is None

    assert provenance["svc:demo_pack:fee"].source_url == (
        documents[0]["provenance"]["svc:demo_pack:fee"]["source_url"]
    )
    assert graph.disclaimer == documents[1]["disclaimer"]


def test_graph_is_an_independent_immutable_snapshot(documents):
    procedure = parse(documents)
    before = procedure.model_dump(mode="json")
    graph = build_procedure_graph(procedure)

    assert procedure.model_dump(mode="json") == before

    procedure.plan.steps[0].name = "Changed after graph construction"
    procedure.enrichment.content[0].text = "Changed content"
    procedure.enrichment.actions[0].required_content_ids.clear()

    assert graph.stages[0].name == documents[0]["steps"][0]["name"]
    content = by_id(graph.content, "content_id")
    assert content["content:request_token"].text == (
        documents[1]["content"][0]["text"]
    )

    with pytest.raises(ValidationError):
        graph.stages[0].name = "Attempted graph mutation"

    with pytest.raises(ValidationError):
        graph.completeness.actions = "unknown"

    with pytest.raises(AttributeError):
        graph.actions.append(graph.actions[0])


def test_builder_revalidates_mutated_input(documents):
    procedure = parse(documents)
    procedure.enrichment.actions[0].service_id = "svc:missing"

    with pytest.raises(ProcedureInputError, match="unknown parent stage"):
        build_procedure_graph(procedure)


@pytest.mark.parametrize("selection", ["AND", "OR", "XOR"])
def test_branch_conditions_and_parallel_hyperedges_are_preserved(
    documents, selection
):
    graph = build_procedure_graph(
        parse(rich_documents(documents, selection))
    )
    actions = by_id(graph.actions, "action_id")

    group = graph.branch_groups[0]
    assert group.selection == selection
    assert tuple(option.option_id for option in group.options) == (
        "option:left",
        "option:right",
    )

    left = actions["action:left_a"]
    assert left.direct_condition_ids == ("condition:eligible",)
    assert left.applicability.condition_ids == (
        "condition:eligible",
        "condition:left_applies",
    )
    assert left.applicability.branch_group_id == "branch:choice"
    assert left.applicability.branch_option_id == "option:left"

    right = actions["action:right"]
    assert right.applicability.condition_ids == (
        "condition:eligible",
        "condition:right_applies",
    )

    parallel = graph.parallel_groups[0]
    assert parallel.action_ids == ("action:left_a", "action:left_b")
    assert parallel.evidence_ids == ("evidence:structure",)

    pairs = {
        (edge.source_id, edge.target_id)
        for edge in graph.action_prerequisites
    }
    assert ("action:left_a", "action:left_b") not in pairs
    assert ("action:left_b", "action:left_a") not in pairs
    assert len(pairs) == 4

    assert left.supplementary_content_ids == ("content:left_note",)
    assert "content:left_note" not in left.required_content_ids


def test_canonical_output_is_stable_for_unordered_input_collections(documents):
    original = rich_documents(documents)
    reordered = copy.deepcopy(original)

    for name in (
        "actions",
        "content",
        "evidence",
        "conditions",
        "prerequisites",
        "branch_groups",
        "parallel_groups",
    ):
        reordered[1][name].reverse()

    for group in reordered[1]["branch_groups"]:
        group["options"].reverse()
        for option in group["options"]:
            option["action_ids"].reverse()

    for group in reordered[1]["parallel_groups"]:
        group["action_ids"].reverse()

    first = build_procedure_graph(parse(original))
    second = build_procedure_graph(parse(reordered))

    assert first.model_dump_json() == second.model_dump_json()


def test_stage_dependencies_do_not_generate_action_prerequisites(documents):
    documents[1]["prerequisites"] = []
    graph = build_procedure_graph(parse(documents))

    assert len(graph.stage_dependencies) == 1
    assert graph.action_prerequisites == ()

    stage_index = dependency_index(graph, "stage")
    action_index = dependency_index(graph, "action")

    assert stage_index.predecessors["svc:demo_pack"] == ("svc:demo_token",)
    assert action_index.predecessors["action:collect_pack"] == ()
    assert action_index.predecessors["action:request_token"] == ()


def test_display_order_and_missing_edges_do_not_invent_structure(documents):
    documents[0]["steps"][1]["depends_on"] = []
    documents[1]["prerequisites"] = []

    graph = build_procedure_graph(parse(documents))

    assert [stage.display_order for stage in graph.stages] == [1, 2]
    assert graph.stage_dependencies == ()
    assert graph.action_prerequisites == ()
    assert graph.parallel_groups == ()

    index = dependency_index(graph, "action")
    assert index.topological_order == tuple(sorted(index.predecessors))
    assert all(not value for value in index.predecessors.values())


def test_dependency_index_contains_direct_edges_and_is_immutable(documents):
    enrichment = documents[1]
    finish = add_action(enrichment, "finish")
    enrichment["prerequisites"].append(
        {
            "prerequisite_id": "prerequisite:collect_before_finish",
            "kind": "requires_completion",
            "required_action_id": "action:collect_pack",
            "dependent_action_id": finish,
            "evidence_ids": ["evidence:finish"],
        }
    )
    enrichment["evidence"][-1]["text"] = (
        "In this fictional scenario, finish only after pack collection."
    )

    graph = build_procedure_graph(parse(documents))
    index = dependency_index(graph, "action")

    assert index.topological_order == (
        "action:request_token",
        "action:collect_pack",
        "action:finish",
    )
    assert index.predecessors["action:finish"] == ("action:collect_pack",)
    assert index.successors["action:request_token"] == ("action:collect_pack",)
    assert len(graph.action_prerequisites) == 2

    with pytest.raises(TypeError):
        index.predecessors["action:finish"] = ()

    with pytest.raises(ValueError, match="level"):
        dependency_index(graph, "combined")


def test_unknown_structure_and_missing_actions_remain_unknown(documents):
    enrichment = documents[1]
    enrichment["actions"] = enrichment["actions"][:1]
    enrichment["prerequisites"] = []
    enrichment["completeness"]["actions"] = "partial"
    enrichment["completeness"]["prerequisites"] = "unknown"
    enrichment["completeness"]["parallel_groups"] = "unknown"

    graph = build_procedure_graph(parse(documents))

    assert len(graph.stages) == 2
    assert len(graph.actions) == 1
    assert not any(
        action.service_id == "svc:demo_pack" for action in graph.actions
    )
    assert graph.action_prerequisites == ()
    assert graph.parallel_groups == ()
    assert graph.completeness.actions == "partial"
    assert graph.completeness.prerequisites == "unknown"
    assert graph.completeness.parallel_groups == "unknown"


def test_missing_and_additional_provenance_are_preserved(documents):
    plan = documents[0]
    del plan["provenance"]["svc:demo_pack:fee"]
    plan["provenance"]["svc:demo_pack:eligibility"] = {
        "source_url": "https://example.org/c4/extra-source",
        "retrieved_at": "2026-10-14T00:00:00Z",
    }

    graph = build_procedure_graph(parse(documents))
    provenance = by_id(graph.provenance, "fact_id")
    facts = by_id(graph.facts, "fact_id")

    assert "svc:demo_pack:fee" in facts
    assert "svc:demo_pack:fee" not in provenance
    assert "svc:demo_pack:eligibility" in provenance
    assert "svc:demo_pack:eligibility" not in facts


def test_source_evidence_classification_is_not_changed(documents):
    enrichment = documents[1]
    enrichment["synthetic"] = False
    enrichment["disclaimer"] = (
        "Test source metadata; authenticity is not established."
    )
    for evidence in enrichment["evidence"]:
        evidence["kind"] = "source_passage"
        evidence["retrieved_at"] = "2026-10-14T05:30:00+05:30"

    graph = build_procedure_graph(parse(documents))

    assert graph.synthetic is False
    assert all(item.kind == "source_passage" for item in graph.evidence)
    assert all(
        item.retrieved_at.isoformat() == "2026-10-14T00:00:00+00:00"
        for item in graph.evidence
    )


def test_duplicate_graph_records_are_rejected(documents):
    graph = build_procedure_graph(parse(documents))
    values = {
        name: getattr(graph, name)
        for name in type(graph).model_fields
    }
    values["actions"] = graph.actions + (graph.actions[0],)

    with pytest.raises(ValidationError, match="duplicate identifier"):
        CanonicalProcedureGraph(**values)


def test_overlapping_parallel_groups_do_not_become_one_larger_group(documents):
    enrichment = documents[1]
    first = add_action(enrichment, "first")
    middle = add_action(enrichment, "middle")
    last = add_action(enrichment, "last")

    enrichment["evidence"].append(
        {
            "evidence_id": "evidence:overlap",
            "kind": "synthetic_authored",
            "source_url": "https://example.org/c4/graph-tests/overlap",
            "text": (
                "In this fictional test, first and middle may run "
                "concurrently. Middle and last may run concurrently. "
                "No claim is supplied about first and last."
            ),
            "retrieved_at": None,
        }
    )
    enrichment["parallel_groups"] = [
        {
            "group_id": "parallel:first_middle",
            "service_id": "svc:demo_pack",
            "action_ids": [first, middle],
            "evidence_ids": ["evidence:overlap"],
        },
        {
            "group_id": "parallel:middle_last",
            "service_id": "svc:demo_pack",
            "action_ids": [middle, last],
            "evidence_ids": ["evidence:overlap"],
        },
    ]

    graph = build_procedure_graph(parse(documents))

    assert len(graph.parallel_groups) == 2
    assert all(len(group.action_ids) == 2 for group in graph.parallel_groups)
    assert len(graph.action_prerequisites) == 1