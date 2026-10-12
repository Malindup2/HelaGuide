-- The knowledge base: every saved page, cut into chunks that can be searched and cited.
-- Facts (fees, documents...) stay in staged_facts and the graph. This is for everything else a
-- citizen may ask: a phone number, an address, an office, how to make an RTI request.
-- Apply by hand to an existing database:
--   docker compose exec -T postgres psql -U helaguide -d helaguide < infra/postgres/006_c2_chunks.sql
-- Idempotent.

CREATE TABLE IF NOT EXISTS c2.chunks (
    chunk_id     BIGSERIAL PRIMARY KEY,
    source_url   TEXT NOT NULL,
    agency       TEXT,
    page_title   TEXT,
    heading      TEXT,                       -- the nearest heading above the text
    position     INTEGER NOT NULL,           -- order within the page
    text         TEXT NOT NULL,
    page_hash    TEXT NOT NULL,              -- hash of the saved page this came from
    source_file  TEXT,                       -- archive file, relative to the crawl root
    retrieved_at TIMESTAMPTZ NOT NULL,
    tsv          TSVECTOR GENERATED ALWAYS AS
                 (to_tsvector('english', coalesce(page_title,'') || ' ' || coalesce(heading,'') || ' ' || text)) STORED,
    UNIQUE (source_url, position)
);

CREATE INDEX IF NOT EXISTS chunks_tsv_idx ON c2.chunks USING GIN (tsv);
CREATE INDEX IF NOT EXISTS chunks_url_idx ON c2.chunks (source_url);
