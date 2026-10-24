"""V2 measurements include conditional constraints without inventing plain edges."""
from app.procedures.procedure_features import extract_structural_features
from app.models.procedure_features import StructuralFeatures
from typing import Literal

class V2StructuralFeatures(StructuralFeatures):
    measurement_version: Literal["c4-structural-v2.1"] = "c4-structural-v2.1"

def measurements(graph, overlay):
    original = extract_structural_features(graph)
    base = V2StructuralFeatures(**{name:getattr(original,name) for name in type(original).model_fields if name != "measurement_version"})
    if not overlay:
        return base
    branches = {b.group_id: b for b in graph.branch_groups}
    def leaves(expr):
        if expr.kind == "action":
            return {expr.ref}
        if expr.kind == "selected_option_of":
            return {a for o in branches[expr.ref].options for a in o.action_ids}
        return set().union(*(leaves(c) for c in expr.children))
    predecessors = {a.action_id: set() for a in graph.actions}
    for edge in graph.action_prerequisites:
        predecessors[edge.target_id].add(edge.source_id)
    for join in overlay.joins:
        predecessors[join.target].update(leaves(join.requirement))
    def depth(node):
        return max((depth(p) + 1 for p in predecessors[node]), default=0)
    # Each conditional join is one logical constraint, not an unconditional edge per alternative.
    values = {"dependency_count": len(graph.action_prerequisites) + len(overlay.joins),
              "dependency_depth": max((depth(a) for a in predecessors), default=0),
              "parallel_group_count": len(graph.parallel_groups) + len(overlay.parallel_areas)}
    return base.model_copy(update={k:getattr(base,k).model_copy(update={"observed":v}) for k,v in values.items()})
