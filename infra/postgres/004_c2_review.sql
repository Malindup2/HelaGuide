-- C2 review gate: every decision on a staged fact, kept forever.
-- Nothing reaches Neo4j without an 'approved' row here.
--
-- Apply by hand to an existing database (001 only runs on a fresh volume):
--   docker compose exec -T postgres psql -U helaguide -d helaguide < infra/postgres/004_c2_review.sql
-- Idempotent: safe to run again. Requires 003_c2_extraction.sql.

CREATE TABLE IF NOT EXISTS c2.review_log (
    review_id  BIGSERIAL PRIMARY KEY,
    staged_id  BIGINT NOT NULL REFERENCES c2.staged_facts(staged_id) ON DELETE CASCADE,
    fact_id    TEXT NOT NULL,                      -- copied so the audit reads on its own
    decision   TEXT NOT NULL CHECK (decision IN ('approved', 'rejected')),
    reason     TEXT,
    reviewer   TEXT NOT NULL,
    decided_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS review_log_staged_idx ON c2.review_log (staged_id);
CREATE INDEX IF NOT EXISTS review_log_fact_idx   ON c2.review_log (fact_id, decided_at DESC);

-- Set once the graph writer has put an approved fact into Neo4j, so a fact is written once.
ALTER TABLE c2.staged_facts ADD COLUMN IF NOT EXISTS written_at TIMESTAMPTZ;
