"""PostgreSQL side of stage 1: the run log and the page registry (schema c2).

The JSONL log keeps working; this is written beside it. Schema: infra/postgres/002_c2.sql.
Install the driver first: pip install -e ".[db]"
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse

from app.core.acquisition.monitor import PageResult, RunSummary
from app.core.acquisition.seeds import Seed


def dsn_from_dotenv(path: Path) -> str | None:
    """Build a host-side DSN from the repo .env (the container DSN points at host 'postgres').

    Postgres is published on POSTGRES_HOST_PORT (5433 on a machine where 5432 is taken).
    """
    path = Path(path)
    if not path.exists():
        return None
    env: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    try:
        user, password, db = env["POSTGRES_USER"], env["POSTGRES_PASSWORD"], env["POSTGRES_DB"]
    except KeyError:
        return None
    port = env.get("POSTGRES_HOST_PORT", "5432")
    return f"postgresql://{quote(user)}:{quote(password)}@localhost:{port}/{db}"


def _connect(dsn: str):
    try:
        import psycopg
    except ImportError as e:  # pragma: no cover
        raise RuntimeError('psycopg is missing: pip install -e ".[db]"') from e
    return psycopg.connect(dsn, autocommit=True)


def _ts(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(value)


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


class PageRegistry:
    """c2.sources and c2.pages: every URL the crawler has been told about or has found."""

    def __init__(self, dsn: str) -> None:
        self.conn = _connect(dsn)

    def close(self) -> None:
        self.conn.close()

    def source_id(self, url: str, agency: str | None = None) -> int:
        row = self.conn.execute(
            """INSERT INTO c2.sources (host, agency) VALUES (%s, %s)
               ON CONFLICT (host) DO UPDATE SET agency = COALESCE(c2.sources.agency, EXCLUDED.agency)
               RETURNING source_id""",
            (_host(url), agency),
        ).fetchone()
        return row[0]

    def page_id(self, url: str, service: str | None = None, agency: str | None = None,
                source_type: str = "html") -> int:
        """Register a URL if new; always refresh last_seen_at. Never changes an existing status."""
        row = self.conn.execute(
            """INSERT INTO c2.pages (url, source_id, service_id, agency, source_type)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (url) DO UPDATE SET
                   last_seen_at = now(),
                   service_id = COALESCE(c2.pages.service_id, EXCLUDED.service_id),
                   agency     = COALESCE(c2.pages.agency, EXCLUDED.agency),
                   source_type = EXCLUDED.source_type
               RETURNING page_id""",
            (url, self.source_id(url, agency), service, agency, source_type),
        ).fetchone()
        return row[0]

    def sync_seeds(self, seeds: list[Seed]) -> None:
        """Seeds are the monitored set. A verified seed becomes 'monitored'; an unverified
        one is a 'candidate'. A status a human already set is never downgraded."""
        for s in seeds:
            pid = self.page_id(s.url, s.service, s.agency)
            self.conn.execute(
                """UPDATE c2.pages SET note = COALESCE(NULLIF(%s, ''), note),
                          status = CASE
                              WHEN %s THEN 'monitored'
                              WHEN status IN ('discovered') THEN 'candidate'
                              ELSE status END
                   WHERE page_id = %s""",
                (s.note, s.verified, pid),
            )

    def record_candidate(self, url: str, parent: str, source_type: str, *, has_fee: bool,
                         has_docs: bool, has_prereq: bool, score: int) -> None:
        pid = self.page_id(url, source_type=source_type)
        self.conn.execute(
            """UPDATE c2.pages SET discovered_from = COALESCE(discovered_from, %s),
                      has_fee = %s, has_docs = %s, has_prereq = %s, signal_score = %s,
                      status = CASE WHEN status = 'discovered' AND %s > 0 THEN 'candidate' ELSE status END
               WHERE page_id = %s""",
            (parent, has_fee, has_docs, has_prereq, score, score, pid),
        )

    def counts(self) -> dict[str, int]:
        rows = self.conn.execute("SELECT status, count(*) FROM c2.pages GROUP BY status").fetchall()
        return {status: n for status, n in rows}


class PgRunLog:
    """RunLog implementation writing c2.crawl_runs and c2.page_results."""

    def __init__(self, dsn: str, mode: str = "http") -> None:
        self.registry = PageRegistry(dsn)
        self.conn = self.registry.conn
        self.mode = mode
        self._runs: set[str] = set()

    def _ensure_run(self, run_id: str, started: str) -> None:
        if run_id in self._runs:
            return
        self.conn.execute(
            """INSERT INTO c2.crawl_runs (run_id, started_at, mode) VALUES (%s, %s, %s)
               ON CONFLICT (run_id) DO NOTHING""",
            (run_id, _ts(started), self.mode),
        )
        self._runs.add(run_id)

    def page(self, r: PageResult) -> None:
        self._ensure_run(r.run_id, r.fetched_at)
        pid = self.registry.page_id(r.url, r.service, r.agency, r.source_type)
        fp = r.fingerprint
        self.conn.execute(
            """INSERT INTO c2.page_results
                   (run_id, page_id, url, change_class, http_status, source_type, tls_relaxed,
                    duration_ms, content_hash, structure_hash, char_count, error, detail, fetched_at,
                    file_path)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (r.run_id, pid, r.url, r.kind.value, r.status, r.source_type, r.tls_relaxed,
             r.duration_ms, fp.content_hash if fp else None, fp.structure_hash if fp else None,
             fp.char_count if fp else None, r.error or None, json.dumps(r.detail),
             _ts(r.fetched_at), r.file_path or None),
        )

    def finish(self, s: RunSummary) -> None:
        self._ensure_run(s.run_id, s.started_at)
        self.conn.execute(
            """UPDATE c2.crawl_runs SET finished_at = %s, pages = %s, counts = %s, to_extract = %s
               WHERE run_id = %s""",
            (_ts(s.finished_at), len(s.pages), json.dumps(s.counts), len(s.to_extract), s.run_id),
        )

    def close(self) -> None:
        self.registry.close()


class TeeRunLog:
    """Writes every record to several logs, so the JSONL files and Postgres stay in step."""

    def __init__(self, *logs) -> None:
        self.logs = logs

    def page(self, result: PageResult) -> None:
        for log in self.logs:
            log.page(result)

    def finish(self, summary: RunSummary) -> None:
        for log in self.logs:
            log.finish(summary)
