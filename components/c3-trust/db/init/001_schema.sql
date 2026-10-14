-- Runs once, the first time the C3 database volume is created.
-- The tables themselves are created by the application (python -m app.cli.reset).
CREATE SCHEMA IF NOT EXISTS c3;
