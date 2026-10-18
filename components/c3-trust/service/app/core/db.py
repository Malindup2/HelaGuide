"""
C3's own tables. On PostgreSQL they live in schema `c3` (search_path is set on connect);
on SQLite (used by the unit tests and --sqlite demos) they are plain tables.

Table names are deliberately different from infra/postgres/001_init.sql (c3.feedback,
c3.trust_scores) so this implementation can never collide with the team's schema.
"""
from __future__ import annotations

from sqlalchemy import (JSON, Boolean, Column, Date, DateTime, Float, Integer, LargeBinary,
                        MetaData, String, Table, Text, create_engine, text)
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool

metadata = MetaData()
TS = DateTime(timezone=True)

fact_registry = Table(
    "fact_registry", metadata,
    Column("fact_id", String(200), primary_key=True),
    Column("valid_from", TS, primary_key=True),
    Column("valid_to", TS),
    Column("service_id", String(120), nullable=False),
    Column("predicate", String(40), nullable=False),
    Column("qualifier", String(80)),
    Column("value_text", Text, nullable=False),
    Column("value_num", Float),
    Column("unit", String(20)),
    Column("description", Text),
    Column("source_url", Text),
    Column("retrieved_at", TS),
    Column("connection_unverified", Boolean, nullable=False, default=False),
    Column("embedding", LargeBinary),
)

# C3 OWNS THIS TABLE: one row per fact VERSION (the README's ownership rule).
fact_confidence = Table(
    "fact_confidence", metadata,
    Column("fact_id", String(200), primary_key=True),
    Column("valid_from", TS, primary_key=True),
    Column("base_confidence", Float, nullable=False),
    Column("confidence", Float, nullable=False),
    Column("status", String(20), nullable=False),
    Column("drop_events", Integer, nullable=False, default=0),
    Column("verified_by_source", Boolean, nullable=False, default=False),
    Column("last_updated", TS),
    Column("last_reason", Text),
)

reporters = Table(
    "reporters", metadata,
    Column("reporter_id", String(120), primary_key=True),
    Column("created_at", TS, nullable=False),
    Column("a", Float, nullable=False, default=0.0),
    Column("b", Float, nullable=False, default=0.0),
    Column("rep_day", Date),
    Column("rep_delta_today", Float, nullable=False, default=0.0),
)

reports = Table(
    "reports", metadata,
    Column("report_id", String(60), primary_key=True),
    Column("message_id", String(120), nullable=False, unique=True),
    Column("path", String(20), nullable=False),
    Column("reporter_id", String(120), nullable=False),
    Column("raw_text", Text, nullable=False),
    Column("text_en", Text),
    Column("language", String(20)),
    Column("fact_id", String(200), nullable=False),
    Column("fact_valid_from", TS, nullable=False),
    Column("discrepancy_type", String(40)),
    Column("report_kind", String(20), nullable=False),
    Column("claimed_value_raw", Text),
    Column("claimed_num", Float),
    Column("claimed_key", String(200)),
    Column("visit_date", Date),
    Column("submitted_at", TS, nullable=False),
    Column("trust_t", Float, nullable=False),
    Column("sig_r", Float), Column("sig_s", Float), Column("sig_c", Float), Column("sig_v", Float),
    Column("v_imputed", Boolean, default=False),
    Column("dup_count", Integer, default=0),
    Column("indep_i", Float, default=1.0),
    Column("state", String(30), nullable=False, default="active"),
    Column("embedding", LargeBinary),
    Column("trace", JSON),
)

confidence_audit = Table(
    "confidence_audit", metadata,
    Column("audit_id", Integer, primary_key=True, autoincrement=True),
    Column("fact_id", String(200), nullable=False),
    Column("valid_from", TS, nullable=False),
    Column("old_confidence", Float),
    Column("new_confidence", Float),
    Column("reason", Text),
    Column("report_ids", JSON),
    Column("created_at", TS),
)

unresolved_reports = Table(
    "unresolved_reports", metadata,
    Column("report_id", String(60), primary_key=True),
    Column("message_id", String(120), nullable=False, unique=True),
    Column("path", String(20)),
    Column("reporter_id", String(120)),
    Column("raw_text", Text),
    Column("text_en", Text),
    Column("service_id", String(120)),
    Column("predicate", String(40)),
    Column("state", String(40), nullable=False),
    Column("reason", Text),
    Column("trace", JSON),
    Column("created_at", TS),
)

sessions = Table(
    "sessions", metadata,
    Column("session_id", String(120), primary_key=True),
    Column("last_service_id", String(120)),
    Column("updated_at", TS),
)


def normalise_url(url: str) -> str:
    """postgresql://... -> postgresql+psycopg://... (the psycopg 3 driver)."""
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    return url


def make_engine(url: str) -> Engine:
    url = normalise_url(url)
    if url.startswith("postgresql"):
        return create_engine(url, pool_pre_ping=True,
                             connect_args={"options": "-csearch_path=c3,public"})
    if url in ("sqlite://", "sqlite:///:memory:"):
        return create_engine("sqlite://", poolclass=StaticPool,
                             connect_args={"check_same_thread": False})
    return create_engine(url, connect_args={"check_same_thread": False})


def is_postgres(engine: Engine) -> bool:
    return engine.dialect.name == "postgresql"


def init_db(engine: Engine) -> None:
    if is_postgres(engine):
        with engine.begin() as conn:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS c3"))
    metadata.create_all(engine)


def reset_db(engine: Engine) -> None:
    """Drop and recreate C3's own tables only. Never touches any other table.

    Safety: on PostgreSQL this refuses to run unless the database name contains "c3"
    (or C3_ALLOW_RESET=1 is set), so it can never wipe the team's shared database by accident.
    """
    if is_postgres(engine):
        import os
        name = (engine.url.database or "").lower()
        if "c3" not in name and os.environ.get("C3_ALLOW_RESET") != "1":
            raise RuntimeError(f"Refusing to reset database {name!r}: its name does not contain 'c3'. "
                               "Use the C3 database from docker-compose.c3.yml.")
        with engine.begin() as conn:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS c3"))
    metadata.drop_all(engine)
    metadata.create_all(engine)
