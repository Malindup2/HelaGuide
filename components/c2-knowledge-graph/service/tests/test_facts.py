"""Real (non-stub) /v1/facts/{id}. Skips when Neo4j is not reachable, matching
tests/test_graph_writer.py and tests/test_workflow.py.
"""

from pathlib import Path

import pytest

from app.core.graph.writer import neo4j_from_dotenv

REPO_ROOT = Path(__file__).resolve().parents[4]


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


def _any_real_fact_id(session) -> str | None:
    row = session.run("MATCH (f:Fact) WHERE f.valid_to IS NULL RETURN f.fact_id AS fid LIMIT 1").single()
    return row["fid"] if row else None


def test_a_real_fact_has_a_python_datetime_not_the_driver_s_own_type(real_env):
    # The real bug this guards: neo4j.time.DateTime is not a datetime.datetime, and
    # Pydantic rejects it outright -- every timestamp from the driver must be converted
    # before it reaches the contract model.
    from datetime import datetime

    from app.core.facts import get
    from app.core.graph.driver import get_driver

    with get_driver().session() as s:
        fid = _any_real_fact_id(s)
    if fid is None:
        pytest.skip("no facts in this graph")
    fact = get(fid)
    assert isinstance(fact.valid_from, datetime)
    assert isinstance(fact.retrieved_at, datetime)
    for h in fact.history:
        assert isinstance(h.valid_from, datetime)


def test_a_fact_with_a_closed_version_carries_its_history(real_env):
    from app.core.facts import get

    fact = get("svc:nic:fee:first_issue_standard")
    if fact is None:
        pytest.skip("that fact is not in this graph")
    assert fact.valid_to is None
    for h in fact.history:
        assert h.valid_to is not None  # only closed versions appear in history


def test_an_unknown_fact_returns_none(real_env):
    from app.core.facts import get

    assert get("svc:nic:fee:not_a_real_qualifier") is None
