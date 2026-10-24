"""Research-relevant acceptance tests for the complete C4 input boundary."""

import copy
import json
from pathlib import Path

import pytest

from app.procedures.procedure_input import (
    ProcedureInputError,
    load_procedure_input,
    parse_procedure_input,
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
    return (
        json.loads((FIXTURES / "plan.json").read_text(encoding="utf-8")),
        json.loads((FIXTURES / "enrichment.json").read_text(encoding="utf-8")),
    )


def parse(documents):
    return parse_procedure_input(
        json.dumps(documents[0]),
        json.dumps(documents[1]),
    )


def evidence(enrichment, name, text):
    identifier = f"evidence:{name}"
    enrichment["evidence"].append(
        {
            "evidence_id": identifier,
            "kind": "synthetic_authored",
            "source_url": f"https://example.org/c4/tests/{name}",
            "text": text,
            "retrieved_at": None,
        }
    )
    return identifier


def action(enrichment, name):
    evidence_id = evidence(
        enrichment, name, f"Perform fictional preparation action {name}."
    )
    content_id = f"content:{name}"
    action_id = f"action:{name}"
    enrichment["content"].append(
        {
            "content_id": content_id,
            "role": "required",
            "text": f"Perform fictional preparation action {name}.",
            "evidence_ids": [evidence_id],
            "fact_ids": [],
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


def condition(enrichment, name):
    evidence_id = evidence(
        enrichment, name, f"Fictional condition {name} applies."
    )
    identifier = f"condition:{name}"
    enrichment["conditions"].append(
        {
            "condition_id": identifier,
            "text": f"Fictional condition {name} applies.",
            "evidence_ids": [evidence_id],
        }
    )
    return identifier


def prerequisite(enrichment, name, required, dependent):
    evidence_id = evidence(
        enrichment,
        name,
        f"In this fictional case {required} must finish before {dependent}.",
    )
    enrichment["prerequisites"].append(
        {
            "prerequisite_id": f"prerequisite:{name}",
            "kind": "requires_completion",
            "required_action_id": required,
            "dependent_action_id": dependent,
            "evidence_ids": [evidence_id],
        }
    )


def branch(enrichment, selection="XOR"):
    left = action(enrichment, "left")
    right = action(enrichment, "right")
    evidence_id = evidence(
        enrichment,
        "choice",
        f"Use the explicit {selection} rule to select fictional options.",
    )
    enrichment["branch_groups"].append(
        {
            "group_id": "branch:choice",
            "service_id": "svc:demo_pack",
            "selection": selection,
            "options": [
                {
                    "option_id": "option:left",
                    "action_ids": [left],
                    "condition_ids": [],
                },
                {
                    "option_id": "option:right",
                    "action_ids": [right],
                    "condition_ids": [],
                },
            ],
            "evidence_ids": [evidence_id],
        }
    )
    return left, right


def parallel(enrichment, members, name="preparation"):
    evidence_id = evidence(
        enrichment,
        name,
        f"These fictional actions may run concurrently: {members}.",
    )
    enrichment["parallel_groups"].append(
        {
            "group_id": f"parallel:{name}",
            "service_id": "svc:demo_pack",
            "action_ids": members,
            "evidence_ids": [evidence_id],
        }
    )


def test_linear_fixture_loads_and_preserves_data(documents):
    original = copy.deepcopy(documents)
    result = load_procedure_input(
        FIXTURES / "plan.json", FIXTURES / "enrichment.json"
    )

    assert result.plan.model_dump(mode="json") == original[0]
    assert result.enrichment.model_dump(mode="json") == original[1]
    assert result.enrichment.synthetic is True
    assert result.enrichment.evidence[0].retrieved_at is None
    assert len(result.enrichment.actions) == 2

    parse(documents)
    assert documents == original


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "2.0"),
        ("plan_id", "wrong-plan"),
        ("base_generated_at", "2026-10-15T00:00:00Z"),
        ("synthetic", "true"),
    ],
)
def test_schema_and_identity_failures(documents, field, value):
    documents[1][field] = value
    with pytest.raises(ProcedureInputError):
        parse(documents)


def test_extra_fields_and_duplicate_ids_are_rejected(documents):
    bad = copy.deepcopy(documents)
    bad[1]["unexpected"] = True
    with pytest.raises(ProcedureInputError):
        parse(bad)

    documents[1]["actions"].append(
        copy.deepcopy(documents[1]["actions"][0])
    )
    with pytest.raises(ProcedureInputError, match="duplicate"):
        parse(documents)


@pytest.mark.parametrize(
    ("collection", "field", "value"),
    [
        ("actions", "service_id", "svc:missing"),
        ("actions", "required_content_ids", ["content:missing"]),
        ("actions", "condition_ids", ["condition:missing"]),
        ("content", "evidence_ids", ["evidence:missing"]),
        ("content", "fact_ids", ["svc:demo_pack:fee:missing"]),
        ("prerequisites", "dependent_action_id", "action:missing"),
    ],
)
def test_unknown_references_are_rejected(documents, collection, field, value):
    documents[1][collection][0][field] = value
    with pytest.raises(ProcedureInputError, match="unknown"):
        parse(documents)


def test_stage_validation_and_no_dependency_inference(documents):
    bad = copy.deepcopy(documents)
    bad[0]["steps"].append(copy.deepcopy(bad[0]["steps"][0]))
    with pytest.raises(ProcedureInputError, match="duplicate"):
        parse(bad)

    bad = copy.deepcopy(documents)
    bad[0]["requested_service_id"] = "svc:missing"
    with pytest.raises(ProcedureInputError, match="requested_service_id"):
        parse(bad)

    documents[0]["steps"][1]["depends_on"] = []
    with pytest.raises(ProcedureInputError, match="stage dependency path"):
        parse(documents)


def test_stage_and_action_cycles_are_rejected(documents):
    bad = copy.deepcopy(documents)
    bad[0]["steps"][0]["depends_on"] = ["svc:demo_pack"]
    with pytest.raises(ProcedureInputError, match="cycle"):
        parse(bad)

    enrichment = documents[1]
    other = action(enrichment, "other")
    prerequisite(enrichment, "forward", "action:collect_pack", other)
    prerequisite(enrichment, "backward", other, "action:collect_pack")
    with pytest.raises(ProcedureInputError, match="cycle"):
        parse(documents)


def test_self_link_and_reversed_stage_prerequisite_are_rejected(documents):
    bad = copy.deepcopy(documents)
    edge = bad[1]["prerequisites"][0]
    edge["dependent_action_id"] = edge["required_action_id"]
    with pytest.raises(ProcedureInputError, match="self-link"):
        parse(bad)

    edge = documents[1]["prerequisites"][0]
    edge["required_action_id"] = "action:collect_pack"
    edge["dependent_action_id"] = "action:request_token"
    with pytest.raises(ProcedureInputError, match="stage dependency path"):
        parse(documents)


def test_required_and_supplementary_content_roles(documents):
    enrichment = documents[1]
    extra = copy.deepcopy(enrichment["content"][0])
    extra["content_id"] = "content:explanation"
    extra["role"] = "supplementary"
    enrichment["content"].append(extra)
    enrichment["actions"][0]["supplementary_content_ids"] = [
        "content:explanation"
    ]
    assert parse(documents).enrichment.content[-1].role == "supplementary"

    extra["role"] = "required"
    with pytest.raises(ProcedureInputError, match="wrong role"):
        parse(documents)


def test_incomplete_input_is_preserved_without_inventing_structure(documents):
    enrichment = documents[1]
    enrichment["actions"] = enrichment["actions"][:1]
    enrichment["prerequisites"] = []
    enrichment["completeness"]["actions"] = "partial"
    enrichment["completeness"]["prerequisites"] = "unknown"
    enrichment["completeness"]["parallel_groups"] = "unknown"

    result = parse(documents)
    assert result.enrichment.completeness.actions == "partial"
    assert result.enrichment.completeness.prerequisites == "unknown"
    assert result.enrichment.parallel_groups == []
    assert result.enrichment.completeness.parallel_groups == "unknown"

    enrichment["completeness"]["actions"] = "complete"
    with pytest.raises(ProcedureInputError, match="cover every"):
        parse(documents)


def test_synthetic_evidence_cannot_be_relabelled_as_official(documents):
    bad = copy.deepcopy(documents)
    bad[1]["synthetic"] = False
    with pytest.raises(ProcedureInputError, match="synthetic status"):
        parse(bad)

    documents[1]["evidence"][0]["retrieved_at"] = "2026-10-14T00:00:00Z"
    with pytest.raises(ProcedureInputError, match="retrieved_at=null"):
        parse(documents)


def test_source_passage_metadata_and_missing_provenance_are_preserved(documents):
    plan, enrichment = documents
    enrichment["synthetic"] = False
    enrichment["disclaimer"] = "Test input; authenticity is not verified."
    for item in enrichment["evidence"]:
        item["kind"] = "source_passage"
        item["retrieved_at"] = "2026-10-14T00:00:00Z"
    plan["provenance"] = {}

    result = parse(documents)
    assert result.plan.provenance == {}
    assert all(
        item.kind == "source_passage" for item in result.enrichment.evidence
    )

    enrichment["evidence"][0]["retrieved_at"] = None
    with pytest.raises(ProcedureInputError, match="needs retrieved_at"):
        parse(documents)


@pytest.mark.parametrize("selection", ["AND", "OR", "XOR"])
def test_explicit_branch_semantics_are_preserved(documents, selection):
    enrichment = documents[1]
    branch(enrichment, selection)
    guard = condition(enrichment, "eligible")
    enrichment["branch_groups"][0]["options"][0]["condition_ids"] = [guard]

    result = parse(documents)
    group = result.enrichment.branch_groups[0]
    assert group.selection == selection
    assert group.options[0].condition_ids == [guard]

    group_data = enrichment["branch_groups"][0]
    group_data["options"][1]["action_ids"] = list(
        group_data["options"][0]["action_ids"]
    )
    with pytest.raises(ProcedureInputError, match="multiple branch"):
        parse(documents)


def test_optional_branch_cannot_be_unconditional_prerequisite(documents):
    enrichment = documents[1]
    left, right = branch(enrichment)
    prerequisite(enrichment, "wrong_join", left, right)

    with pytest.raises(ProcedureInputError, match="optional branch"):
        parse(documents)


def test_conditional_prerequisite_requires_guaranteed_applicability(documents):
    enrichment = documents[1]
    required = action(enrichment, "conditional")
    dependent = action(enrichment, "dependent")
    guard = condition(enrichment, "eligible")
    enrichment["actions"][-2]["condition_ids"] = [guard]
    prerequisite(enrichment, "conditional_requirement", required, dependent)

    with pytest.raises(ProcedureInputError, match="applicability"):
        parse(documents)

    enrichment["actions"][-1]["condition_ids"] = [guard]
    parse(documents)


def test_and_branch_still_checks_conditions(documents):
    enrichment = documents[1]
    left, right = branch(enrichment, "AND")
    guard = condition(enrichment, "left_eligible")
    enrichment["branch_groups"][0]["options"][0]["condition_ids"] = [guard]
    prerequisite(enrichment, "conditional_and", left, right)

    with pytest.raises(ProcedureInputError, match="applicability"):
        parse(documents)

    enrichment["branch_groups"][0]["options"][1]["condition_ids"] = [guard]
    parse(documents)


def test_parallel_group_accepts_shared_prerequisite_but_not_indirect_order(
    documents,
):
    enrichment = documents[1]
    left = action(enrichment, "parallel_left")
    right = action(enrichment, "parallel_right")
    parallel(enrichment, [left, right])
    prerequisite(enrichment, "shared_left", "action:collect_pack", left)
    prerequisite(enrichment, "shared_right", "action:collect_pack", right)

    result = parse(documents)
    assert len(result.enrichment.parallel_groups) == 1

    middle = action(enrichment, "middle")
    prerequisite(enrichment, "left_middle", left, middle)
    prerequisite(enrichment, "middle_right", middle, right)
    with pytest.raises(ProcedureInputError, match="prerequisite path"):
        parse(documents)


def test_parallel_claim_requires_complete_information(documents):
    enrichment = documents[1]
    left = action(enrichment, "parallel_left")
    right = action(enrichment, "parallel_right")
    parallel(enrichment, [left, right])
    enrichment["completeness"]["prerequisites"] = "unknown"

    with pytest.raises(ProcedureInputError, match="require complete"):
        parse(documents)


def test_parallel_members_must_have_compatible_applicability(documents):
    enrichment = documents[1]
    left, right = branch(enrichment)
    parallel(enrichment, [left, right])

    with pytest.raises(ProcedureInputError, match="incompatible applicability"):
        parse(documents)

    group = enrichment["branch_groups"][0]
    third = action(enrichment, "third")
    group["options"][0]["action_ids"].append(third)
    enrichment["parallel_groups"][0]["action_ids"] = [left, third]
    parse(documents)


def test_no_parallelism_is_inferred_and_overlap_does_not_merge_groups(documents):
    enrichment = documents[1]
    left = action(enrichment, "left")
    middle = action(enrichment, "middle")
    right = action(enrichment, "right")

    assert parse(documents).enrichment.parallel_groups == []

    parallel(enrichment, [left, middle], "left_middle")
    parallel(enrichment, [middle, right], "middle_right")
    result = parse(documents)

    assert len(result.enrichment.parallel_groups) == 2
    assert all(
        set(group.action_ids) != {left, middle, right}
        for group in result.enrichment.parallel_groups
    )


def test_realistic_file_and_json_failures(tmp_path, documents):
    with pytest.raises(ProcedureInputError, match="cannot read"):
        load_procedure_input(tmp_path / "missing.json", FIXTURES / "enrichment.json")

    enrichment_json = json.dumps(documents[1])
    with pytest.raises(ProcedureInputError, match="invalid JSON"):
        parse_procedure_input('{"plan_id":', enrichment_json)

    with pytest.raises(ProcedureInputError, match="duplicate object key"):
        parse_procedure_input(
            '{"plan_id":"first","plan_id":"second"}',
            enrichment_json,
        )


def test_existing_stub_fee_and_warning_contract(client, example):
    response = client.post(
        "/v1/render",
        json={
            "session_id": "anon-c4-regression",
            "plan": example("plan"),
            "trust": [example("trust")],
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["mode"] == "standard"
    assert result["detail_level"] == "medium"
    assert result["steps"][0]["fee_display"] == "Free"
    assert result["steps"][1]["fee_display"] == "LKR 11,000"
    assert result["steps"][1]["warning"] == (
        "Some citizens have reported this fee may have changed."
    )


def test_plan_provenance_rejects_non_web_sources(documents):
    plan, enrichment = documents

    # Exercise non-synthetic input so the example-domain restriction
    # cannot hide a failure to enforce HTTP/HTTPS.
    enrichment["synthetic"] = False
    for item in enrichment["evidence"]:
        item["kind"] = "source_passage"
        item["retrieved_at"] = "2026-10-14T00:00:00Z"

    source = next(iter(plan["provenance"].values()))
    source["source_url"] = "javascript:alert(1)"

    with pytest.raises(ProcedureInputError, match="HTTP"):
        parse(documents)