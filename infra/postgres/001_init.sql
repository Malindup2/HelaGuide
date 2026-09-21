-- HelaGuide private citizen data. Runs automatically on the first Postgres start.
-- One schema per component that owns it. No names, no NIC numbers: sessions are anonymous.

CREATE SCHEMA IF NOT EXISTS c1;   -- Dabarera: conversation state
CREATE SCHEMA IF NOT EXISTS c3;   -- Minuli:   feedback and trust
CREATE SCHEMA IF NOT EXISTS c4;   -- Dias:     preferences and behaviour

-- ---------------------------------------------------------------- C1
CREATE TABLE IF NOT EXISTS c1.sessions (
    session_id   TEXT PRIMARY KEY,
    language     TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS c1.turns (
    session_id TEXT NOT NULL REFERENCES c1.sessions(session_id) ON DELETE CASCADE,
    turn_id    INTEGER NOT NULL,
    text       TEXT NOT NULL,
    intent     TEXT,
    service_id TEXT,
    confidence REAL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (session_id, turn_id)
);

-- ---------------------------------------------------------------- C3
CREATE TABLE IF NOT EXISTS c3.feedback (
    feedback_id    TEXT PRIMARY KEY,
    session_id     TEXT NOT NULL,
    fact_id        TEXT NOT NULL,
    plan_id        TEXT,
    text           TEXT NOT NULL,
    proposed_value TEXT,
    cluster_id     TEXT,
    submitted_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS feedback_fact ON c3.feedback (fact_id);

CREATE TABLE IF NOT EXISTS c3.trust_scores (
    fact_id      TEXT PRIMARY KEY,
    confidence   REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    status       TEXT NOT NULL CHECK (status IN ('ok', 'disputed', 'verified_correction')),
    report_count INTEGER NOT NULL DEFAULT 0,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- C4
CREATE TABLE IF NOT EXISTS c4.preferences (
    session_id   TEXT PRIMARY KEY,
    mode         TEXT NOT NULL DEFAULT 'standard' CHECK (mode IN ('standard', 'simplified', 'voice')),
    detail_level TEXT NOT NULL DEFAULT 'medium'   CHECK (detail_level IN ('low', 'medium', 'high')),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS c4.behaviour_signals (
    id          BIGSERIAL PRIMARY KEY,
    session_id  TEXT NOT NULL,
    signal      TEXT NOT NULL,          -- e.g. hesitation, repeated_tap, back_navigation
    value       REAL,
    step_order  INTEGER,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS signals_session ON c4.behaviour_signals (session_id);
