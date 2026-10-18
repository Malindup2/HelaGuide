"""Real (non-stub) /v1/plan. _pick_fee is pure and runs anywhere; plan_for needs a live
Neo4j and skips when it is not reachable, matching tests/test_graph_writer.py.
"""

from pathlib import Path

import pytest

from app.core.graph.writer import neo4j_from_dotenv
from app.core.graph.plan import Item
from app.core.workflow import _pick_fee

REPO_ROOT = Path(__file__).resolve().parents[4]


def _item(qualifier: str, amount: float | None) -> Item:
    return Item(fact_id=f"svc:x:fee:{qualifier}", value=str(amount), qualifier=qualifier,
               unit="LKR", amount=amount, source_url="https://example.gov.lk", quote="q", review="")


# ------------------------------------------------------------------- _pick_fee
def test_first_issue_is_preferred_over_a_qualifier_that_merely_contains_standard():
    # amended_standard would win a plain "standard" substring match if it came first in
    # the list; first_issue must be tried before that generic fallback (the real bug this
    # guards: svc:nic returned the amended fee for a first-time applicant).
    fees = [_item("amended_standard", 500.0), _item("first_issue_standard", 200.0)]
    assert _pick_fee(fees).qualifier == "first_issue_standard"


def test_a_fee_with_no_amount_is_skipped_in_favour_of_one_that_has_one():
    fees = [_item("standard", None), _item("one_day", 2000.0)]
    assert _pick_fee(fees).qualifier == "one_day"


def test_no_priced_fee_returns_none():
    assert _pick_fee([_item("standard", None)]) is None


def test_empty_list_returns_none():
    assert _pick_fee([]) is None


# ------------------------------------------------------------------- plan_for (real graph)
@pytest.fixture
def real_env(monkeypatch):
    conf = neo4j_from_dotenv(REPO_ROOT / ".env")
    if conf is None:
        pytest.skip("no .env with NEO4J_* settings")
    uri, user, password = conf
    monkeypatch.setenv("NEO4J_URI", uri)
    monkeypatch.setenv("NEO4J_USER", user)
    monkeypatch.setenv("NEO4J_PASSWORD", password)
    monkeypatch.setenv("STUB_MODE", "false")
    from app.core.graph.driver import get_driver
    get_driver.cache_clear()
    try:
        get_driver().verify_connectivity()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"Neo4j is not reachable: {type(e).__name__}")
    yield
    get_driver.cache_clear()


def test_a_real_plan_is_ordered_with_dependencies_before_the_service_that_needs_them(real_env):
    from app.core.workflow import plan_for

    plan = plan_for("svc:passport", "ordinary")
    if plan is None:
        pytest.skip("svc:passport is not in this graph")
    ids = [s.service_id for s in plan.steps]
    assert ids.index("svc:nic") < ids.index("svc:passport")
    for step in plan.steps:
        assert step.fee.value >= 0
        assert all(d in ids for d in step.depends_on)


def test_an_unknown_service_returns_none(real_env):
    from app.core.workflow import plan_for

    assert plan_for("svc:this_service_does_not_exist") is None
