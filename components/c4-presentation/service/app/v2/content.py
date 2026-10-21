"""C4-owned enrichment overlay; never changes shared Plan v1.

Approved variants are declarations by a named reviewer, not an automated
assertion that natural language is entailed. Unreviewed content is rejected.
"""
import hashlib
import json
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Literal
from app.core.official_procedures import load_registered_procedures
from app.core.demo_procedures import reviewed_demo_safety
from app.core.procedure_input import load_procedure_input
from app.core.procedure_graph import build_procedure_graph
from app.v2.measurements import measurements
from app.core.scaffolds import graph_fingerprint
from app.core.presentation import action_navigation_order

ROOT = Path(__file__).resolve().parents[3] / "research" / "data"

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()

class Expression(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["action", "all_of", "any_of", "selected_option_of"]
    ref: str | None = None
    children: list["Expression"] = Field(default_factory=list)

    @model_validator(mode="after")
    def shape(self):
        if self.kind in ("action", "selected_option_of"):
            if not self.ref or self.children:
                raise ValueError("reference expression needs ref only")
        elif self.ref or len(self.children) < 2:
            raise ValueError("join requires two or more children and no ref")
        return self

class Join(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    target: str
    requirement: Expression
    evidence_ids: list[str] = Field(min_length=1)

class Ownership(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    action_id: str
    actor: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)

class Variant(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    action_id: str
    title: str = Field(min_length=1)
    concise: str = Field(min_length=1)
    expanded: str = Field(min_length=1)
    recap: str = Field(min_length=1)
    required_content_ids: list[str]
    evidence_ids: list[str] = Field(min_length=1)

class Overlay(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["c4-enrichment-v2.1"] = "c4-enrichment-v2.1"
    graph_fingerprint: str
    reviewer: str = Field(min_length=1)
    optional_content_ids: list[str] = Field(default_factory=list)
    variants: list[Variant] = Field(default_factory=list)
    owners: list[Ownership] = Field(default_factory=list)
    joins: list[Join] = Field(default_factory=list)
    # These are explicitly permitted concurrent work areas, including a route.
    parallel_areas: list[list[Expression]] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


def validate_overlay(graph, overlay):
    if overlay.graph_fingerprint != graph_fingerprint(graph):
        raise ValueError("enrichment is bound to a different graph")
    optional = {c.content_id for c in graph.content if c.role == "supplementary" and not c.fact_ids}
    if not set(overlay.optional_content_ids) <= optional:
        raise ValueError("only fact-free supplementary content may receive optional approval")
    actions = {a.action_id: a for a in graph.actions}
    branches = {b.group_id: b for b in graph.branch_groups}
    evidence = {e.evidence_id for e in graph.evidence}
    def refs(expr, depth=0):
        if depth > 16:
            raise ValueError("expression nesting exceeds supported bound")
        if expr.kind == "action":
            if expr.ref not in actions:
                raise ValueError("unknown action reference")
            return {expr.ref}
        if expr.kind == "selected_option_of":
            if expr.ref not in branches:
                raise ValueError("unknown branch reference")
            if branches[expr.ref].selection != "XOR":
                raise ValueError("selected-option joins require an XOR branch")
            return {a for o in branches[expr.ref].options for a in o.action_ids}
        return set().union(*(refs(c, depth + 1) for c in expr.children))
    for collection in (overlay.variants, overlay.owners):
        if len({v.action_id for v in collection}) != len(collection):
            raise ValueError("duplicate action overlay")
        for v in collection:
            if v.action_id not in actions or not set(v.evidence_ids) <= evidence:
                raise ValueError("unresolved overlay reference")
    for v in overlay.variants:
        if set(v.required_content_ids) != set(actions[v.action_id].required_content_ids):
            raise ValueError("reviewed variant must cover every required content reference")
        if v.concise.strip() == v.expanded.strip():
            raise ValueError("explanation variants must differ")
    adjacency = {a: set() for a in actions}
    for e in graph.action_prerequisites:
        adjacency[e.source_id].add(e.target_id)
    for join in overlay.joins:
        if join.target not in actions or not set(join.evidence_ids) <= evidence:
            raise ValueError("unresolved join evidence or target")
        for source in refs(join.requirement):
            adjacency[source].add(join.target)
    visiting, visited = set(), set()
    def visit(node):
        if node in visiting:
            raise ValueError("cyclic conditional dependency")
        if node in visited:
            return
        visiting.add(node)
        for target in adjacency[node]:
            visit(target)
        visiting.remove(node)
        visited.add(node)
    for a in actions:
        visit(a)
    def reachable(source, target):
        pending, seen = [source], set()
        while pending:
            node = pending.pop()
            if node in seen:
                continue
            seen.add(node)
            pending.extend(adjacency[node])
        return target in seen
    if overlay.parallel_areas and (not overlay.evidence_ids or not set(overlay.evidence_ids) <= evidence):
        raise ValueError("parallel areas require evidence")
    for areas in overlay.parallel_areas:
        if len(areas) < 2:
            raise ValueError("parallel work requires at least two areas")
        groups = [refs(e) for e in areas]
        for i, group in enumerate(groups):
            for other in groups[i + 1:]:
                if any(reachable(a, b) or reachable(b, a) for a in group for b in other):
                    raise ValueError("parallel areas conflict with prerequisites")
    return overlay


def procedure(graph, overlay=None):
    if overlay:
        validate_overlay(graph, overlay)
    content = {c.content_id: c for c in graph.content}
    stages = {s.service_id: s for s in graph.stages}
    variants = {v.action_id: v for v in overlay.variants} if overlay else {}
    owners = {v.action_id: v.actor for v in overlay.owners} if overlay else {}
    safety = reviewed_demo_safety(graph)
    safe_optional = set(safety.disclosure_review.safe_content_ids) if safety.disclosure_review else set()
    if overlay:
        safe_optional.update(overlay.optional_content_ids)
    actions = []
    by_id = {a.action_id: a for a in graph.actions}
    for action_id in action_navigation_order(graph):
        a = by_id[action_id]
        required = [content[c] for c in a.required_content_ids if c != "content:scope" or content[c].text != graph.disclaimer]
        v = variants.get(a.action_id)
        text = "\n\n".join(c.text for c in required)
        title = a.action_id.split(":", 1)[-1].replace("_", " ").capitalize()
        if v:
            title, text = v.title, v.concise
        facts = sorted({f for c in required for f in c.fact_ids})
        actions.append({"id": a.action_id, "title": title, "service_id": a.service_id,
            "service_agency": stages[a.service_id].agency, "actor": owners.get(a.action_id),
            "concise": text, "expanded": v.expanded if v else text,
            "recap": v.recap if v else title, "fact_ids": facts,
            "coverage": list(a.required_content_ids),
            "conditions": [c.text for c in graph.conditions if c.condition_id in a.applicability.condition_ids],
            "branch": a.applicability.branch_group_id, "option": a.applicability.branch_option_id,
            "optional": [{"id": c, "text": content[c].text} for c in a.supplementary_content_ids if c in safe_optional],
            # Unreviewed supplementary passages remain visible, never disappear.
            "unreviewed_supplement": [content[c].text for c in a.supplementary_content_ids if c not in safe_optional]})
    measures = measurements(graph, overlay)
    has_relation = bool(graph.action_prerequisites or graph.branch_groups or graph.parallel_groups or graph.stage_dependencies)
    has_overlay_relation = bool(overlay and (overlay.joins or overlay.parallel_areas))
    optional = any(a["optional"] for a in actions)
    expanded = bool(actions) and all(a.action_id in variants for a in graph.actions)
    def cap(states, applicable, reason):
        return {"states": states, "applicable": applicable, "reason": reason}
    caps = {
        "navigation": cap(["overview", "guided"] if len(actions) > 1 else ["overview"], len(actions) > 1, "bounded guidance browsing; not execution order"),
        "explanation": cap(["concise", "expanded"] if expanded else ["concise"], True, "expanded requires reviewed full coverage variants"),
        "disclosure": cap(["collapsed", "expanded"] if optional else ["collapsed"], optional, "no reviewed optional material"),
        "relationships": cap(["none", "inline", "map"] if has_relation or has_overlay_relation else ["none"], has_relation or has_overlay_relation, "only supplied relationships; completeness caveats retained"),
        "recap": cap(["off", "on"] if len(actions) > 1 else ["off"], len(actions) > 1, "within-journey opportunity appears after earlier action display"),
        "summary": cap(["off", "on"] if len(graph.facts) > 1 else ["off"], len(graph.facts) > 1, "deduplicated facts; no inferred fee total"),
    }
    document = {"id": graph.plan_id, "title": stages[graph.requested_service_id].name, "synthetic": graph.synthetic,
        "scope": graph.disclaimer, "graph_fingerprint": graph_fingerprint(graph), "actions": actions,
        "facts": [f.model_dump(mode="json") for f in graph.facts], "sources": [e.model_dump(mode="json") for e in graph.evidence],
        "provenance": [e.model_dump(mode="json") for e in graph.provenance],
        "conditions": [c.model_dump(mode="json") for c in graph.conditions],
        "stages": [s.model_dump(mode="json") for s in graph.stages],
        "stage_edges": [e.model_dump(mode="json") for e in graph.stage_dependencies],
        "edges": [e.model_dump(mode="json") for e in graph.action_prerequisites],
        "branches": [b.model_dump(mode="json") for b in graph.branch_groups],
        "parallel": [p.model_dump(mode="json") for p in graph.parallel_groups],
        "joins": [j.model_dump(mode="json") for j in overlay.joins] if overlay else [],
        "parallel_areas": [[e.model_dump(mode="json") for e in group] for group in overlay.parallel_areas] if overlay else [],
        "completeness": graph.completeness.model_dump(), "capabilities": caps,
        "measurement_semantics": "v2.1: conditional joins count once; depth is maximum supplied structural path; no implied completion",
        "content_origin": "reviewed authored fixture" if overlay else "source-preserving fallback",
        "reviewer": overlay.reviewer if overlay else None}
    document["content_fingerprint"] = digest(document)
    return {"graph": graph, "overlay": overlay, "measurements": measures, "document": document}


def registry():
    graphs, _ = load_registered_procedures()
    result = {g.plan_id: procedure(g) for g in graphs}
    # Additional research inputs remain C4-owned Plan v1 + enrichment packets.
    for folder in sorted((ROOT / "v2").glob("*")):
        if not folder.is_dir() or not (folder / "plan.json").exists():
            continue
        g = build_procedure_graph(load_procedure_input(folder / "plan.json", folder / "enrichment.json"))
        if g.plan_id in result:
            raise ValueError("duplicate C4 procedure identity")
        overlay_path = folder / "overlay.json"
        overlay = Overlay.model_validate_json(overlay_path.read_text(encoding="utf-8-sig")) if overlay_path.exists() else None
        result[g.plan_id] = procedure(g, overlay)
    # Explicit reviewed artifacts override wording only for the matching graph.
    for path in sorted((ROOT / "v2" / "approved").glob("*.json")):
        from app.v2.preparation import resolve
        artifact = json.loads(path.read_text(encoding="utf-8-sig"))
        matches = [key for key, value in result.items() if graph_fingerprint(value["graph"]) == artifact.get("source_fingerprint")]
        if len(matches) != 1:
            raise ValueError("approved content must match exactly one registered graph")
        key = matches[0]
        result[key] = resolve(result[key]["graph"], path)
    return result
