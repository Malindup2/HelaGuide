-- Keep what the model actually said, so a code fix can re-process it without a new call.
-- Apply by hand to an existing database:
--   docker compose exec -T postgres psql -U helaguide -d helaguide < infra/postgres/005_c2_raw_reply.sql
-- Idempotent. Requires 003_c2_extraction.sql.

ALTER TABLE c2.extractions ADD COLUMN IF NOT EXISTS raw_reply   TEXT;  -- the model's reply, verbatim
ALTER TABLE c2.extractions ADD COLUMN IF NOT EXISTS source_file TEXT;  -- the page it read, relative to the repo
ALTER TABLE c2.extractions ADD COLUMN IF NOT EXISTS service_id  TEXT;
ALTER TABLE c2.extractions ADD COLUMN IF NOT EXISTS agency      TEXT;
