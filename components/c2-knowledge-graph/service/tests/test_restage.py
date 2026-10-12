"""Re-processing a stored model reply, and filing it under a different service. Needs Postgres."""

import json
import uuid
from pathlib import Path

import pytest

from app.core.extraction.extractor import ExtractionResult
from app.core.extraction.restage import restage
from app.core.extraction.staging import StagingStore

REPO_ROOT = Path(__file__).resolve().parents[4]
PAGE = """## Other services
English translation of the National Identity card. Fee: Rs.2000/- paid at the head office cashier.
Bring the National Identity card (undamaged clear National Identity card should be provided).
"""
REPLY = {
    "fees": [{"qualifier": "standard", "amount_text": "Rs.2000/-",
              "evidence": "Fee: Rs.2000/- paid at the head office cashier."}],
    "documents": [{"name": "National Identity card",
                   "evidence": "Bring the National Identity card (undamaged clear National Identity card should be provided)."}],
}


@pytest.fixture
def stored(tmp_path):
    import psycopg

    from app.core.acquisition.db import dsn_from_dotenv

    dsn = dsn_from_dotenv(REPO_ROOT / ".env")
    if dsn is None:
        pytest.skip("no .env with POSTGRES_* settings")
    try:
        with psycopg.connect(dsn, connect_timeout=3) as c:
            c.execute("SELECT raw_reply FROM c2.extractions LIMIT 1")
    except Exception as e:
        pytest.skip(f"c2 tables not reachable: {type(e).__name__}")

    host = f"pgtest-{uuid.uuid4().hex[:8]}.invalid"
    url = f"https://{host}/other"
    page = tmp_path / "other.md"
    page.write_text(PAGE, encoding="utf-8")
    store = StagingStore(dsn)
    result = ExtractionResult(model="fake", raw_reply=json.dumps(REPLY))
    ext_id, _ = store.save(url, result, "svc:nic", "DRP", source_file=str(page))
    yield dsn, ext_id, url
    with psycopg.connect(dsn, autocommit=True) as c:
        c.execute("DELETE FROM c2.staged_facts WHERE source_url = %s", (url,))
        c.execute("DELETE FROM c2.extractions WHERE source_url = %s", (url,))
        c.execute("DELETE FROM c2.pages WHERE url = %s", (url,))
        c.execute("DELETE FROM c2.sources WHERE host = %s", (host,))
    store.close()


def test_reprocessing_uses_the_stored_reply_and_saves_new_pending_facts(stored):
    dsn, ext_id, _ = stored
    new_id, facts, dropped, staged = restage(dsn, ext_id, REPO_ROOT)
    assert new_id and new_id != ext_id
    assert {f.fact_id for f in facts} == {"svc:nic:fee:standard", "svc:nic:document:national_identity_card"}
    assert staged == 2 and dropped == []


def test_filing_under_another_service_rebuilds_ids_and_links_back_to_the_nic(stored):
    dsn, ext_id, _ = stored
    _, facts, _, _ = restage(dsn, ext_id, REPO_ROOT, dry_run=True, service_id="svc:nic_translation")
    ids = {f.fact_id for f in facts}
    assert "svc:nic_translation:fee:standard" in ids
    assert "svc:nic_translation:document:national_identity_card" in ids
    link = next(f for f in facts if f.predicate == "prerequisite")
    assert link.detail["requires_service"] == "svc:nic"       # translating a card needs the card
    assert all(f.service_id == "svc:nic_translation" for f in facts)


def test_a_dry_run_saves_nothing(stored):
    import psycopg

    dsn, ext_id, url = stored
    restage(dsn, ext_id, REPO_ROOT, dry_run=True, service_id="svc:nic_translation")
    with psycopg.connect(dsn) as c:
        n = c.execute("SELECT count(*) FROM c2.staged_facts WHERE source_url = %s", (url,)).fetchone()[0]
    assert n == 0


def test_an_extraction_without_a_stored_reply_says_so(stored):
    import psycopg

    dsn, _, url = stored
    store = StagingStore(dsn)
    old, _ = store.save(url, ExtractionResult(model="old"), "svc:nic", "DRP")
    store.close()
    with pytest.raises(LookupError, match="no stored reply"):
        restage(dsn, old, REPO_ROOT)
    assert psycopg


def test_refiling_a_page_that_was_read_by_sections_is_refused_not_ignored(stored, tmp_path):
    import json

    from app.core.extraction.staging import StagingStore

    dsn, _, url = stored
    sections_reply = {"services": [{"title": "Translation", "slug": "nic_translation", "is_service": True,
                                    "fees": [{"qualifier": "standard", "amount_text": "Rs.2000/-",
                                              "evidence": "Fee: Rs.2000/- paid at the head office cashier."}]}]}
    page = tmp_path / "sections.md"
    page.write_text(PAGE, encoding="utf-8")
    store = StagingStore(dsn)
    ext, _ = store.save(url, ExtractionResult(model="fake [sections]", raw_reply=json.dumps(sections_reply)),
                        "svc:nic", "DRP", source_file=str(page))
    store.close()
    with pytest.raises(LookupError, match="read by sections"):
        restage(dsn, ext, REPO_ROOT, dry_run=True, service_id="svc:something_else")
    # without an override it re-processes normally, under the model's own service names
    _, facts, _, _ = restage(dsn, ext, REPO_ROOT, dry_run=True)
    assert {f.service_id for f in facts} == {"svc:nic_translation"}
