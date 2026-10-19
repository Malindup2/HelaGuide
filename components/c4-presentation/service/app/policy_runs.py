"""Explicit offline prior validation and backed-up fresh simulation runs.

Stop the backend first. No provider, network generation, or automatic startup reset.
"""

import argparse
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path

from app.core.navigation_migration import canonical, checksum, write_backup
from app.core.policy import SharedLinTSPolicy
from app.core.prior import load_prior, prior_digest
from app.core.state_store import StateStoreError, compatibility_manifest
from app.core.user_context import InMemoryContextService
from app.models.policy import PolicyConfig
from app.models.runtime_state import RuntimeState, SessionState
from app.models.user_context import PreferenceChange


LEGACY_SCHEMA = "b18424adc48eba44fbc2aba8313c54a0b2398feb33f60152c75e443a25dcfce5"


def manifest_for(config, storage):
    result = json.loads(compatibility_manifest(config))
    if storage == "postgresql":
        result["storage_version"] = "c4-postgres-snapshot-1.0"
    return canonical(result)


def read_state(row, storage):
    if row is None or type(row[0]) is not int or row[0] < 1 or not isinstance(row[2], str):
        raise StateStoreError("no saved simulation snapshot")
    revision, manifest, payload, digest = row
    if checksum(payload) != digest:
        raise StateStoreError("snapshot checksum mismatch")
    state = RuntimeState.model_validate_json(payload)
    if state.policy.config.feedback_mode != "simulation":
        raise StateStoreError("fresh-run operation is simulation-only")
    actual = json.loads(manifest)
    expected = json.loads(manifest_for(state.policy.config, storage))
    if actual != expected:
        # Only the exact immediately preceding schema/config representation is
        # supported. Never reinterpret arbitrary historical database versions.
        legacy = dict(expected)
        legacy["runtime_schema_fingerprint"] = LEGACY_SCHEMA
        legacy["policy_config"] = dict(legacy["policy_config"])
        legacy["policy_config"].pop("prior", None)
        if state.policy.config.prior is not None or actual != legacy:
            raise StateStoreError("unsupported saved schema/config; keep the old database")
    # Validate attribution, posterior replay, profiles, corrections and source
    # binding before archiving anything. No persistent runtime is opened here.
    validate_state(state)
    return state


def validate_state(state):
    from app.core.llm_provider import OpenAIExplanationProvider
    # Importing dev_main also constructs the lazy ASGI app, but does not enter
    # its lifespan or connect to a database or provider.
    from app.dev_main import DevRuntime
    provider = OpenAIExplanationProvider(enabled=False)
    runtime = DevRuntime(provider, (), {}, policy_config=state.policy.config)
    try:
        runtime._restore(state)
        if runtime.export_state() != state:
            raise StateStoreError("runtime validation changed snapshot")
    finally:
        runtime.close()
        provider.close()


def fresh_state(old, config):
    if config.feedback_mode != "simulation" or old.policy.config.feedback_mode != "simulation":
        raise StateStoreError("fresh-run operation is simulation-only")
    sessions = []
    for record in old.sessions:
        # Retain genuine context edits and current profile settings. Remove
        # exposure/navigation history so random rehearsal behavior is not used.
        events = tuple(event.model_copy(update={"sequence": sequence})
                       for sequence, event in enumerate(
                           (event for event in record.events if isinstance(event, PreferenceChange)), 1))
        session = record.session.model_copy(update={
            "revision": len(events),
            "updated_at": events[-1].occurred_at if events else record.session.created_at,
        })
        sessions.append(SessionState(session=session, events=events, offers=()))
    contexts = InMemoryContextService.from_state(tuple(sessions))
    state = RuntimeState(sessions=tuple(sessions),
                         policy=SharedLinTSPolicy(contexts, config=config).export_state(),
                         profiles=old.profiles, presentations=(), feedback=(), corrections=())
    validate_state(state)
    return state


def prepare(row, storage, config, expected_run):
    old = read_state(row, storage)
    if old.policy.policy_run_id != expected_run:
        raise StateStoreError("policy run changed; inspect again (no reset performed)")
    new = fresh_state(old, config)
    return new, manifest_for(config, storage), new.model_dump_json(round_trip=True)


def report(state):
    return {"policy_run_id": state.policy.policy_run_id,
            "prior_version": state.policy.config.prior.version if state.policy.config.prior else "neutral",
            "prior_digest": prior_digest(state.policy.config.prior),
            "prior_status": state.policy.config.prior.status if state.policy.config.prior else "neutral",
            "posterior_revision": state.policy.posterior_revision,
            "accepted_feedback_count": len(state.feedback), "profile_count": len(state.profiles)}


def operate_sqlite(path, backup, config=None, expected_run=None):
    path = Path(path).resolve()
    if not path.is_file():
        raise StateStoreError("SQLite snapshot does not exist")
    with closing(sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, isolation_level=None)) as connection:
        try:
            connection.execute("BEGIN IMMEDIATE" if config else "BEGIN")
            row = connection.execute("SELECT revision, manifest, payload, checksum FROM c4_snapshot WHERE singleton=1").fetchone()
            if config:
                state, manifest, payload = prepare(row, "sqlite", config, expected_run)
                write_backup(backup, "sqlite", "simulation", row)
                connection.execute("UPDATE c4_snapshot SET revision=?, manifest=?, payload=?, checksum=? WHERE singleton=1",
                                   (row[0] + 1, manifest, payload, checksum(payload)))
            else:
                state = read_state(row, "sqlite")
            connection.execute("COMMIT")
            return report(state)
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise


def operate_postgres(dsn, backup, config=None, expected_run=None):
    import psycopg
    with psycopg.connect(dsn, autocommit=True, connect_timeout=5,
                         options="-c statement_timeout=30000 -c lock_timeout=5000") as connection:
        with connection.transaction():
            row = connection.execute(
                "SELECT revision, manifest, payload, checksum FROM c4.research_runtime_state "
                "WHERE state_key=%s" + (" FOR UPDATE" if config else ""), ("simulation",)).fetchone()
            if config:
                state, manifest, payload = prepare(row, "postgresql", config, expected_run)
                write_backup(backup, "postgresql", "simulation", row)
                connection.execute(
                    "UPDATE c4.research_runtime_state SET revision=%s, manifest=%s, payload=%s, checksum=%s WHERE state_key=%s",
                    (row[0] + 1, manifest, payload, checksum(payload), "simulation"))
            else:
                state = read_state(row, "postgresql")
            return report(state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "inspect", "start"))
    backend = parser.add_mutually_exclusive_group()
    backend.add_argument("--sqlite", type=Path)
    backend.add_argument("--postgres", action="store_true")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--prior", type=Path)
    source.add_argument("--neutral", action="store_true")
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--expected-run")
    parser.add_argument("--confirm-fresh-simulation", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "validate":
            if not args.prior:
                parser.error("validate requires --prior")
            prior = load_prior(args.prior)
            print(json.dumps({"version": prior.version, "status": prior.status,
                              "digest": prior_digest(prior), "judgments": len(prior.judgments),
                              "maximum_absolute_score_shift": sum(abs(j.score_delta) for j in prior.judgments)}, indent=2))
            return
        if not (args.sqlite or args.postgres):
            parser.error("choose --sqlite or --postgres")
        config = None
        if args.command == "start":
            if not (args.confirm_fresh_simulation and args.backup and args.expected_run and (args.prior or args.neutral)):
                parser.error("start requires --prior or --neutral, --backup, --expected-run and --confirm-fresh-simulation")
            config = PolicyConfig(cold_start_updates=0, prior=load_prior(args.prior) if args.prior else None)
        if args.postgres:
            dsn = os.getenv("C4_DATABASE_URL")
            if not dsn:
                raise StateStoreError("C4_DATABASE_URL is not configured")
            result = operate_postgres(dsn, args.backup, config, args.expected_run)
        else:
            result = operate_sqlite(args.sqlite, args.backup, config, args.expected_run)
        print(json.dumps(result, indent=2))
    except Exception as exc:
        # Never print driver errors/connection strings or secret-bearing bodies.
        if isinstance(exc, StateStoreError):
            parser.exit(2, f"Operation stopped: {exc}\n")
        parser.exit(2, f"Operation stopped ({type(exc).__name__}); no database update committed. Keep any backup.\n")


if __name__ == "__main__":
    main()
