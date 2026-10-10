-- C2 operational state: what the crawler has seen and done. No personal data.
-- Neo4j holds the approved public knowledge; this schema holds how it was acquired.
--
-- The 001 file only runs on a fresh volume. On an existing database apply this one by hand:
--   docker compose exec -T postgres psql -U helaguide -d helaguide < infra/postgres/002_c2.sql
-- It is idempotent: safe to run again.

CREATE SCHEMA IF NOT EXISTS c2;   -- Malindu: acquisition, staging and review

-- One row per agency site.
CREATE TABLE IF NOT EXISTS c2.sources (
    source_id      SERIAL PRIMARY KEY,
    host           TEXT NOT NULL UNIQUE,
    agency         TEXT,
    robots_allowed BOOLEAN,                       -- null until robots.txt has been read
    needs_browser  BOOLEAN NOT NULL DEFAULT false,
    tls_relaxed    BOOLEAN NOT NULL DEFAULT false,
    notes          TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per URL ever seen. status is the life of a page:
--   discovered -> candidate (scored) -> verified (a human read it) -> monitored (crawled each run)
--   parked: blocked, irrelevant or out of scope. Rows are never deleted.
CREATE TABLE IF NOT EXISTS c2.pages (
    page_id         SERIAL PRIMARY KEY,
    url             TEXT NOT NULL UNIQUE,
    source_id       INTEGER REFERENCES c2.sources(source_id),
    service_id      TEXT,                          -- svc:<slug>, see contracts/naming.md
    agency          TEXT,
    source_type     TEXT NOT NULL DEFAULT 'html' CHECK (source_type IN ('html', 'pdf')),
    status          TEXT NOT NULL DEFAULT 'discovered'
                    CHECK (status IN ('discovered', 'candidate', 'verified', 'monitored', 'parked')),
    discovered_from TEXT,                          -- the page whose links led here
    has_fee         BOOLEAN,
    has_docs        BOOLEAN,
    has_prereq      BOOLEAN,
    signal_score    INTEGER,
    note            TEXT,
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS pages_status_idx  ON c2.pages (status);
CREATE INDEX IF NOT EXISTS pages_service_idx ON c2.pages (service_id);

-- One row per monitoring pass.
CREATE TABLE IF NOT EXISTS c2.crawl_runs (
    run_id      TEXT PRIMARY KEY,
    started_at  TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    mode        TEXT NOT NULL DEFAULT 'http',      -- http | browser
    pages       INTEGER,
    counts      JSONB,                             -- {"NEW": 4, "UNREACHABLE": 2}
    to_extract  INTEGER
);

-- One row per page per run. The durable hand-off to extraction.
CREATE TABLE IF NOT EXISTS c2.page_results (
    result_id      BIGSERIAL PRIMARY KEY,
    run_id         TEXT NOT NULL REFERENCES c2.crawl_runs(run_id) ON DELETE CASCADE,
    page_id        INTEGER REFERENCES c2.pages(page_id),
    url            TEXT NOT NULL,
    change_class   TEXT NOT NULL,                  -- NEW | UNCHANGED | CONTENT_CHANGED | STRUCTURE_CHANGED | UNREACHABLE
    http_status    INTEGER,
    source_type    TEXT NOT NULL DEFAULT 'html',
    tls_relaxed    BOOLEAN NOT NULL DEFAULT false,
    duration_ms    INTEGER,
    content_hash   TEXT,
    structure_hash TEXT,
    char_count     INTEGER,
    error          TEXT,
    detail         JSONB,
    fetched_at     TIMESTAMPTZ NOT NULL,
    file_path      TEXT                            -- archived Markdown, relative to the crawl root
);
-- For databases created before file_path existed.
ALTER TABLE c2.page_results ADD COLUMN IF NOT EXISTS file_path TEXT;
CREATE INDEX IF NOT EXISTS page_results_run_idx  ON c2.page_results (run_id);
CREATE INDEX IF NOT EXISTS page_results_page_idx ON c2.page_results (page_id, fetched_at DESC);
