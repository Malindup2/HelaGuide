"""Plan traversal over a tiny in-memory graph: ordering, missing facts, cycles, case filter."""

import json

from app.core.graph.plan import build_plan, render_text


class FakeGraph:
    """Answers the three queries the planner makes, from plain dicts."""

    def __init__(self, requires, facts):
        self.requires, self.facts = requires, facts

    def session(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def run(self, query, **kw):
        sid = kw["sid"]
        if "count(s)" in query:
            known = sid in self.requires or sid in self.facts
            return _Rows([{"n": 1 if known else 0}])
        if "REQUIRES" in query:
            return _Rows([{"t": t} for t in sorted(self.requires.get(sid, []))])
        return _Rows(self.facts.get(sid, []))


class _Rows(list):
    def single(self):
        return self[0]


def fact(pred, qual, value, url="https://x.lk/p", detail=None, amount=None, unit=None):
    return {"fact_id": f"svc:s:{pred}:{qual}", "predicate": pred, "qualifier": qual, "value": value,
            "amount": amount, "unit": unit, "quote": value, "review": "human", "url": url,
            "detail": json.dumps(detail or {})}


def test_prerequisites_come_before_the_service_that_needs_them():
    g = FakeGraph({"svc:passport": ["svc:nic", "svc:birth"], "svc:nic": ["svc:birth"]},
                  {"svc:passport": [fact("fee", "normal", "Rs. 10,000", amount=10000, unit="LKR")],
                   "svc:nic": [fact("fee", "normal", "Rs. 200", amount=200, unit="LKR")],
                   "svc:birth": []})
    plan = build_plan(g, "svc:passport")
    assert [s.service_id for s in plan.steps] == ["svc:birth", "svc:nic", "svc:passport"]
    assert plan.steps[-1].depends_on == ["svc:birth", "svc:nic"]


def test_a_required_service_with_no_facts_is_listed_as_incomplete_not_dropped():
    g = FakeGraph({"svc:a": ["svc:b"]}, {"svc:a": [fact("fee", "normal", "Rs. 1", amount=1, unit="LKR")]})
    plan = build_plan(g, "svc:a")
    assert plan.incomplete == ["svc:b"]
    assert "INCOMPLETE" in render_text(plan)


def test_an_unknown_service_is_none():
    assert build_plan(FakeGraph({}, {}), "svc:nope") is None


def test_a_cycle_is_reported_and_does_not_loop_forever():
    g = FakeGraph({"svc:a": ["svc:b"], "svc:b": ["svc:a"]}, {"svc:a": [fact("fee", "n", "1")],
                                                              "svc:b": [fact("fee", "n", "1")]})
    plan = build_plan(g, "svc:a")
    assert plan.cycle and plan.cycle[0] == plan.cycle[-1]


def test_a_case_keeps_its_own_fees_and_documents_and_drops_the_others():
    docs = [fact("document", "birth", "Birth certificate", detail={"applies_to": ["ordinary", "minor"]}),
            fact("document", "court", "Court order", detail={"applies_to": ["minor"]}),
            fact("document", "form", "Application form", detail={"applies_to_all": True})]
    fees = [fact("fee", "ordinary_normal", "Rs. 10,000"), fact("fee", "minor_normal_3y", "Rs. 3,000")]
    g = FakeGraph({}, {"svc:p": docs + fees})
    plan = build_plan(g, "svc:p", case="ordinary")
    step = plan.steps[0]
    assert plan.cases == ["minor", "ordinary"]
    assert {d.value for d in step.documents} == {"Birth certificate", "Application form"}
    assert [f.qualifier for f in step.fees] == ["ordinary_normal"]
    # without a case everything is listed
    assert len(build_plan(g, "svc:p").steps[0].documents) == 3


def test_a_derived_requires_link_is_an_edge_not_a_written_step():
    g = FakeGraph({"svc:a": ["svc:b"]},
                  {"svc:a": [fact("prerequisite", "nic", "svc:b", detail={"requires_service": "svc:b"}),
                             fact("prerequisite", "gn", "Grama Niladhari attests the form")],
                   "svc:b": [fact("fee", "n", "1")]})
    step = build_plan(g, "svc:a").steps[-1]
    assert [i.value for i in step.steps] == ["Grama Niladhari attests the form"]
