"""Registered synthetic procedures for the independent C4 demonstration.

This module reads local fixtures only when load_demo_procedures() is called.
It does not access a database, start a service or call an LLM.

The disclosure allowlist is an explicit author review of exact supplementary
paragraphs. It is not a general-purpose semantic safety classifier.
"""

from pathlib import Path

from app.procedures.procedure_graph import build_procedure_graph
from app.procedures.procedure_input import load_procedure_input
from app.procedures.scaffolds import graph_fingerprint
from app.models.procedure_graph import CanonicalProcedureGraph
from app.models.scaffolds import ContentSafety, DisclosureReview


FIXTURES_ROOT = (
    Path(__file__).resolve().parents[3]
    / "research"
    / "data"
    / "fixtures"
)

SCENARIOS = ("linear", "conditional", "parallel")

# plan_id -> content_id -> (exact reviewed text, exact evidence references).
# Only these explanatory paragraphs may receive catalogue disclosure approval.
REVIEWED_SUPPLEMENTS = {
    "synthetic-conditional-v1": {
        "content:collection_comparison": (
            "The two collection methods are alternatives rather than a sequence. "
            "Comparing them side by side may make the choice easier to understand.",
            ("evidence:collection_rules",),
        ),
    },
    "synthetic-parallel-v1": {
        "content:preparation_explanation": (
            "Think of preparation as two work areas that come together at "
            "submission. This is another way to describe the required "
            "preparation relationships.",
            ("evidence:application_rules",),
        ),
    },
}


def reviewed_demo_safety(graph: CanonicalProcedureGraph) -> ContentSafety:
    """Approve only exact, explicitly reviewed synthetic supplementary blocks.

    Approval is attached to the supplied graph's exact fingerprint. Unknown
    content, changed text, fact-linked text and unused text receive no approval.
    Required cards, evidence and structural records remain protected by the
    existing feasibility preservation contract.
    """
    if not graph.synthetic:
        return ContentSafety()

    reviewed = REVIEWED_SUPPLEMENTS.get(graph.plan_id, {})
    supplementary_refs = {
        content_id
        for action in graph.actions
        for content_id in action.supplementary_content_ids
    }

    approved = []
    for block in graph.content:
        expected = reviewed.get(block.content_id)
        if expected is None:
            continue

        expected_text, expected_evidence_ids = expected
        if (
            block.role == "supplementary"
            and block.content_id in supplementary_refs
            and block.text == expected_text
            and block.evidence_ids == expected_evidence_ids
            and not block.fact_ids
        ):
            approved.append(block.content_id)

    if not approved:
        return ContentSafety()

    return ContentSafety(
        disclosure_review=DisclosureReview(
            graph_fingerprint=graph_fingerprint(graph),
            safe_content_ids=tuple(sorted(approved)),
        ),
    )


def load_demo_procedures(
    fixtures_root: str | Path | None = None,
) -> tuple[
    tuple[CanonicalProcedureGraph, ...],
    dict[str, ContentSafety],
]:
    """Load validated demo graphs and their trusted content-safety inputs.

    Linear remains first for compatibility with existing demonstration scripts.
    Invalid or missing fixtures fail startup instead of silently disappearing.
    """
    root = FIXTURES_ROOT if fixtures_root is None else Path(fixtures_root)
    graphs = []
    safety_by_fingerprint = {}

    for scenario in SCENARIOS:
        directory = root / scenario
        procedure = load_procedure_input(
            directory / "plan.json",
            directory / "enrichment.json",
        )
        graph = build_procedure_graph(procedure)

        if not graph.synthetic:
            raise ValueError(
                f"Demo scenario '{scenario}' must be explicitly synthetic"
            )

        fingerprint = graph_fingerprint(graph)
        if fingerprint in safety_by_fingerprint:
            raise ValueError(f"Duplicate demo graph: '{scenario}'")

        graphs.append(graph)
        safety_by_fingerprint[fingerprint] = reviewed_demo_safety(graph)

    return tuple(graphs), safety_by_fingerprint