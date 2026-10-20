"""Local, manually curated official-source snapshots; no network at startup.

These are bounded research tasks, not complete government workflows. The
synthetic catalogue remains available separately for closed-world experiments.
"""

from pathlib import Path

from app.core.demo_procedures import load_demo_procedures
from app.core.procedure_graph import build_procedure_graph
from app.core.procedure_input import load_procedure_input
from app.core.scaffolds import graph_fingerprint
from app.models.scaffolds import ContentSafety


OFFICIAL_ROOT = Path(__file__).resolve().parents[3] / "research" / "data" / "official"
OFFICIAL_EXAMPLES = ("birth_copy", "nic_amendment", "company_pack")


def load_official_procedures(root: str | Path | None = None):
    directory = OFFICIAL_ROOT if root is None else Path(root)
    graphs = []
    safety = {}
    for name in OFFICIAL_EXAMPLES:
        graph = build_procedure_graph(load_procedure_input(
            directory / name / "plan.json", directory / name / "enrichment.json",
        ))
        if graph.synthetic:
            raise ValueError(f"Official-source example '{name}' must not be synthetic")
        fingerprint = graph_fingerprint(graph)
        if fingerprint in safety:
            raise ValueError(f"Duplicate official-source graph: '{name}'")
        graphs.append(graph)
        # No automatic author review or disclosure permission for official text.
        safety[fingerprint] = ContentSafety()
    return tuple(graphs), safety


def load_registered_procedures():
    """Append examples without changing existing synthetic IDs/fingerprints."""
    synthetic, synthetic_safety = load_demo_procedures()
    official, official_safety = load_official_procedures()
    if set(synthetic_safety) & set(official_safety):
        raise ValueError("Duplicate catalogue fingerprint")
    return synthetic + official, {**synthetic_safety, **official_safety}
