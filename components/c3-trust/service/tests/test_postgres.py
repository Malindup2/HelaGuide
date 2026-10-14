"""Runs only when you point it at a real PostgreSQL:
       $env:C3_TEST_PG_URL="postgresql://c3:c3pass@localhost:5433/c3_pp1" ; pytest
"""
import os

import pytest

from app.core import db
from app.core.pipeline import Pipeline
from tests.helpers import make_settings
from tests.pipeline_fixtures import ds, run  # noqa: F401

URL = os.environ.get("C3_TEST_PG_URL")
pytestmark = pytest.mark.skipif(not URL, reason="set C3_TEST_PG_URL to test against PostgreSQL")


def test_full_story_on_postgres(ds):
    p = Pipeline.build(make_settings(database_url=URL), reset=True)
    p.load_reporters(); p.sync_facts()
    for mid in ["ft-A1", "fb-A2", "ft-A3", "fb-A4", "ft-A5", "ft-A6"]:
        r = run(p, ds, mid)
    assert r.confidence["status"] == "flagged"
    p.source.publish_updates(p.s.data_dir / "c2_facts_updates.json")
    p.sync_facts()
    assert p.exposure.explain("svc:passport:fee:normal")["confidence_pct"] == 90
    assert db.is_postgres(p.engine)


def test_tables_live_in_schema_c3():
    engine = db.make_engine(URL)
    db.reset_db(engine)
    with engine.connect() as c:
        rows = c.exec_driver_sql("select table_name from information_schema.tables where table_schema='c3'").fetchall()
    assert {"fact_confidence", "reports", "reporters"} <= {r[0] for r in rows}


def test_reset_refuses_a_database_that_is_not_c3s():
    other = URL.rsplit("/", 1)[0] + "/other_db"
    engine = db.make_engine(other)
    with pytest.raises(RuntimeError, match="Refusing to reset"):
        db.reset_db(engine)
