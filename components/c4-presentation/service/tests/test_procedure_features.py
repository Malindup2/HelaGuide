"""Research-facing invariants for the seven structural features."""

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.procedures.procedure_features import (
    extract_structural_features,
    lexical_units,
)
from app.procedures.procedure_graph import build_procedure_graph
from app.procedures.procedure_input import parse_procedure_input
from app.models.procedure_features import (
    FEATURE_NAMES,
    FeatureMeasurement,
    NormalizationScales,
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
        json.loads(
            (FIXTURES / "plan.json").read_text(encoding="utf-8-sig")
        ),
        json.loads(
            (FIXTURES / "enrichment.json").read_text(
                encoding="utf-8-sig"
            )
        ),
    )


def graph_from(documents):
    return build_procedure_graph(
        parse_procedure_input(
            json.dumps(documents[0]),
            json.dumps(documents[1]),
        )
    )


def add_action(enrichment, name):
    """Add a fictional action reusing the supplied pack content.

    Shared content is intentional: the feature counts content IDs once,
    while separately counting each action.
    """
    action = copy.deepcopy(enrichment["actions"][1])
    action["action_id"] = f"action:{name}"
    action["condition_ids"] = []
    enrichment["actions"].append(action)
    return action["action_id"]


def add_edge(enrichment, name, source, target):
    enrichment["prerequisites"].append(
        {
            "prerequisite_id": f"prerequisite:{name}",
            "kind": "requires_completion",
            "required_action_id": source,
            "dependent_action_id": target,
            "evidence_ids": ["evidence:structure"],
        }
    )


def add_structure_evidence(enrichment, text):
    enrichment["evidence"].append(
        {
            "evidence_id": "evidence:structure",
            "kind": "synthetic_authored",
            "source_url": "https://example.org/c4/feature-tests",
            "text": text,
            "retrieved_at": None,
        }
    )


def branching_documents(documents, selection):
    plan, enrichment = copy.deepcopy(documents)

    add_structure_evidence(
        enrichment,
        (
            "Authored fictional measurement scenario. Added actions "
            "repeat demo pack collection. Token collection precedes "
            "all pack actions. The left option contains collect_pack "
            "and left; these may proceed concurrently. The right "
            "option contains right. Each option has its stated "
            f"condition. Group selection is {selection}."
        ),
    )

    left = add_action(enrichment, "left")
    right = add_action(enrichment, "right")

    add_edge(
        enrichment,
        "token_before_left",
        "action:request_token",
        left,
    )
    add_edge(
        enrichment,
        "token_before_right",
        "action:request_token",
        right,
    )

    enrichment["conditions"] = [
        {
            "condition_id": "condition:left",
            "text": "Left option applies.",
            "evidence_ids": ["evidence:structure"],
        },
        {
            "condition_id": "condition:right",
            "text": "Right option applies.",
            "evidence_ids": ["evidence:structure"],
        },
    ]

    enrichment["branch_groups"] = [
        {
            "group_id": "branch:choice",
            "service_id": "svc:demo_pack",
            "selection": selection,
            "options": [
                {
                    "option_id": "option:left",
                    "action_ids": ["action:collect_pack", left],
                    "condition_ids": ["condition:left"],
                },
                {
                    "option_id": "option:right",
                    "action_ids": [right],
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
            "action_ids": ["action:collect_pack", left],
            "evidence_ids": ["evidence:structure"],
        }
    ]

    return plan, enrichment


def test_linear_fixture_has_hand_calculated_measurements(documents):
    graph = graph_from(documents)
    result = extract_structural_features(graph)

    assert tuple(
        item.observed for item in result.ordered_measurements()
    ) == (2, 46, 0, 0, 1, 1, 0)

    # 18 stage-label units + 21 required-content units + 7 fact units.
    info = result.diagnostics.information
    assert info.stage_label_units == 18
    assert info.required_content_units == 21
    assert info.supplementary_content_units == 0
    assert info.condition_units == 0
    assert info.fact_units == 7
    assert info.total == 46

    assert all(
        item.completeness == "complete"
        and item.exact_value == item.observed
        for item in result.ordered_measurements()
    )
    assert result.diagnostics.stage_count == 2
    assert result.diagnostics.observed_stage_dependency_count == 1
    assert result.diagnostics.observed_stage_dependency_depth == 1

    assert result.synthetic is True
    assert result.disclaimer == graph.disclaimer
    assert result.source_completeness == graph.completeness


def test_action_and_stage_dependency_layers_are_not_added(documents):
    documents[1]["prerequisites"] = []

    result = extract_structural_features(graph_from(documents))

    assert result.step_count.exact_value == 2
    assert result.dependency_count.exact_value == 0
    assert result.dependency_depth.exact_value == 0
    assert result.diagnostics.observed_stage_dependency_count == 1
    assert result.diagnostics.observed_stage_dependency_depth == 1
    assert result.parallel_group_count.exact_value == 0


def test_information_counts_references_once_and_excludes_source_text(
    documents,
):
    baseline = extract_structural_features(graph_from(documents))

    enrichment = documents[1]

    # A second reference does not duplicate the content's contribution.
    enrichment["actions"][1]["required_content_ids"].append(
        "content:request_token"
    )

    # Unreferenced content and source quotation length are excluded.
    enrichment["content"].append(
        {
            "content_id": "content:unused",
            "role": "supplementary",
            "text": "Unused material " * 100,
            "evidence_ids": ["evidence:request_token"],
            "fact_ids": [],
        }
    )
    enrichment["evidence"][0]["text"] += " Additional source text." * 100

    result = extract_structural_features(graph_from(documents))
    assert result.information_volume.observed == baseline.information_volume.observed
    assert result.diagnostics.referenced_content_count == 2
    assert result.diagnostics.unreferenced_content_count == 1

    # Once referenced, the supplementary block contributes exactly its
    # 200 lexical units, even when two actions reference it.
    for action in enrichment["actions"]:
        action["supplementary_content_ids"] = ["content:unused"]

    referenced = extract_structural_features(graph_from(documents))
    assert referenced.information_volume.observed == 246
    assert referenced.diagnostics.information.supplementary_content_units == 200
    assert referenced.diagnostics.referenced_content_count == 3
    assert referenced.diagnostics.unreferenced_content_count == 0


@pytest.mark.parametrize("selection", ["AND", "OR", "XOR"])
def test_explicit_groups_and_shared_conditions_are_counted_once(
    documents, selection
):
    graph = graph_from(branching_documents(documents, selection))
    result = extract_structural_features(graph)

    assert result.step_count.exact_value == 4
    assert result.branch_count.exact_value == 1
    assert result.condition_count.exact_value == 2
    assert result.parallel_group_count.exact_value == 1
    assert result.dependency_count.exact_value == 3
    assert result.dependency_depth.exact_value == 1

    # Required content is shared by the added actions. Only the two
    # referenced condition texts add six units to the linear input.
    assert result.information_volume.exact_value == 52
    assert result.diagnostics.information.condition_units == 6
    assert result.diagnostics.branch_option_count == 2

    assert result.diagnostics.and_group_count == int(selection == "AND")
    assert result.diagnostics.or_group_count == int(selection == "OR")
    assert result.diagnostics.xor_group_count == int(selection == "XOR")


def test_depth_is_longest_edge_path_not_node_count_or_edge_count(
    documents,
):
    enrichment = documents[1]
    add_structure_evidence(
        enrichment,
        (
            "Fictional chain: request_token, collect_pack, middle, finish. "
            "Each action must follow its predecessor. A direct requirement "
            "also states that request_token must precede finish. "
            "Added actions repeat the fictional pack collection content."
        ),
    )
    middle = add_action(enrichment, "middle")
    finish = add_action(enrichment, "finish")

    add_edge(
        enrichment, "collect_middle", "action:collect_pack", middle
    )
    add_edge(enrichment, "middle_finish", middle, finish)
    add_edge(
        enrichment, "token_finish", "action:request_token", finish
    )

    result = extract_structural_features(graph_from(documents))

    assert result.step_count.exact_value == 4
    assert result.dependency_count.exact_value == 4
    assert result.dependency_depth.exact_value == 3
    assert result.diagnostics.observed_stage_dependency_count == 1


def test_unknown_empty_actions_do_not_fall_back_to_stages(documents):
    enrichment = documents[1]
    enrichment["actions"] = []
    enrichment["prerequisites"] = []
    for field in enrichment["completeness"]:
        enrichment["completeness"][field] = "unknown"

    result = extract_structural_features(graph_from(documents))

    assert result.step_count.observed == 0
    assert result.step_count.exact_value is None
    assert result.dependency_depth.observed == 0
    assert result.dependency_depth.exact_value is None

    # Stage labels and structured facts still exist; action text is now
    # unreferenced. The 25 observed units do not claim total completeness.
    assert result.information_volume.observed == 25
    assert result.information_volume.exact_value is None
    assert result.diagnostics.stage_count == 2
    assert result.diagnostics.unreferenced_content_count == 2

    assert all(
        item.completeness == "unknown"
        and item.exact_value is None
        and item.normalized_exact is None
        for item in result.ordered_measurements()
    )

    encoded = dict(result.context_encoding())
    assert encoded["step_count.normalized_observed"] == 0.0
    assert encoded["step_count.is_unknown"] == 1.0
    assert encoded["step_count.is_complete"] == 0.0


def test_partial_structure_retains_observations_without_exact_claims(
    documents,
):
    enrichment = documents[1]
    enrichment["actions"] = enrichment["actions"][:1]
    enrichment["prerequisites"] = []
    enrichment["completeness"]["actions"] = "partial"
    enrichment["completeness"]["content"] = "partial"
    enrichment["completeness"]["prerequisites"] = "unknown"

    result = extract_structural_features(graph_from(documents))

    assert result.step_count.observed == 1
    assert result.step_count.completeness == "partial"
    assert result.step_count.exact_value is None
    assert result.information_volume.observed == 30
    assert result.information_volume.completeness == "partial"

    # Unknown is not weakened into partial when flags are combined.
    assert result.dependency_count.completeness == "unknown"
    assert result.dependency_depth.completeness == "unknown"

    # An empty group collection is not a proven zero when the action
    # coverage needed to interpret the whole procedure is incomplete.
    assert result.branch_count.observed == 0
    assert result.branch_count.completeness == "partial"
    assert result.branch_count.exact_value is None


def test_unreferenced_conditions_do_not_inflate_measurements(documents):
    enrichment = documents[1]
    enrichment["conditions"].append(
        {
            "condition_id": "condition:unused",
            "text": "This unattached condition is not part of applicability.",
            "evidence_ids": ["evidence:request_token"],
        }
    )

    result = extract_structural_features(graph_from(documents))

    assert result.condition_count.exact_value == 0
    assert result.information_volume.exact_value == 46
    assert result.diagnostics.unreferenced_condition_count == 1


def test_overlapping_parallel_groups_are_not_merged(documents):
    enrichment = documents[1]
    add_structure_evidence(
        enrichment,
        (
            "Fictional additional pack actions: first, middle and last. "
            "First and middle may proceed concurrently. Middle and last "
            "may proceed concurrently. No other parallel claim is made."
        ),
    )
    first = add_action(enrichment, "first")
    middle = add_action(enrichment, "middle")
    last = add_action(enrichment, "last")

    enrichment["parallel_groups"] = [
        {
            "group_id": "parallel:first_middle",
            "service_id": "svc:demo_pack",
            "action_ids": [first, middle],
            "evidence_ids": ["evidence:structure"],
        },
        {
            "group_id": "parallel:middle_last",
            "service_id": "svc:demo_pack",
            "action_ids": [middle, last],
            "evidence_ids": ["evidence:structure"],
        },
    ]

    result = extract_structural_features(graph_from(documents))

    assert result.parallel_group_count.exact_value == 2
    assert result.dependency_count.exact_value == 1
    assert result.dependency_depth.exact_value == 1


def test_lexical_rule_is_unicode_aware_and_normalization_stable():
    assert lexical_units("Request a fictional demo token.") == 5
    assert lexical_units("alpha-beta") == 2
    assert lexical_units("alpha   \n beta") == 2
    assert lexical_units("café") == lexical_units("cafe\u0301") == 1
    assert lexical_units("සිංහල தமிழ்") == 2
    assert lexical_units("... \u0301 !!!") == 0


def test_normalization_is_fixed_monotonic_and_records_uncertainty(
    documents,
):
    graph = graph_from(documents)
    scales = NormalizationScales(step_count=2.0)
    result = extract_structural_features(graph, scales=scales)

    assert result.step_count.scale == 2.0
    assert result.step_count.normalized_exact == 0.5
    assert result.step_count.observed == 2

    small = FeatureMeasurement(
        observed=1, completeness="complete", scale=2.0
    )
    large = FeatureMeasurement(
        observed=1000, completeness="partial", scale=2.0
    )
    assert 0 < small.normalized_observed < large.normalized_observed < 1
    assert large.normalized_exact is None
    assert large.exact_value is None

    encoded = result.context_encoding()
    assert len(encoded) == 28
    assert len(dict(encoded)) == 28
    assert tuple(name for name, _ in encoded[::4]) == tuple(
        f"{name}.normalized_observed" for name in FEATURE_NAMES
    )
    for name in FEATURE_NAMES:
        values = dict(encoded)
        assert sum(
            values[f"{name}.is_{state}"]
            for state in ("complete", "partial", "unknown")
        ) == 1.0

    with pytest.raises(ValidationError):
        NormalizationScales(step_count=0.0)
    with pytest.raises(ValidationError):
        NormalizationScales(information_volume=float("inf"))


def test_extraction_is_deterministic_immutable_and_exportable(documents):
    graph = graph_from(documents)
    before = graph.model_dump_json()

    first = extract_structural_features(graph)
    second = extract_structural_features(graph)

    assert graph.model_dump_json() == before
    assert first.model_dump_json() == second.model_dump_json()

    exported = json.loads(first.model_dump_json())
    assert exported["step_count"]["exact_value"] == 2
    assert exported["information_volume"]["observed"] == 46
    assert exported["synthetic"] is True
    assert exported["measurement_version"] == "c4-structural-1.0"
    assert exported["unicode_data_version"]

    with pytest.raises(ValidationError):
        first.step_count.observed = 999

    reordered = copy.deepcopy(documents)
    for field in ("actions", "content", "evidence", "prerequisites"):
        reordered[1][field].reverse()

    reordered_result = extract_structural_features(
        graph_from(reordered)
    )
    assert first.model_dump_json() == reordered_result.model_dump_json()