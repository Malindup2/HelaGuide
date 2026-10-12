"""The review gate against the real c2 schema. Skipped when the database is not reachable.

Every row a test writes is removed again, so it can run beside real data.
"""

import uuid
from pathlib import Path

import pytest

from app.core.extraction.extractor import ExtractionResult
from app.core.extraction.ontology import StagedFact

REPO_ROOT = Path(__file__).resolve().parents[4]
WHEN = "2026-10-11T08:00:00+00:00"


def _dsn():
    from app.core.acquisition.db import dsn_from_dotenv

    dsn = dsn_from_dotenv(REPO_ROOT / ".env")
    if dsn is None:
        pytest.skip("no .env with POSTGRES_* settings")
    try:
        import psycopg

        with psycopg.connect(dsn, connect_timeout=3) as conn:
            conn.execute("SELECT 1 FROM c2.review_log LIMIT 1")
    except Exception as e:  # not running, or 004_c2_review.sql not applied
        pytest.skip(f"c2 review tables not reachable: {type(e).__name__}")
    return dsn


@pytest.fixture
def staged():
    """Three pending facts on a throwaway site; yields (store, ids, url, service)."""
    import psycopg

    from app.core.extraction.staging import StagingStore
    from app.core.graph.review import ReviewStore

    dsn = _dsn()
    host = f"pgtest-{uuid.uuid4().hex[:8]}.invalid"
    url = f"https://{host}/p"
    svc = f"svc:t{uuid.uuid4().hex[:6]}"

    def fact(pred, q, value, num=None):
        return StagedFact(fact_id=f"{svc}:{pred}:{q}", service_id=svc, predicate=pred, qualifier=q,
                          value_text=value, source_url=url, retrieved_at=WHEN,
                          evidence=f"{value} on the page", value_num=num, unit="LKR" if num else None)

    result = ExtractionResult(facts=[fact("fee", "normal", "LKR 10,000", 10000.0),
                                     fact("fee", "urgent", "LKR 20,000", 20000.0),
                                     fact("document", "birth_certificate", "Birth Certificate")],
                              model="fake")
    stage = StagingStore(dsn)
    stage.save(url, result, svc, "Test agency")
    store = ReviewStore(dsn)
    ids = [f.staged_id for f in store.pending(svc)]
    try:
        yield store, ids, url, svc
    finally:
        with psycopg.connect(dsn, autocommit=True) as conn:
            conn.execute("DELETE FROM c2.staged_facts WHERE source_url = %s", (url,))
            conn.execute("DELETE FROM c2.extractions WHERE source_url = %s", (url,))
            conn.execute("DELETE FROM c2.pages WHERE url = %s", (url,))
            conn.execute("DELETE FROM c2.sources WHERE host = %s", (host,))
        stage.close()
        store.close()


def test_pending_facts_are_listed_for_the_service(staged):
    store, ids, _, svc = staged
    assert len(ids) == 3
    assert {f.predicate for f in store.pending(svc)} == {"fee", "document"}


def test_approving_changes_status_and_writes_the_audit_row(staged):
    store, ids, _, svc = staged
    assert store.decide(ids[0], "approved", "malindu", "matches the page") is True
    assert len(store.pending(svc)) == 2
    row = store.conn.execute(
        "SELECT decision, reviewer, reason FROM c2.review_log WHERE staged_id = %s", (ids[0],)
    ).fetchone()
    assert row == ("approved", "malindu", "matches the page")


def test_a_fact_is_decided_once(staged):
    store, ids, _, _ = staged
    assert store.decide(ids[0], "approved", "malindu") is True
    assert store.decide(ids[0], "rejected", "malindu", "changed my mind") is False
    n = store.conn.execute(
        "SELECT count(*) FROM c2.review_log WHERE staged_id = %s", (ids[0],)).fetchone()[0]
    assert n == 1  # the second attempt left no trace and changed nothing


def test_rejection_is_recorded_and_removes_it_from_the_queue(staged):
    store, ids, _, svc = staged
    store.decide(ids[1], "rejected", "malindu", "the page says 25,000")
    assert ids[1] not in [f.staged_id for f in store.pending(svc)]
    assert store.counts().get("rejected", 0) >= 1


def test_decide_many_reports_what_it_skipped(staged):
    store, ids, _, _ = staged
    store.decide(ids[0], "approved", "malindu")
    assert store.decide_many(ids, "approved", "malindu") == (2, 1)


def test_a_decision_needs_a_reviewer_and_a_known_verdict(staged):
    store, ids, _, _ = staged
    with pytest.raises(ValueError):
        store.decide(ids[0], "approved", "  ")
    with pytest.raises(ValueError):
        store.decide(ids[0], "maybe", "malindu")


def test_pending_shows_the_value_already_in_the_graph_for_the_same_position(staged):
    store, _, url, svc = staged
    first = next(f for f in store.pending(svc) if f.fact_id.endswith("fee:normal"))
    store.decide(first.staged_id, "approved", "malindu")
    # the page now says something different for the same position
    store.conn.execute(
        """INSERT INTO c2.staged_facts (fact_id, service_id, predicate, qualifier, value_text,
               value_num, unit, source_url, retrieved_at, evidence)
           VALUES (%s, %s, 'fee', 'normal', 'LKR 11,000', 11000, 'LKR', %s, %s, 'LKR 11,000 on the page')""",
        (f"{svc}:fee:normal", svc, url, WHEN))
    changed = next(f for f in store.pending(svc) if f.value_text == "LKR 11,000")
    assert changed.old_value == "LKR 10,000"


def test_renaming_a_waiting_service_moves_only_waiting_facts(staged):
    store, ids, _, svc = staged
    store.decide(ids[0], "approved", "malindu")            # a decided fact must not move
    new = svc + "_renamed"
    moved = store.rename_service(svc, new, "malindu")
    assert moved == 2
    left = {f.service_id for f in store.pending(new)}
    assert left == {new}
    assert all(f.fact_id.startswith(new + ":") for f in store.pending(new))
    decided = store.conn.execute(
        "SELECT service_id FROM c2.staged_facts WHERE staged_id = %s", (ids[0],)).fetchone()[0]
    assert decided == svc                                   # untouched


def test_a_rename_needs_a_well_formed_id(staged):
    store, _, _, svc = staged
    with pytest.raises(ValueError):
        store.rename_service(svc, "Not A Service", "malindu")
