"""Deterministic structural features from a validated canonical graph.

Counting scope:
- Actions, not stages, define step_count.
- Only explicit action prerequisites define dependency_count and depth.
- Branch and parallel groups remain explicit groups.
- Information volume is measured before generation or rendering.

Use graphs produced by build_procedure_graph(). This module is not a
replacement for the semantic input validation boundary.
"""

import unicodedata

from app.procedures.procedure_graph import DependencyIndex, dependency_index
from app.models.procedure import Completeness
from app.models.procedure_features import (
    FeatureDiagnostics,
    FeatureMeasurement,
    InformationBreakdown,
    NormalizationScales,
    StructuralFeatures,
)
from app.models.procedure_graph import CanonicalProcedureGraph


def lexical_units(text: str) -> int:
    """Count NFC-normalized Unicode letter/mark/number runs.

    A run contributes one unit only if it contains a letter or number.
    Combining marks stay attached to a run. Punctuation, whitespace and
    other categories separate runs.

    This is a language-independent lexical proxy, not linguistic word
    segmentation or an LLM token count.
    """
    count = 0
    run_has_letter_or_number = False

    for character in unicodedata.normalize("NFC", text):
        category = unicodedata.category(character)[0]

        if category in {"L", "N", "M"}:
            if category in {"L", "N"}:
                run_has_letter_or_number = True
        else:
            if run_has_letter_or_number:
                count += 1
            run_has_letter_or_number = False

    if run_has_letter_or_number:
        count += 1

    return count


def _combined_completeness(
    *states: Completeness,
) -> Completeness:
    if "unknown" in states:
        return "unknown"
    if "partial" in states:
        return "partial"
    return "complete"


def _longest_path_edges(index: DependencyIndex) -> int:
    """Longest path in a DAG, measured in edges.

    Uses the existing validated topological index. The dynamic-programming
    pass is O(V + E); it neither enumerates paths nor adds implied edges.
    """
    depths: dict[str, int] = {}

    for node_id in index.topological_order:
        depths[node_id] = max(
            (
                depths[predecessor] + 1
                for predecessor in index.predecessors[node_id]
            ),
            default=0,
        )

    return max(depths.values(), default=0)


def extract_structural_features(
    graph: CanonicalProcedureGraph,
    *,
    scales: NormalizationScales | None = None,
) -> StructuralFeatures:
    """Measure an immutable graph produced by build_procedure_graph().

    Observations are always retained. Incomplete observations are not
    exposed as exact values. No branch selection, condition evaluation,
    parallel inference or stage-to-action expansion occurs here.
    """
    if not isinstance(graph, CanonicalProcedureGraph):
        raise TypeError("graph must be a CanonicalProcedureGraph")

    if scales is None:
        scales = NormalizationScales()
    elif not isinstance(scales, NormalizationScales):
        raise TypeError("scales must be NormalizationScales or None")

    action_index = dependency_index(graph, "action")
    stage_index = dependency_index(graph, "stage")

    content_by_id = {item.content_id: item for item in graph.content}
    condition_by_id = {
        item.condition_id: item for item in graph.conditions
    }
    fact_by_id = {item.fact_id: item for item in graph.facts}

    required_ids = {
        content_id
        for action in graph.actions
        for content_id in action.required_content_ids
    }
    supplementary_ids = {
        content_id
        for action in graph.actions
        for content_id in action.supplementary_content_ids
    }
    content_ids = required_ids | supplementary_ids

    # Effective applicability includes direct and option-level conditions.
    # Option references are included explicitly as well: selection
    # conditions belong to the procedure even before a branch is selected.
    condition_ids = {
        condition_id
        for action in graph.actions
        for condition_id in action.applicability.condition_ids
    }
    condition_ids.update(
        condition_id
        for group in graph.branch_groups
        for option in group.options
        for condition_id in option.condition_ids
    )

    fact_ids = {stage.fee_fact_id for stage in graph.stages}
    fact_ids.update(
        fact_id
        for stage in graph.stages
        for fact_id in stage.document_fact_ids
    )

    # Guard the references used by this extractor. Complete relationship
    # validation remains the responsibility of the existing 1A/1B boundary.
    for label, referenced_ids, table in (
        ("content", content_ids, content_by_id),
        ("condition", condition_ids, condition_by_id),
        ("fact", fact_ids, fact_by_id),
    ):
        missing = referenced_ids - table.keys()
        if missing:
            raise ValueError(
                f"graph contains unknown {label} references: "
                f"{sorted(missing)}"
            )

    if required_ids & supplementary_ids:
        raise ValueError(
            "graph assigns the same content as required and supplementary"
        )

    for content_id in required_ids:
        if content_by_id[content_id].role != "required":
            raise ValueError(
                f"content '{content_id}' has an inconsistent required role"
            )
    for content_id in supplementary_ids:
        if content_by_id[content_id].role != "supplementary":
            raise ValueError(
                f"content '{content_id}' has an inconsistent supplementary role"
            )

    for content_id in content_ids:
        fact_ids.update(content_by_id[content_id].fact_ids)

    missing_facts = fact_ids - fact_by_id.keys()
    if missing_facts:
        raise ValueError(
            f"graph contains unknown fact references: {sorted(missing_facts)}"
        )

    fact_units = 0
    for fact_id in sorted(fact_ids):
        fact = fact_by_id[fact_id]
        if fact.kind == "document":
            fact_units += lexical_units(fact.name)
        else:
            # The numeric amount is one structured scalar unit regardless
            # of its magnitude, decimal formatting or whether it is zero.
            fact_units += 1 + lexical_units(fact.currency)

    information = InformationBreakdown(
        stage_label_units=sum(
            lexical_units(stage.name) + lexical_units(stage.agency)
            for stage in graph.stages
        ),
        required_content_units=sum(
            lexical_units(content_by_id[item_id].text)
            for item_id in sorted(required_ids)
        ),
        supplementary_content_units=sum(
            lexical_units(content_by_id[item_id].text)
            for item_id in sorted(supplementary_ids)
        ),
        condition_units=sum(
            lexical_units(condition_by_id[item_id].text)
            for item_id in sorted(condition_ids)
        ),
        fact_units=fact_units,
    )

    completeness = graph.completeness

    action_status = completeness.actions
    information_status = _combined_completeness(
        completeness.actions,
        completeness.content,
        completeness.conditions,
        completeness.branch_groups,
    )
    branch_status = _combined_completeness(
        completeness.actions,
        completeness.branch_groups,
    )
    condition_status = _combined_completeness(
        completeness.actions,
        completeness.conditions,
        completeness.branch_groups,
    )
    dependency_status = _combined_completeness(
        completeness.actions,
        completeness.prerequisites,
    )
    parallel_status = _combined_completeness(
        completeness.actions,
        completeness.parallel_groups,
    )

    def measurement(
        name: str,
        observed: int,
        status: Completeness,
    ) -> FeatureMeasurement:
        return FeatureMeasurement(
            observed=observed,
            completeness=status,
            scale=getattr(scales, name),
        )

    return StructuralFeatures(
        unicode_data_version=unicodedata.unidata_version,
        graph_schema_version=graph.graph_schema_version,
        plan_id=graph.plan_id,
        requested_service_id=graph.requested_service_id,
        generated_at=graph.generated_at,
        synthetic=graph.synthetic,
        disclaimer=graph.disclaimer,
        source_completeness=completeness,
        step_count=measurement(
            "step_count", len(graph.actions), action_status
        ),
        information_volume=measurement(
            "information_volume", information.total, information_status
        ),
        branch_count=measurement(
            "branch_count", len(graph.branch_groups), branch_status
        ),
        condition_count=measurement(
            "condition_count", len(condition_ids), condition_status
        ),
        dependency_count=measurement(
            "dependency_count",
            len(graph.action_prerequisites),
            dependency_status,
        ),
        dependency_depth=measurement(
            "dependency_depth",
            _longest_path_edges(action_index),
            dependency_status,
        ),
        parallel_group_count=measurement(
            "parallel_group_count",
            len(graph.parallel_groups),
            parallel_status,
        ),
        diagnostics=FeatureDiagnostics(
            stage_count=len(graph.stages),
            observed_stage_dependency_count=len(
                graph.stage_dependencies
            ),
            observed_stage_dependency_depth=_longest_path_edges(
                stage_index
            ),
            and_group_count=sum(
                group.selection == "AND"
                for group in graph.branch_groups
            ),
            or_group_count=sum(
                group.selection == "OR"
                for group in graph.branch_groups
            ),
            xor_group_count=sum(
                group.selection == "XOR"
                for group in graph.branch_groups
            ),
            branch_option_count=sum(
                len(group.options) for group in graph.branch_groups
            ),
            referenced_content_count=len(content_ids),
            referenced_fact_count=len(fact_ids),
            unreferenced_content_count=len(
                content_by_id.keys() - content_ids
            ),
            unreferenced_condition_count=len(
                condition_by_id.keys() - condition_ids
            ),
            information=information,
        ),
    )