"""Module R: the fact registry, C3's ownership of confidence, version changes, reputation verdicts."""
from datetime import date, datetime, timezone

import pytest

from app.core.catalog import ServiceCatalog
from app.core.db import make_engine, reset_db
from app.core.embeddings import HashEmbedder
from app.core.factsource import FileFactSource
from app.core.registry import Registry, initial_confidence
from app.core.repo import Repo
from app.models.internal import Reporter, ReportRow
from tests.helpers import make_settings

FACT = "svc:passport:fee:normal"


def build(**over):
    s = make_settings(**over)
    engine = make_engine(s.database_url)
    reset_db(engine)
    repo = Repo(engine)
    reg = Registry(repo, HashEmbedder(), ServiceCatalog(s.data_dir / "service_aliases.json"), s)
    return s, repo, reg


@pytest.fixture
def env():
    s, repo, reg = build()
    src = FileFactSource(s.data_dir / "c2_facts.json")
    reg.sync(src)
    return s, repo, reg, src


def dt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def fake_report(repo, rid, reporter, fact_id, valid_from, claimed, indep=1.0, kind="dispute"):
    """Store a report directly, so the registry's verdicts can be tested without the rest of the pipeline."""
    repo.ensure_reporter(reporter, dt("2026-01-01T00:00:00Z"))
    repo.insert_report(ReportRow(
        report_id=rid, message_id=rid, path="freetext", reporter_id=reporter, raw_text="x", text_en="x",
        language="en", fact_id=fact_id, fact_valid_from=valid_from, discrepancy_type="fee", report_kind=kind,
        claimed_value_raw=None if claimed is None else str(claimed), claimed_num=claimed,
        claimed_key="unspecified" if claimed is None else f"num:{claimed:g}", visit_date=None,
        submitted_at=dt("2026-10-20T10:00:00Z"), trust_t=0.8, sig_r=0.5, sig_s=0.5, sig_c=0.5, sig_v=0.5,
        v_imputed=False, dup_count=0, indep_i=indep, state="active"))


def test_every_fact_version_gets_a_confidence_record_owned_by_c3(env):
    s, repo, reg, src = env
    facts = repo.list_current_facts()
    assert len(facts) == len(src.list_facts()) >= 50
    for f in facts:
        rec = repo.get_confidence(f.fact_id, f.valid_from)
        assert rec.confidence == pytest.approx(0.9) and rec.status == "active" and rec.base_confidence == 0.9


def test_registry_sync_twice_changes_nothing(env):
    s, repo, reg, src = env
    n = len(repo.list_current_facts())
    results = reg.sync(src)
    assert not any(r.created or r.new_version for r in results)
    assert len(repo.list_current_facts()) == n


def test_the_fact_id_survives_a_value_change_but_the_version_does_not(env):
    s, repo, reg, src = env
    old = repo.current_version(FACT)
    src.publish_updates(s.data_dir / "c2_facts_updates.json")
    res = [r for r in reg.sync(src) if r.fact_id == FACT][0]
    new = repo.current_version(FACT)
    assert res.new_version and new.fact_id == old.fact_id == FACT
    assert new.valid_from > old.valid_from and new.value_text == "12000"
    assert repo.get_version(FACT, old.valid_from).valid_to == new.valid_from          # old version closed
    assert len(repo.versions(FACT)) == 2
    assert repo.get_confidence(FACT, new.valid_from).confidence == pytest.approx(0.9)  # fresh record


def test_unverified_connection_lowers_the_starting_confidence():
    s, repo, reg = build(unverified_hosts=["www.immigration.gov.lk"])
    reg.sync(FileFactSource(s.data_dir / "c2_facts.json"))
    v = repo.current_version(FACT)
    assert v.connection_unverified
    assert repo.get_confidence(FACT, v.valid_from).confidence == pytest.approx(0.9 * 0.85)
    assert initial_confidence(s, False) == 0.9


def test_earlier_reports_are_judged_against_the_new_official_value(env):
    s, repo, reg, src = env
    old = repo.current_version(FACT)
    fake_report(repo, "r1", "anon-a", FACT, old.valid_from, 12000.0)
    fake_report(repo, "r2", "anon-b", FACT, old.valid_from, 12000.0, indep=0.6)     # a copy earns less
    fake_report(repo, "r3", "anon-c", FACT, old.valid_from, 11000.0, kind="support")  # backed the old value
    fake_report(repo, "r4", "anon-d", FACT, old.valid_from, None)                   # no specific claim
    src.publish_updates(s.data_dir / "c2_facts_updates.json")
    res = [r for r in reg.sync(src) if r.fact_id == FACT][0]
    outcome = {v.report_id: v.outcome for v in res.verdicts}
    assert outcome == {"r1": "verified_by_source", "r2": "verified_by_source",
                       "r3": "contradicted_by_source", "r4": "superseded"}
    assert repo.get_reporter("anon-a").a == pytest.approx(1.0)
    assert repo.get_reporter("anon-b").a == pytest.approx(0.6)
    assert repo.get_reporter("anon-c").b == pytest.approx(0.5)
    assert repo.get_reporter("anon-d").a == 0 == repo.get_reporter("anon-d").b
    new = repo.current_version(FACT)
    assert repo.get_confidence(FACT, new.valid_from).verified_by_source is True


def test_reputation_cannot_be_farmed_faster_than_the_daily_cap(env):
    s, repo, reg, src = env
    repo.upsert_reporter(Reporter("anon-x", dt("2026-01-01T00:00:00Z"), a=4, b=1))
    repo.apply_reputation("anon-x", 5.0, 0.0, date(2026, 11, 1), 2.0)
    assert repo.get_reporter("anon-x").a == pytest.approx(6.0)             # only 2.0 of the 5.0 was applied
    repo.apply_reputation("anon-x", 1.0, 0.0, date(2026, 11, 1), 2.0)
    assert repo.get_reporter("anon-x").a == pytest.approx(6.0)             # today's room is used up
    repo.apply_reputation("anon-x", 1.0, 0.0, date(2026, 11, 2), 2.0)
    assert repo.get_reporter("anon-x").a == pytest.approx(7.0)             # a new day, new room


def test_facts_are_described_in_plain_english(env):
    s, repo, reg, src = env
    assert repo.current_version(FACT).description == "Passport: normal fee is LKR 11,000"
    nic = repo.current_version("svc:nic:document:icao_photograph")
    assert nic.description == "National Identity Card (NIC): required document - ICAO standard photograph from a registered studio"
