"""PostgreSQL run log and page registry. Skipped unless the c2 schema is reachable.

Locally: docker compose up -d postgres, then apply infra/postgres/002_c2.sql. The test reads
the repo .env, so no connection string is needed. Every row it writes is removed again.
"""

import asyncio
import uuid
from pathlib import Path

import pytest

from app.core.acquisition.db import PageRegistry, PgRunLog, TeeRunLog, dsn_from_dotenv
from app.core.acquisition.fetch import FetchResult
from app.core.acquisition.monitor import JsonlRunLog, run_pass
from app.core.acquisition.seeds import Seed
from app.core.acquisition.store import SnapshotStore

REPO_ROOT = Path(__file__).resolve().parents[5]


def _dsn():
    dsn = dsn_from_dotenv(REPO_ROOT / ".env")
    if dsn is None:
        pytest.skip("no .env with POSTGRES_* settings")
    try:
        import psycopg

        with psycopg.connect(dsn, connect_timeout=3) as conn:
            conn.execute("SELECT 1 FROM c2.pages LIMIT 1")
    except Exception as e:  # not running, or 002_c2.sql not applied
        pytest.skip(f"c2 schema not reachable: {type(e).__name__}")
    return dsn


@pytest.fixture
def dsn():
    return _dsn()


@pytest.fixture
def tag(dsn):
    """A throwaway site for one test. Everything written under it is deleted afterwards."""
    import psycopg

    host = f"pgtest-{uuid.uuid4().hex[:8]}.invalid"
    yield f"https://{host}"
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("DELETE FROM c2.crawl_runs WHERE run_id IN "
                     "(SELECT run_id FROM c2.page_results WHERE url LIKE %s)", (f"%{host}%",))
        conn.execute("DELETE FROM c2.pages WHERE url LIKE %s", (f"%{host}%",))
        conn.execute("DELETE FROM c2.sources WHERE host = %s", (host,))


class Static:
    def __init__(self, text):
        self.text = text

    async def fetch(self, url):
        return FetchResult(url, True, status=200, html=f"<p>{self.text}</p>", text=self.text,
                           fetched_at="2026-10-10T08:00:00+00:00")


def test_a_pass_is_logged_to_postgres_beside_the_jsonl(dsn, tag, tmp_path):
    seed = Seed(f"{tag}/pages_e.php?id=8", "svc:passport", "Immigration", verified=True)
    pg = PgRunLog(dsn)
    pg.registry.sync_seeds([seed])
    log = TeeRunLog(JsonlRunLog(tmp_path), pg)

    summary = asyncio.run(run_pass([seed], Static("Normal Basis - LKR. 10,000.00 fee " * 12),
                                   SnapshotStore(tmp_path), log))
    conn = pg.conn
    run = conn.execute("SELECT pages, counts, to_extract FROM c2.crawl_runs WHERE run_id = %s",
                       (summary.run_id,)).fetchone()
    assert run[0] == 1 and run[1] == {"NEW": 1} and run[2] == 1

    row = conn.execute("""SELECT r.change_class, r.char_count, p.status, p.service_id, r.file_path
                          FROM c2.page_results r JOIN c2.pages p USING (page_id)
                          WHERE r.run_id = %s""", (summary.run_id,)).fetchone()
    assert row[0] == "NEW" and row[1] > 0
    assert row[2] == "monitored" and row[3] == "svc:passport"
    assert row[4].startswith("archive/") and row[4].endswith(".md")
    assert (tmp_path / row[4]).exists()  # the row really points at the saved file
    assert (tmp_path / "changes.jsonl").exists()  # the file log still works
    pg.close()


def test_registry_never_downgrades_a_status_or_duplicates_a_url(dsn, tag):
    reg = PageRegistry(dsn)
    url = f"{tag}/a"
    first = reg.page_id(url, "svc:nic", "DRP")
    reg.sync_seeds([Seed(url, "svc:nic", "DRP", verified=True)])
    assert reg.page_id(url) == first
    reg.sync_seeds([Seed(url, "svc:nic", "DRP", verified=False)])  # unverified must not demote
    status = reg.conn.execute("SELECT status FROM c2.pages WHERE page_id = %s", (first,)).fetchone()[0]
    assert status == "monitored"
    reg.close()


def test_candidates_are_recorded_with_their_parent_and_signals(dsn, tag):
    reg = PageRegistry(dsn)
    parent, child = f"{tag}/index", f"{tag}/fees"
    reg.record_candidate(child, parent, "html", has_fee=True, has_docs=False, has_prereq=False, score=1)
    row = reg.conn.execute("""SELECT status, discovered_from, has_fee, signal_score
                              FROM c2.pages WHERE url = %s""", (child,)).fetchone()
    assert row == ("candidate", parent, True, 1)
    reg.close()
