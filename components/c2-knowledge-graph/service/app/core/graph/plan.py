"""Answer "what do I need for service X?" by walking the graph. No model is involved.

The plan is the requested service and everything it REQUIRES, ordered so a prerequisite always
comes before the service that needs it. Each step carries its fees, documents, steps and times,
and each of those carries the page and the quote it came from. A service that is required but
has no facts yet is still listed, marked as incomplete, never silently dropped.

    python -m app.core.graph.plan svc:passport
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field

MAX_DEPTH = 8


@dataclass
class Item:
    fact_id: str
    value: str
    qualifier: str
    unit: str | None
    amount: float | None
    source_url: str | None
    quote: str
    review: str  # "human", "auto", or "" for facts written before this was recorded
    applies_to: list[str] = field(default_factory=list)  # cases a document is for; [] = all
    applies_to_all: bool = False


@dataclass
class Step:
    order: int
    service_id: str
    agency: str | None = None
    fees: list[Item] = field(default_factory=list)
    documents: list[Item] = field(default_factory=list)
    steps: list[Item] = field(default_factory=list)       # prerequisites that are not services
    times: list[Item] = field(default_factory=list)
    eligibility: list[Item] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    complete: bool = True
    missing: list[str] = field(default_factory=list)


@dataclass
class Plan:
    requested: str
    steps: list[Step]
    cycle: list[str] | None = None
    cases: list[str] = field(default_factory=list)  # cases the requested service distinguishes
    case: str | None = None                          # the case the plan was narrowed to

    @property
    def incomplete(self) -> list[str]:
        return [s.service_id for s in self.steps if not s.complete]


def _facts(session, service_id: str) -> list[dict]:
    return [dict(r) for r in session.run(
        """MATCH (s:Service {service_id: $sid})-[:HAS_FACT]->(f:Fact)
           WHERE f.valid_to IS NULL
           OPTIONAL MATCH (f)-[:FROM_SOURCE]->(p:SourcePage)
           RETURN f.fact_id AS fact_id, f.predicate AS predicate, f.qualifier AS qualifier,
                  f.value AS value, f.value_num AS amount, f.unit AS unit, f.evidence AS quote,
                  f.review AS review, f.detail_json AS detail, p.url AS url
           ORDER BY f.fact_id""", sid=service_id)]


def _requires(session, service_id: str) -> list[str]:
    return [r["t"] for r in session.run(
        """MATCH (:Service {service_id: $sid})-[r:REQUIRES]->(t:Service)
           WHERE r.valid_to IS NULL RETURN DISTINCT t.service_id AS t ORDER BY t""", sid=service_id)]


def _exists(session, service_id: str) -> bool:
    return session.run("MATCH (s:Service {service_id: $sid}) RETURN count(s) AS n",
                       sid=service_id).single()["n"] > 0


def _variant_of(qualifier: str, variants: set[str]) -> str | None:
    for v in sorted(variants, key=len, reverse=True):
        if qualifier == v or qualifier.startswith(v + "_"):
            return v
    return None


def build_plan(driver, service_id: str, case: str | None = None) -> Plan | None:
    """None when the service is not in the graph. Otherwise the ordered plan.

    case narrows the REQUESTED service to one applicant case (ordinary, minor, lost...). Fees
    and times of other cases, and documents that apply only to other cases, are left out. The
    prerequisite services are shown whole: their own cases are a different question.
    """
    with driver.session() as session:
        if not _exists(session, service_id):
            return None

        order: list[str] = []     # post-order: prerequisites first
        edges: dict[str, list[str]] = {}
        state: dict[str, int] = {}  # 1 = on the path, 2 = done
        cycle: list[str] | None = None

        def visit(sid: str, path: list[str]) -> None:
            nonlocal cycle
            if state.get(sid) == 2:
                return
            if state.get(sid) == 1:
                cycle = cycle or (path[path.index(sid):] + [sid])
                return
            if len(path) > MAX_DEPTH:
                return
            state[sid] = 1
            edges[sid] = _requires(session, sid)
            for dep in edges[sid]:
                visit(dep, path + [sid])
            state[sid] = 2
            order.append(sid)

        visit(service_id, [])

        steps = []
        for n, sid in enumerate(order, start=1):
            step = Step(order=n, service_id=sid, depends_on=edges.get(sid, []))
            for f in _facts(session, sid):
                detail = {}
                try:
                    detail = json.loads(f["detail"]) if f["detail"] else {}
                except (TypeError, ValueError):
                    pass
                item = Item(f["fact_id"], f["value"], f["qualifier"] or "", f["unit"],
                            f["amount"], f["url"], f["quote"] or "", f["review"] or "",
                            list(detail.get("applies_to") or []),
                            bool(detail.get("applies_to_all", False)))
                p = f["predicate"]
                if p == "agency":
                    step.agency = step.agency or f["value"]
                elif p == "fee":
                    step.fees.append(item)
                elif p == "document":
                    step.documents.append(item)
                elif p == "processing_time":
                    step.times.append(item)
                elif p == "eligibility":
                    step.eligibility.append(item)
                elif p == "prerequisite" and not detail.get("requires_service"):
                    step.steps.append(item)
            if not (step.fees or step.documents or step.steps or step.times):
                step.complete, step.missing = False, ["no facts of its own yet"]
            else:
                if not step.fees:
                    step.missing.append("fee not stated in the pages read")
                if not step.documents:
                    step.missing.append("no documents listed")
            steps.append(step)

    requested = next(s for s in steps if s.service_id == service_id)
    cases = sorted({c for d in requested.documents for c in d.applies_to})
    if case:
        variants = set(cases)
        keep_doc = lambda d: d.applies_to_all or not d.applies_to or case in d.applies_to  # noqa: E731
        keep_qual = lambda i: _variant_of(i.qualifier, variants) in (None, case)            # noqa: E731
        requested.documents = [d for d in requested.documents if keep_doc(d)]
        requested.fees = [i for i in requested.fees if keep_qual(i)]
        requested.times = [i for i in requested.times if keep_qual(i)]
    return Plan(requested=service_id, steps=steps, cycle=cycle, cases=cases, case=case)


def _line(item: Item) -> str:
    tag = "  (auto-approved)" if item.review == "auto" else ""
    where = item.source_url.replace("https://", "") if item.source_url else "no source"
    return f"{item.value}  [{item.qualifier or '-'}]{tag}\n          from {where}"


def render_text(plan: Plan) -> str:
    out = [f"Plan for {plan.requested}: {len(plan.steps)} step(s), read from the graph "
           f"(no model used)"]
    if plan.case:
        out.append(f"Narrowed to the case '{plan.case}' for {plan.requested}. "
                   "Prerequisite services are shown with all of their cases.")
    elif plan.cases:
        out.append(f"{plan.requested} distinguishes cases: {', '.join(plan.cases)}. "
                   "Everything is listed. Add --case <name> to narrow it.")
    if plan.cycle:
        out.append("WARNING: a prerequisite cycle was found: " + " -> ".join(plan.cycle))
    for s in plan.steps:
        mark = "" if s.complete else "   <-- INCOMPLETE"
        out.append(f"\n{s.order}. {s.service_id}{mark}")
        if s.agency:
            out.append(f"     agency: {s.agency}")
        if s.depends_on:
            out.append(f"     needs first: {', '.join(s.depends_on)}")
        for label, items in (("fee", s.fees), ("document", s.documents), ("step", s.steps),
                             ("time", s.times)):
            for it in items:
                out.append(f"     {label}: {_line(it)}")
        for why in s.missing:
            out.append(f"     missing: {why}")
    if plan.incomplete:
        out.append(f"\nIncomplete: {', '.join(plan.incomplete)}")
    return "\n".join(out)


def to_dict(plan: Plan) -> dict:
    def item(i: Item) -> dict:
        return {"fact_id": i.fact_id, "value": i.value, "qualifier": i.qualifier, "unit": i.unit,
                "amount": i.amount, "source_url": i.source_url, "quote": i.quote, "review": i.review}

    return {"requested": plan.requested, "cycle": plan.cycle, "incomplete": plan.incomplete,
            "cases": plan.cases, "case": plan.case,
            "steps": [{"order": s.order, "service_id": s.service_id, "agency": s.agency,
                       "depends_on": s.depends_on, "complete": s.complete, "missing": s.missing,
                       "fees": [item(i) for i in s.fees], "documents": [item(i) for i in s.documents],
                       "steps": [item(i) for i in s.steps], "times": [item(i) for i in s.times],
                       "eligibility": [item(i) for i in s.eligibility]} for s in plan.steps]}


def main(argv: list[str] | None = None) -> int:
    from pathlib import Path

    from app.core.graph.writer import neo4j_from_dotenv

    args = sys.argv[1:] if argv is None else argv
    if not args:
        print("usage: python -m app.core.graph.plan svc:<service> [--case NAME] [--json]")
        return 2
    from neo4j import GraphDatabase

    repo = Path(__file__).resolve().parents[6]
    conf = neo4j_from_dotenv(repo / ".env")
    if conf is None:
        print(f"no NEO4J_PASSWORD in {repo / '.env'}")
        return 2
    uri, user, password = conf
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        case = args[args.index("--case") + 1] if "--case" in args else None
        plan = build_plan(driver, args[0], case)
        if plan is None:
            print(f"{args[0]} is not in the graph.")
            return 1
        print(json.dumps(to_dict(plan), indent=2, ensure_ascii=False) if "--json" in args
              else render_text(plan))
        return 0
    finally:
        driver.close()


if __name__ == "__main__":
    raise SystemExit(main())
