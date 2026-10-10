-- C2 extraction: what the language model read, and the facts it proposed.
-- Facts land here as 'pending'. Nothing reaches Neo4j without an approved decision.
--
-- Apply by hand to an existing database (001 only runs on a fresh volume):
--   docker compose exec -T postgres psql -U helaguide -d helaguide < infra/postgres/003_c2_extraction.sql
-- Idempotent: safe to run again. Requires 002_c2.sql.

-- One row per extraction call. Tokens are the real counts the provider reported.
CREATE TABLE IF NOT EXISTS c2.extractions (
    extraction_id     BIGSERIAL PRIMARY KEY,
    page_id           INTEGER REFERENCES c2.pages(page_id),
    source_url        TEXT NOT NULL,
    model             TEXT,
    prompt_tokens     INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    facts             INTEGER NOT NULL DEFAULT 0,
    dropped           INTEGER NOT NULL DEFAULT 0,   -- items whose quote was not on the page
    truncated         BOOLEAN NOT NULL DEFAULT false,
    error             TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS extractions_page_idx ON c2.extractions (page_id, created_at DESC);

-- One row per proposed fact. fact_id comes from position (contracts/naming.md), never value.
CREATE TABLE IF NOT EXISTS c2.staged_facts (
    staged_id     BIGSERIAL PRIMARY KEY,
    extraction_id BIGINT REFERENCES c2.extractions(extraction_id) ON DELETE CASCADE,
    fact_id       TEXT NOT NULL CHECK (fact_id ~ '^svc:[a-z0-9_]+:[a-z0-9_]+(:[a-z0-9_]+)?$'),
    service_id    TEXT NOT NULL,
    predicate     TEXT NOT NULL
                  CHECK (predicate IN ('fee', 'document', 'agency', 'prerequisite',
                                       'processing_time', 'eligibility')),
    qualifier     TEXT,
    value_text    TEXT NOT NULL,                    -- exactly as written on the page
    value_num     NUMERIC,                          -- parsed amount, when the value is one
    unit          TEXT,
    detail        JSONB,
    source_url    TEXT NOT NULL,
    retrieved_at  TIMESTAMPTZ NOT NULL,
    evidence      TEXT NOT NULL,                    -- the quote that grounds it
    status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'approved', 'rejected')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (fact_id, value_text, source_url)
);
CREATE INDEX IF NOT EXISTS staged_facts_status_idx  ON c2.staged_facts (status);
CREATE INDEX IF NOT EXISTS staged_facts_fact_idx    ON c2.staged_facts (fact_id);
