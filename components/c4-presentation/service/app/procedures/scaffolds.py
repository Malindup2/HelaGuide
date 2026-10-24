"""Deterministic catalogue and hard feasibility for C4 scaffolds.

Input graphs must come from build_procedure_graph(). Feature inputs must
come from extract_structural_features().

This module does not select a learned action, resolve branch choices,
mark actions completed, generate text or render a user interface.
"""

import hashlib
import json
from itertools import product

from app.procedures.procedure_features import extract_structural_features
from app.models.procedure_features import (
    FEATURE_NAMES,
    NormalizationScales,
    StructuralFeatures,
)
from app.models.procedure_graph import CanonicalProcedureGraph
from app.models.scaffolds import (
    ConfigurationDecision,
    ContentSafety,
    FeasibilityContext,
    FeasibilityResult,
    Notice,
    PresentationItem,
    PreservationContract,
    Reason,
    ScaffoldConfiguration,
    VisibilityDeclaration,
)


DIMENSIONS = (
    "presentation_mode",
    "progressive_disclosure",
    "previous_context_recap",
    "relationship_visual",
    "prerequisite_cue",
)


def enumerate_scaffolds() -> tuple[ScaffoldConfiguration, ...]:
    """Return all 64 configurations in stable catalogue order."""
    return tuple(
        ScaffoldConfiguration(
            presentation_mode=mode,
            progressive_disclosure=disclosure,
            previous_context_recap=recap,
            relationship_visual=visual,
            prerequisite_cue=cue,
        )
        for mode, disclosure, recap, visual, cue in product(
            ("OVERVIEW", "GUIDED"),
            (False, True),
            (False, True),
            ("NONE", "BRANCH_MAP", "DEPENDENCY_MAP", "PARALLEL_MAP"),
            (False, True),
        )
    )


def graph_fingerprint(graph: CanonicalProcedureGraph) -> str:
    """Identify the exact canonical graph snapshot, including content."""
    encoded = json.dumps(
        graph.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _reason(code: str, message: str) -> Reason:
    return Reason(code=code, message=message)


def _unique(values, label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} contains duplicate identifiers")


def _validate_features(
    graph: CanonicalProcedureGraph,
    features: StructuralFeatures,
) -> None:
    """Check all seven measurements, diagnostics and metadata."""
    if not isinstance(features, StructuralFeatures):
        raise TypeError("features must be StructuralFeatures")

    scales = NormalizationScales(
        **{
            name: getattr(features, name).scale
            for name in FEATURE_NAMES
        }
    )
    expected = extract_structural_features(graph, scales=scales)
    if features != expected:
        raise ValueError(
            "features do not match the supplied graph; extract them again"
        )


def _notices(graph, safety) -> tuple[Notice, ...]:
    _unique(
        [warning.notice_id for warning in safety.warnings],
        "warning IDs",
    )
    if any(
        warning.notice_id.startswith("c4:")
        for warning in safety.warnings
    ):
        raise ValueError("warning IDs beginning with 'c4:' are reserved")

    notices = [
        Notice(
            notice_id="c4:disclaimer",
            text=graph.disclaimer,
        ),
        Notice(
            notice_id="c4:source_status",
            text=(
                "Synthetic research data; not official procedural guidance."
                if graph.synthetic
                else (
                    "Supplied source passages and provenance are retained. "
                    "This engine has not independently authenticated them."
                )
            ),
        ),
    ]

    incomplete = [
        f"{name}={value}"
        for name, value in graph.completeness.model_dump().items()
        if value != "complete"
    ]
    if incomplete:
        notices.append(
            Notice(
                notice_id="c4:incomplete_structure",
                text=(
                    "Some procedure structure is incomplete: "
                    + ", ".join(sorted(incomplete))
                    + ". Missing relationships must not be assumed absent."
                ),
            )
        )

    provenance_ids = {item.fact_id for item in graph.provenance}
    missing = sorted(
        item.fact_id
        for item in graph.facts
        if item.fact_id not in provenance_ids
    )
    if missing:
        notices.append(
            Notice(
                notice_id="c4:missing_provenance",
                text=(
                    "Source provenance is unavailable for these supplied "
                    "facts: " + ", ".join(missing)
                ),
            )
        )

    notices.extend(safety.warnings)
    return tuple(sorted(notices, key=lambda item: item.notice_id))


def _preservation_contract(
    graph,
    safety,
    fingerprint,
    notices,
) -> PreservationContract:
    content = {item.content_id: item for item in graph.content}
    supplementary_refs = {
        content_id
        for action in graph.actions
        for content_id in action.supplementary_content_ids
    }

    _unique(safety.warning_content_ids, "warning content IDs")
    unknown_warnings = set(safety.warning_content_ids) - content.keys()
    if unknown_warnings:
        raise ValueError(
            f"unknown warning content IDs: {sorted(unknown_warnings)}"
        )

    approved = set()
    review = safety.disclosure_review
    if review is not None:
        if review.graph_fingerprint != fingerprint:
            raise ValueError("disclosure review belongs to another graph snapshot")
        _unique(review.safe_content_ids, "reviewed content IDs")

        for content_id in review.safe_content_ids:
            block = content.get(content_id)
            if (
                block is None
                or block.role != "supplementary"
                or content_id not in supplementary_refs
            ):
                raise ValueError(
                    f"reviewed content '{content_id}' must be referenced "
                    "supplementary content"
                )
            if content_id in safety.warning_content_ids:
                raise ValueError(
                    f"warning content '{content_id}' cannot be collapsible"
                )
            if block.fact_ids:
                raise ValueError(
                    f"fact-linked content '{content_id}' cannot be collapsible"
                )
            approved.add(content_id)

    items = []

    tables = (
        ("stage", graph.stages, "service_id"),
        ("action", graph.actions, "action_id"),
        ("content", graph.content, "content_id"),
        ("fact", graph.facts, "fact_id"),
        ("condition", graph.conditions, "condition_id"),
        ("branch_group", graph.branch_groups, "group_id"),
        ("parallel_group", graph.parallel_groups, "group_id"),
        ("stage_dependency", graph.stage_dependencies, "edge_id"),
        ("action_prerequisite", graph.action_prerequisites, "edge_id"),
        ("evidence", graph.evidence, "evidence_id"),
        ("provenance", graph.provenance, "fact_id"),
        ("notice", notices, "notice_id"),
    )

    for kind, records, id_field in tables:
        for record in records:
            identifier = getattr(record, id_field)
            if kind == "content" and identifier in approved:
                continue
            items.append(
                PresentationItem(kind=kind, identifier=identifier)
            )

    return PreservationContract(
        always_visible=tuple(
            sorted(items, key=lambda item: (item.kind, item.identifier))
        ),
        collapsible_content_ids=tuple(sorted(approved)),
    )



def prepare_source_preservation(
    graph: CanonicalProcedureGraph,
    safety: ContentSafety | None = None,
) -> tuple[tuple[Notice, ...], PreservationContract]:
    """Preserve source records without measuring or selecting scaffolds."""
    if not isinstance(graph, CanonicalProcedureGraph):
        raise TypeError("graph must be CanonicalProcedureGraph")
    safety = safety if safety is not None else ContentSafety()
    fingerprint = graph_fingerprint(graph)
    notices = _notices(graph, safety)
    preservation = _preservation_contract(
        graph, safety, fingerprint, notices
    )
    return notices, preservation


def _recap_actions(context, fingerprint, graph) -> tuple[str, ...]:
    """Retain matching exposure only; never infer completed actions."""
    if context.session_id is None:
        return ()

    known = {action.action_id for action in graph.actions}
    exposed = set()
    for event in context.history:
        if (
            event.session_id != context.session_id
            or event.graph_fingerprint != fingerprint
        ):
            continue

        _unique(event.action_ids, "history action IDs")
        unknown = set(event.action_ids) - known
        if unknown:
            raise ValueError(
                f"matching history has unknown actions: {sorted(unknown)}"
            )
        exposed.update(event.action_ids)

    return tuple(sorted(exposed))


def _baseline_key(configuration):
    """A deterministic conservative preference, constrained by feasibility."""
    visual_rank = {
        "NONE": 0,
        "DEPENDENCY_MAP": 1,
        "BRANCH_MAP": 2,
        "PARALLEL_MAP": 3,
    }
    return (
        configuration.presentation_mode != "OVERVIEW",
        configuration.progressive_disclosure,
        configuration.previous_context_recap,
        visual_rank[configuration.relationship_visual],
        configuration.prerequisite_cue,
        configuration.configuration_id,
    )


def filter_scaffolds(
    graph: CanonicalProcedureGraph,
    features: StructuralFeatures,
    *,
    context: FeasibilityContext | None = None,
    safety: ContentSafety | None = None,
) -> FeasibilityResult:
    """Evaluate all 64 configurations against one immutable snapshot.

    Returns accepted candidates, per-configuration explanations, a baseline
    when possible, and preservation obligations for downstream composition.

    Input/context errors raise ValueError. Valid but conflicting locks
    produce an empty feasible set rather than being silently relaxed.
    """
    if not isinstance(graph, CanonicalProcedureGraph):
        raise TypeError("graph must be CanonicalProcedureGraph")
    if context is None:
        context = FeasibilityContext()
    elif not isinstance(context, FeasibilityContext):
        raise TypeError("context must be FeasibilityContext")
    if safety is None:
        safety = ContentSafety()
    elif not isinstance(safety, ContentSafety):
        raise TypeError("safety must be ContentSafety")

    _validate_features(graph, features)

    fingerprint = graph_fingerprint(graph)
    notices = _notices(graph, safety)
    preservation = _preservation_contract(
        graph, safety, fingerprint, notices
    )
    recap_actions = _recap_actions(context, fingerprint, graph)

    completeness = graph.completeness

    def complete(*names):
        return all(
            getattr(completeness, name) == "complete"
            for name in names
        )

    guided_supported = (
        all(
            value == "complete"
            for value in completeness.model_dump().values()
        )
        and (features.step_count.exact_value or 0) > 0
        and (features.information_volume.exact_value or 0) > 0
    )

    branch_supported = (
        bool(graph.branch_groups)
        and features.branch_count.completeness == "complete"
        and features.branch_count.observed > 0
        and features.condition_count.completeness == "complete"
        and complete("actions", "branch_groups", "conditions")
    )

    dependency_layers = []
    if graph.stage_dependencies and complete("service_dependencies"):
        dependency_layers.append("stage")

    if (
        graph.action_prerequisites
        and features.dependency_count.completeness == "complete"
        and features.dependency_count.observed > 0
        and features.dependency_depth.completeness == "complete"
        and features.dependency_depth.observed > 0
        and features.condition_count.completeness == "complete"
        and features.branch_count.completeness == "complete"
        and complete(
            "actions",
            "prerequisites",
            "service_dependencies",
            "conditions",
            "branch_groups",
        )
    ):
        dependency_layers.append("action")

    parallel_supported = (
        bool(graph.parallel_groups)
        and features.parallel_group_count.completeness == "complete"
        and features.parallel_group_count.observed > 0
        and complete(
            "actions",
            "service_dependencies",
            "prerequisites",
            "conditions",
            "branch_groups",
            "parallel_groups",
        )
    )

    disclosure_supported = (
        bool(preservation.collapsible_content_ids)
        and features.information_volume.completeness == "complete"
        and complete("actions", "content")
    )

    visual_support = {
        "NONE": True,
        "BRANCH_MAP": branch_supported,
        "DEPENDENCY_MAP": bool(dependency_layers),
        "PARALLEL_MAP": parallel_supported,
    }

    decisions = []

    for configuration in enumerate_scaffolds():
        satisfied = []
        rejected = []

        def check(condition, code, success, failure):
            if condition:
                satisfied.append(_reason(code, success))
            else:
                rejected.append(_reason(code, failure))

        locks_match = True
        for dimension in DIMENSIONS:
            locked = getattr(context.locks, dimension)
            if (
                locked is not None
                and getattr(configuration, dimension) != locked
            ):
                locks_match = False
                rejected.append(
                    _reason(
                        f"LOCK_{dimension.upper()}",
                        f"{dimension} is explicitly locked to {locked}.",
                    )
                )

        if locks_match:
            satisfied.append(
                _reason("LOCKS", "All explicit presentation locks are respected.")
            )

        if configuration.presentation_mode == "GUIDED":
            check(
                context.accessibility.allow_guided_navigation,
                "ACCESS_GUIDED",
                "Guided navigation is permitted.",
                "Guided navigation is prohibited by an accessibility constraint.",
            )
            check(
                guided_supported,
                "GUIDED_STRUCTURE",
                "Complete action, content and structural coverage is available.",
                "Guided navigation requires complete structure and action content.",
            )
        else:
            satisfied.append(
                _reason(
                    "OVERVIEW",
                    "Overview preserves supplied information and uncertainty notices.",
                )
            )

        if configuration.progressive_disclosure:
            check(
                context.accessibility.allow_collapsed_content,
                "ACCESS_DISCLOSURE",
                "Collapsible supplementary content is permitted.",
                "Collapsed content is prohibited by an accessibility constraint.",
            )
            check(
                disclosure_supported,
                "DISCLOSURE_CONTENT",
                "Reviewed supplementary content is available with complete coverage.",
                "Disclosure requires reviewed supplementary content and complete coverage.",
            )

        if configuration.previous_context_recap:
            check(
                bool(recap_actions),
                "RECAP_HISTORY",
                "Matching prior action exposure exists for this session and snapshot.",
                "No relevant prior exposure exists for this session and snapshot.",
            )

        if configuration.relationship_visual != "NONE":
            check(
                context.accessibility.allow_relationship_visuals,
                "ACCESS_VISUAL",
                "Relationship visuals are permitted.",
                "Relationship visuals are prohibited by an accessibility constraint.",
            )
            check(
                visual_support[configuration.relationship_visual],
                "VISUAL_STRUCTURE",
                (
                    f"{configuration.relationship_visual} has explicit structure "
                    "and sufficient completeness."
                ),
                (
                    f"{configuration.relationship_visual} lacks explicit structure "
                    "or sufficient completeness."
                ),
            )

        if configuration.prerequisite_cue:
            check(
                bool(dependency_layers),
                "PREREQUISITE_STRUCTURE",
                "An explicitly supported dependency layer is available.",
                "No sufficiently complete explicit dependency layer is available.",
            )

        satisfied.append(
            _reason(
                "PRESERVATION_CONTRACT",
                (
                    "Acceptance requires protected facts, warnings, conditions, "
                    "relationships and sources to remain available in faithful "
                    "text form; only reviewed supplementary blocks may collapse."
                ),
            )
        )

        decisions.append(
            ConfigurationDecision(
                configuration=configuration,
                satisfied=tuple(satisfied),
                rejections=tuple(rejected),
            )
        )

    feasible = [
        decision.configuration
        for decision in decisions
        if decision.accepted
    ]
    baseline = min(feasible, key=_baseline_key) if feasible else None

    return FeasibilityResult(
        graph_fingerprint=fingerprint,
        decisions=tuple(decisions),
        baseline=baseline,
        baseline_reason=(
            "Deterministic least-elaborate feasible configuration; all locks "
            "and preservation obligations still apply."
            if baseline is not None
            else (
                "No configuration satisfies all constraints. Inspect rejection "
                "reasons; no user lock or accessibility constraint was relaxed."
            )
        ),
        supported_dependency_layers=tuple(dependency_layers),
        recap_action_ids=recap_actions,
        notices=notices,
        preservation=preservation,
    )


def validate_visibility(
    result: FeasibilityResult,
    configuration: ScaffoldConfiguration,
    declaration: VisibilityDeclaration,
) -> tuple[Reason, ...]:
    """Check coverage and disclosure against an evaluated result.

    An empty tuple means the declaration passes this coverage check.
    This cannot verify actual rendered text, DOM behavior or accessibility.
    """
    errors = []

    if configuration not in result.feasible_candidates():
        return (
            _reason(
                "CONFIGURATION_NOT_FEASIBLE",
                "The selected configuration is not an accepted candidate.",
            ),
        )

    visible = set(declaration.visible)
    collapsed = set(declaration.collapsed)

    if len(visible) != len(declaration.visible):
        errors.append(_reason("DUPLICATE_VISIBLE", "Visible items contain duplicates."))
    if len(collapsed) != len(declaration.collapsed):
        errors.append(
            _reason("DUPLICATE_COLLAPSED", "Collapsed items contain duplicates.")
        )
    if visible & collapsed:
        errors.append(
            _reason("OVERLAPPING_VISIBILITY", "An item is both visible and collapsed.")
        )

    inventory = set(result.preservation.inventory())
    protected = set(result.preservation.always_visible)
    eligible = {
        PresentationItem(kind="content", identifier=content_id)
        for content_id in result.preservation.collapsible_content_ids
    }

    unknown = (visible | collapsed) - inventory
    missing = inventory - (visible | collapsed)
    hidden_protected = protected - visible

    def describe(items):
        return ", ".join(
            f"{item.kind}/{item.identifier}"
            for item in sorted(
                items, key=lambda item: (item.kind, item.identifier)
            )
        )

    if unknown:
        errors.append(
            _reason("UNKNOWN_ITEMS", "Unknown items: " + describe(unknown))
        )
    if missing:
        errors.append(
            _reason("OMITTED_ITEMS", "Omitted items: " + describe(missing))
        )
    if hidden_protected:
        errors.append(
            _reason(
                "PROTECTED_ITEMS_NOT_VISIBLE",
                "Protected items are not visible: " + describe(hidden_protected),
            )
        )

    allowed_collapsed = (
        eligible if configuration.progressive_disclosure else set()
    )
    forbidden = collapsed - allowed_collapsed
    if forbidden:
        errors.append(
            _reason(
                "FORBIDDEN_COLLAPSE",
                "Items cannot be collapsed: " + describe(forbidden),
            )
        )

    return tuple(errors)