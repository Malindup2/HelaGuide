"""Clearly fictional STUDY procedures for the 3.1 synthetic evaluation. Not registered in the citizen application.

They exist to give the six scaffolds varied structure to act on (short/long, branching, multi-level dependencies,
parallel work with joins, several phases, high information volume, mixed). Wording is templated and never shown to
citizens; only structure and measurements matter for the study. Nothing here concerns an official government service.
"""
import json
from app.procedures.procedure_graph import build_procedure_graph
from app.procedures.procedure_input import parse_procedure_input
from app.guidance.content_v31 import GuidanceContent31, SCHEMA31
from app.guidance.sources import ProcedureSource
from app.procedures.canonical import Overlay, graph_fingerprint

URL = "https://example.org/c4/study-fixtures"
WHEN = "2026-10-22T00:00:00Z"
FILL = ("Bring the fictional identity card and keep the fictional reference number. The fictional counter checks the fictional form against the "
        "fictional register. Fictional queues are short in the morning. Keep every fictional receipt. ")

# Each spec: stages, actions (stage index, filler repeats), prerequisite edges, XOR branches, parallel groups, joins.
SPECS = {
    "study-short-linear": dict(stages=[("Collect a fictional token", 0)], actions=[("a1", 0, 0), ("a2", 0, 0), ("a3", 0, 0)], edges=[("a1", "a2"), ("a2", "a3")]),
    "study-long-linear": dict(stages=[("Open a fictional file", 0), ("Verify fictional details", 0), ("Pay fictional charges", 25), ("Collect the fictional certificate", 0)],
        actions=[(f"a{i}", (i - 1) // 2, 1) for i in range(1, 9)], edges=[(f"a{i}", f"a{i + 1}") for i in range(1, 8)]),
    "study-branching": dict(stages=[("Choose a fictional service route", 0), ("Complete the fictional route", 10)],
        actions=[("a1", 0, 1), ("a2", 1, 1), ("a3", 1, 1), ("a4", 1, 1), ("a5", 1, 1), ("a6", 1, 1)],
        edges=[("a1", "a2"), ("a1", "a3"), ("a1", "a4"), ("a1", "a5")],
        joins=[dict(target="a6", all=["b:b1", "b:b2"])],
        branches=[dict(id="b1", stage=1, options=[("o1", ["a2"], "You hold the fictional membership card."), ("o2", ["a3"], "You do not hold the fictional membership card.")]),
                  dict(id="b2", stage=1, options=[("o3", ["a4"], "You apply in person."), ("o4", ["a5"], "You apply by the fictional postal desk.")])]),
    "study-multilevel": dict(stages=[("Register fictionally", 0), ("Gather fictional proofs", 0), ("Assess fictionally", 5), ("Issue fictionally", 0)],
        actions=[("a1", 0, 1), ("a2", 1, 1), ("a3", 1, 1), ("a4", 1, 1), ("a5", 2, 1), ("a6", 2, 1), ("a7", 3, 1), ("a8", 3, 1)],
        edges=[("a1", "a2"), ("a1", "a3"), ("a1", "a4"), ("a2", "a5"), ("a3", "a5"), ("a4", "a6"), ("a5", "a7"), ("a6", "a7"), ("a7", "a8")]),
    "study-parallel-join": dict(stages=[("Register fictionally", 0), ("Prepare fictional items", 0), ("Submit fictionally", 3)],
        actions=[("a1", 0, 1), ("a2", 1, 1), ("a3", 1, 1), ("a4", 1, 1), ("a5", 1, 1), ("a6", 2, 1), ("a7", 2, 1)],
        edges=[("a1", "a2"), ("a1", "a3"), ("a1", "a4"), ("a1", "a5"), ("a2", "a6"), ("a3", "a6"), ("a4", "a6"), ("a5", "a6"), ("a6", "a7")],
        parallel=[["a2", "a3", "a4", "a5"]], joins=[dict(target="a6", all=["a2", "a3", "a4", "a5"])]),
    "study-multiphase": dict(stages=[("Apply fictionally", 0), ("Prepare fictional evidence", 0), ("Attend a fictional appointment", 12), ("Receive the fictional decision", 0)],
        actions=[("a1", 0, 1), ("a2", 0, 1), ("a3", 1, 1), ("a4", 1, 1), ("a5", 1, 1), ("a6", 2, 1), ("a7", 2, 1), ("a8", 3, 1), ("a9", 3, 1)],
        edges=[("a1", "a2"), ("a2", "a3"), ("a2", "a4"), ("a2", "a5"), ("a3", "a6"), ("a4", "a6"), ("a5", "a6"), ("a6", "a7"), ("a7", "a8"), ("a8", "a9")],
        parallel=[["a3", "a4", "a5"]]),
    "study-info-heavy": dict(stages=[("Complete a fictional detailed return", 40)], actions=[("a1", 0, 8), ("a2", 0, 8), ("a3", 0, 8), ("a4", 0, 8)],
        edges=[("a1", "a2"), ("a2", "a3"), ("a3", "a4")]),
    "study-mixed": dict(stages=[("Begin a fictional case", 0), ("Choose and prepare fictionally", 15), ("Conclude fictionally", 0)],
        actions=[("a1", 0, 1), ("a2", 1, 2), ("a3", 1, 2), ("a4", 1, 2), ("a5", 1, 2), ("a6", 1, 2), ("a7", 2, 2), ("a8", 2, 2), ("a9", 2, 2), ("a10", 2, 2)],
        edges=[("a1", "a2"), ("a1", "a3"), ("a1", "a4"), ("a1", "a5"), ("a1", "a6"), ("a4", "a8"), ("a5", "a8"), ("a6", "a9")],
        branches=[dict(id="b1", stage=1, options=[("o1", ["a2"], "You have the fictional licence."), ("o2", ["a3"], "You lack the fictional licence.")])],
        parallel=[["a4", "a5", "a6"]], joins=[dict(target="a7", all=["b:b1"]), dict(target="a10", all=["a7", "a8", "a9"])]),
}
TITLES = {pid: "Study procedure: " + pid.removeprefix("study-").replace("-", " ") for pid in SPECS}
HELD_OUT = ("study-multiphase", "study-mixed")
DEVELOPMENT = ("study-multilevel", "synthetic-conditional-v1")


def _plan_and_enrichment(pid, spec):
    stages = spec["stages"]
    sid = lambda k: "svc:" + pid.replace("-", "_") + f"_{k}"
    fee = lambda k: f"{sid(k)}:fee"
    steps, provenance = [], {}
    for k, (name, amount) in enumerate(stages):
        provenance[fee(k)] = {"source_url": URL, "retrieved_at": WHEN}
        steps.append({"order": k + 1, "service_id": sid(k), "name": TITLES[pid] if k == len(stages) - 1 else f"Study fiction: {name}", "agency": "Fictional C4 Study Office",
                      "fee": {"value": amount, "currency": "LKR", "fact_id": fee(k)}, "documents": [], "depends_on": [sid(k - 1)] if k else []})
    plan = {"plan_id": pid, "requested_service_id": sid(len(stages) - 1), "generated_at": WHEN, "steps": steps, "provenance": provenance}
    cond_for = {}
    for b in spec.get("branches", ()):
        for oid, acts, text in b["options"]:
            for a in acts:
                cond_for[a] = (f"condition:{oid}", text)
    evidence = [{"evidence_id": "evidence:study", "kind": "synthetic_authored", "source_url": URL, "retrieved_at": None, "text": "Authored fictional study procedure. " + " ".join(f"Task {a} follows its listed prerequisites." for a, _, _ in spec["actions"])}]
    conditions, content, actions = [], [], []
    for cid, text in sorted({v for v in cond_for.values()}):
        conditions.append({"condition_id": cid, "text": text, "evidence_ids": ["evidence:study"]})
    for a, stage, fill in spec["actions"]:
        text = f"Do fictional task {a} at the fictional Study Office. " + FILL * fill
        content.append({"content_id": f"content:{a}", "role": "required", "text": text.strip(), "evidence_ids": ["evidence:study"], "fact_ids": [fee(stage)] if a == spec["actions"][0][0] else []})
        actions.append({"action_id": f"action:{a}", "service_id": sid(stage), "required_content_ids": [f"content:{a}"], "supplementary_content_ids": [], "condition_ids": [cond_for[a][0]] if a in cond_for else []})
    prereq = [{"prerequisite_id": f"prerequisite:{u}_{v}", "kind": "requires_completion", "required_action_id": f"action:{u}", "dependent_action_id": f"action:{v}", "evidence_ids": ["evidence:study"]} for u, v in spec.get("edges", ())]
    branches = [{"group_id": f"branch:{b['id']}", "service_id": sid(b["stage"]), "selection": "XOR", "evidence_ids": ["evidence:study"],
                 "options": [{"option_id": f"option:{oid}", "action_ids": [f"action:{x}" for x in acts], "condition_ids": [f"condition:{oid}"]} for oid, acts, _ in b["options"]]} for b in spec.get("branches", ())]
    parallel = [{"group_id": f"parallel:{i}", "service_id": sid(next(s for a, s, _ in spec["actions"] if a == group[0])), "action_ids": [f"action:{x}" for x in group], "evidence_ids": ["evidence:study"]} for i, group in enumerate(spec.get("parallel", ()))]
    enrichment = {"schema_version": "1.0", "plan_id": pid, "base_generated_at": WHEN, "synthetic": True,
                  "disclaimer": "Fictional study procedure authored for C4 research. Not a government service; wording is templated and never shown to citizens.",
                  "actions": actions, "content": content, "evidence": evidence, "conditions": conditions, "prerequisites": prereq, "branch_groups": branches,
                  "parallel_groups": parallel, "completeness": {k: "complete" for k in ("service_dependencies", "actions", "content", "conditions", "branch_groups", "prerequisites", "parallel_groups")}}
    return plan, enrichment


def source(pid) -> ProcedureSource:
    spec = SPECS[pid]
    plan, enrichment = _plan_and_enrichment(pid, spec)
    graph = build_procedure_graph(parse_procedure_input(json.dumps(plan), json.dumps(enrichment)))
    overlay = None
    if spec.get("joins"):
        leaf = lambda x: {"kind": "selected_option_of", "ref": "branch:" + x[2:]} if x.startswith("b:") else {"kind": "action", "ref": f"action:{x}"}
        joins = [{"target": f"action:{j['target']}", "requirement": leaf(j["all"][0]) if len(j["all"]) == 1 else {"kind": "all_of", "children": [leaf(x) for x in j["all"]]}, "evidence_ids": ["evidence:study"]} for j in spec["joins"]]
        areas = [[{"kind": "action", "ref": f"action:{x}"} for x in group] for group in spec.get("parallel", ())]
        overlay = Overlay.model_validate({"schema_version": "c4-enrichment-v2.1", "graph_fingerprint": graph_fingerprint(graph), "reviewer": "study-fixture-author; fictional structure only, not reviewed wording",
                                          "joins": joins, "parallel_areas": areas, "evidence_ids": ["evidence:study"]})
    return ProcedureSource(graph=graph, relationships=overlay).validate()


def content(src: ProcedureSource) -> GuidanceContent31:
    """Templated STUDY wording in the 3.1 shape. Statuses stay draft; the study counts it as reviewed only in the declared hypothetical way (assume_reviewed)."""
    g = src.graph
    passages = {c.content_id: c for c in g.content}
    claims, actions = [], []
    from app.guidance.content_v31 import Action31
    from app.guidance.content import Claim, Phase, Text
    for a in g.actions:
        ids = []
        for i, cid in enumerate(a.required_content_ids):
            p = passages[cid]
            key = f"{a.action_id}:claim:{i}"
            claims.append(Claim(id=key, source_id=cid, start=0, end=len(p.text), quote=p.text, action_ids=(a.action_id,), required=True, kind="instruction", evidence_ids=tuple(p.evidence_ids)))
            ids.append(key)
        raw = "\n\n".join(passages[c].text for c in a.required_content_ids)
        ev = tuple(passages[a.required_content_ids[0]].evidence_ids)
        n = a.action_id.removeprefix("action:")
        short = Text(text=f"Do task {n}.", status="draft", claim_ids=tuple(ids), evidence_ids=ev)
        full = Text(text=f"Do task {n} at the Study Office, after the tasks it depends on. Keep the reference.", status="draft", claim_ids=tuple(ids), evidence_ids=ev)
        actions.append(Action31(id=a.action_id, heading=Text(text=f"Task {n}", status="draft", evidence_ids=ev), heading_actionable=True,
            source_wording=Text(text=raw, status="source_fallback", claim_ids=tuple(ids), evidence_ids=ev), concise=short, detailed=full,
            supplement=None, recap=Text(text=f"Earlier you looked at task {n}.", status="draft", evidence_ids=ev),
            visible_condition_ids=tuple(a.applicability.condition_ids)))
    phases = []
    stage_ids = [s.service_id for s in g.stages]
    if len(stage_ids) > 1:
        for k, sid in enumerate(stage_ids):
            members = tuple(a.action_id for a in g.actions if a.service_id == sid)
            if members:
                phases.append(Phase(id=f"phase:{k}", label=Text(text=f"Part {k + 1}", status="draft", evidence_ids=("evidence:study",)), action_ids=members, basis="stage",
                                    why_grouped="Same fictional stage", adds_orientation=True, evidence_ids=("evidence:study",)))
    # A supplement exists only where an action has dependencies or branching, so some steps legitimately lack one.
    needs = {a.action_id for a in g.actions if any(e.target_id == a.action_id for e in g.action_prerequisites)}
    actions = [x.model_copy(update={"supplement": __import__("app.guidance.content_v31", fromlist=["Supplement"]).Supplement(
        text=Text(text="This task depends on earlier ones.", status="draft", evidence_ids=x.concise.evidence_ids), role="clarification", adds_information=True)}) if x.id in needs else x for x in actions]
    return GuidanceContent31(schema_version=SCHEMA31, procedure_id=g.plan_id, source_graph_fingerprint=src.graph_fingerprint, relationship_fingerprint=src.relationship_fingerprint,
                             content_version="study-templated-1", origin="fictional_authored", source_limit=g.disclaimer, claims=tuple(claims), actions=tuple(actions), phases=tuple(phases))
