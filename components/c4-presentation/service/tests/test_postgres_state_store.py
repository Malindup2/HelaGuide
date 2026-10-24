"""Run existing C4 learning/recovery checks against actual PostgreSQL.

Requires:
    C4_TEST_POSTGRES_DSN targeting c4_pp1_test

The fixture clears C4 snapshot rows in that dedicated test database.
Never point this variable at the demonstration or team database.
"""

import os

import pytest
from fastapi.testclient import TestClient

from app.legacy.postgres_state_store import PostgreSQLStateStore
from app.legacy.state_store import StateCompatibilityError, StateStoreError
from app.dev_main import create_app
from app.models.policy import PolicyConfig

from tests import test_feedback_persistence as common
from tests.test_explanations import FakeProvider


@pytest.fixture(autouse=True)
def postgres_environment(monkeypatch):
    dsn = os.getenv("C4_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("C4_TEST_POSTGRES_DSN is not configured")

    try:
        import psycopg
        from psycopg.conninfo import conninfo_to_dict
    except ImportError:
        pytest.fail("install C4's postgres extra to run PostgreSQL tests")

    details = conninfo_to_dict(dsn)
    if details.get("dbname") != "c4_pp1_test":
        pytest.fail("PostgreSQL tests require the dedicated c4_pp1_test database")

    def clear_test_rows():
        with psycopg.connect(dsn, autocommit=True) as connection:
            exists = connection.execute(
                "SELECT to_regclass('c4.research_runtime_state')"
            ).fetchone()[0]
            if exists is not None:
                connection.execute(
                    """
                    DELETE FROM c4.research_runtime_state
                    WHERE state_key IN (%s, %s)
                    """,
                    ("simulation", "participant"),
                )

    clear_test_rows()

    def postgres_application(path=None, *, mode="simulation"):
        # Existing behavior tests pass a SQLite path to identify a durable
        # store. Here every application targets the dedicated PostgreSQL DB.
        return create_app(
            provider=FakeProvider(failure="offline_test"),
            postgres_dsn=dsn,
            policy_config=PolicyConfig(feedback_mode=mode),
        )

    monkeypatch.setattr(common, "application", postgres_application)

    try:
        yield dsn
    finally:
        clear_test_rows()


@pytest.mark.parametrize(
    ("rating", "reward"),
    [("about_right", 1), ("need_more", 0), ("too_much", 0)],
)
def test_postgres_feedback_updates(rating, reward):
    common.test_valid_feedback_updates_shared_posterior(rating, reward)


def test_postgres_requires_acknowledgment():
    common.test_feedback_requires_acknowledgment_and_valid_request()


def test_postgres_duplicate_and_conflicting_feedback():
    common.test_repeated_feedback_is_idempotent_and_conflicts_are_rejected()


def test_postgres_original_context_is_preserved():
    common.test_late_feedback_preserves_original_context_and_vector()


def test_postgres_shared_learning():
    common.test_learning_is_shared_across_guest_sessions()


def test_postgres_restart_recovery(tmp_path):
    common.test_restart_recovers_state_feedback_sampler_and_pending_offer(tmp_path)


def test_postgres_failed_commit_recovery(tmp_path, monkeypatch):
    common.test_failed_commit_does_not_report_success_and_restart_recovers(
        tmp_path, monkeypatch
    )


def test_postgres_stale_process_cannot_overwrite(tmp_path):
    common.test_second_process_cannot_overwrite_newer_state(tmp_path)


def test_postgres_incompatible_configuration_is_rejected(postgres_environment):
    dsn = postgres_environment
    store = PostgreSQLStateStore(dsn, PolicyConfig())
    original = store.manifest
    store.close()

    with pytest.raises(StateCompatibilityError, match="incompatible"):
        PostgreSQLStateStore(dsn, PolicyConfig(seed=99))

    reopened = PostgreSQLStateStore(dsn, PolicyConfig())
    try:
        assert reopened.manifest == original
        assert reopened.load() == (0, None)
    finally:
        reopened.close()


def test_postgres_corrupt_snapshot_is_rejected(postgres_environment):
    import psycopg

    dsn = postgres_environment
    with TestClient(common.application()) as client:
        common.prepare(client)

    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(
            """
            UPDATE c4.research_runtime_state
            SET payload = %s
            WHERE state_key = %s
            """,
            ("{}", "simulation"),
        )

    with pytest.raises(StateStoreError, match="checksum"):
        with TestClient(common.application()):
            pass