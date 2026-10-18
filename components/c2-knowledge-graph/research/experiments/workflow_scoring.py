"""SO5: workflow-correctness evaluation. Scores the graph's ordered plan, and a lexical
text-search baseline (the B3 comparison from the proposal -- "does a similarity-ranked
system produce a correctly ordered multi-agency procedure"), against a hand-built
ground-truth journey set. Programmatic only: exact match and set match, no LLM judge.

The ground truth below is written from the real-world process (what a citizen genuinely
needs), not copied from the graph's own output -- scoring a system against its own answer
would prove nothing. Two journeys (J3, J6) are deliberately included even though they
depend on svc:police_clearance, which has no facts (police.lk blocks crawlers, a known,
documented limitation) -- an honest evaluation set does not hide the cases where the
system is known to be incomplete.

    python research/experiments/workflow_scoring.py
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parents[1] / "service"
sys.path.insert(0, str(SERVICE_DIR))

from app.admin_ui import _dsn, _neo4j  # noqa: E402
from app.core.graph.plan import build_plan  # noqa: E402
from app.core.knowledge.chunks import search as chunk_search  # noqa: E402
from neo4j import GraphDatabase  # noqa: E402


@dataclass
class Journey:
    id: str
    question: str
    requested: str
    # The correct order a citizen must complete these in. The requested service is last.
    ground_truth: list[str]
    note: str = ""


JOURNEYS = [
    Journey("J1", "I need a passport for the first time, what do I need?",
            "svc:passport", ["svc:birth_certificate", "svc:nic", "svc:passport"]),
    Journey("J2", "How do I get my first NIC?",
            "svc:nic", ["svc:birth_certificate", "svc:nic"]),
    Journey("J3", "I want to apply for dual citizenship",
            "svc:dual_citizenship",
            ["svc:birth_certificate", "svc:nic", "svc:passport", "svc:police_clearance", "svc:dual_citizenship"],
            note="depends on svc:police_clearance, which has no facts (police.lk blocks crawlers). "
                 "nic is included because it is transitively required: dual citizenship needs a "
                 "passport, and a passport itself needs an nic"),
    Journey("J4", "How do I register my marriage?",
            "svc:registration_of_marriages_general",
            ["svc:birth_certificate", "svc:nic", "svc:registration_of_marriages_general"]),
    Journey("J5", "I need to register a power of attorney",
            "svc:registration_of_power_of_attorney",
            ["svc:birth_certificate", "svc:nic", "svc:registration_of_power_of_attorney"],
            note="birth_certificate is transitively required: this needs an nic, and an nic needs "
                 "a birth certificate"),
    Journey("J6", "What do I need for a permanent residence visa?",
            "svc:permanent_residence_visa",
            ["svc:birth_certificate", "svc:nic", "svc:passport", "svc:police_clearance",
             "svc:permanent_residence_visa"],
            note="depends on svc:police_clearance, which has no facts"),
    Journey("J7", "I want to renounce my citizenship",
            "svc:renunciation_of_citizenship",
            ["svc:birth_certificate", "svc:nic", "svc:passport", "svc:renunciation_of_citizenship"]),
    Journey("J8", "I need to change the name on my passport",
            "svc:passport_alteration",
            ["svc:birth_certificate", "svc:nic", "svc:passport_alteration"],
            note="does NOT require svc:passport first -- you already hold the passport being altered"),
    Journey("J9", "How do I register for VAT?",
            "svc:value_added_tax",
            ["svc:nic", "svc:taxpayer_identification_number_tin", "svc:value_added_tax"],
            note="real-world processes usually need a TIN first; checking whether the graph agrees"),
    Journey("J10", "I need a taxpayer identification number",
            "svc:taxpayer_identification_number_tin",
            ["svc:nic", "svc:taxpayer_identification_number_tin"],
            note="ground truth omits svc:passport even though the graph lists it as a prerequisite -- "
                 "a citizen's TIN application needs the NIC; passport is realistically an alternate ID "
                 "for foreign nationals, not a universal prerequisite"),
]


def _url_to_services(dsn: str) -> dict[str, set[str]]:
    import psycopg

    out: dict[str, set[str]] = {}
    with psycopg.connect(dsn) as c:
        for url, sid in c.execute(
                "SELECT DISTINCT source_url, service_id FROM c2.staged_facts WHERE status='approved'"):
            out.setdefault(url, set()).add(sid)
    return out


def _baseline_answer(dsn: str, question: str, url_map: dict[str, set[str]], limit: int = 8) -> set[str]:
    hits = chunk_search(dsn, question, limit=limit)
    found: set[str] = set()
    for h in hits:
        found |= url_map.get(h["url"], set())
    return found


def main() -> None:
    dsn = _dsn()
    uri, user, pw = _neo4j()
    driver = GraphDatabase.driver(uri, auth=(user, pw))
    url_map = _url_to_services(dsn)

    graph_exact = graph_set = baseline_set = 0
    rows = []
    for j in JOURNEYS:
        plan = build_plan(driver, j.requested)
        graph_order = [s.service_id for s in plan.steps] if plan else []
        g_exact = graph_order == j.ground_truth
        g_set = set(graph_order) == set(j.ground_truth)
        graph_exact += g_exact
        graph_set += g_set

        baseline = _baseline_answer(dsn, j.question, url_map)
        b_set = baseline == set(j.ground_truth)
        baseline_set += b_set

        rows.append((j, graph_order, g_exact, g_set, baseline, b_set))

    n = len(JOURNEYS)
    print(f"{n} journeys\n")
    print(f"{'ID':4} {'exact':6} {'set':4} {'base-set':9}  question")
    for j, go, ge, gs, b, bs in rows:
        print(f"{j.id:4} {'YES' if ge else 'no':6} {'YES' if gs else 'no':4} {'YES' if bs else 'no':9}  {j.question}")
        print(f"      graph:    {go}")
        print(f"      expected: {j.ground_truth}")
        print(f"      baseline: {sorted(b)}")
        if j.note:
            print(f"      note: {j.note}")
        print()

    print("=" * 70)
    print(f"Graph exact match:    {graph_exact}/{n}  ({100*graph_exact/n:.0f}%)   target: 85%")
    print(f"Graph set match:      {graph_set}/{n}  ({100*graph_set/n:.0f}%)   target: 95%")
    print(f"Baseline set match:   {baseline_set}/{n}  ({100*baseline_set/n:.0f}%)   (lexical search; cannot produce order at all)")
    print(f"Baseline exact match: 0/{n}  (0%)  -- structural: text search returns an unordered set, never a sequence")
    driver.close()


if __name__ == "__main__":
    main()
