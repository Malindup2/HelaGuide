"""Explicit, backed-up migration from runtime 1.0 to runtime 1.1.

Run only with the C4 development server stopped.
No LLM requests or policy learning are performed.
"""

import argparse
import hashlib
import json
import os
import sqlite3
from pathlib import Path

from app.core.state_store import (
    StateCompatibilityError,
    StateStoreError,
    compatibility_manifest,
)
from app.models.policy import PolicyConfig
from app.models.runtime_state import RuntimeState
from app.models.runtime_state_v1 import RuntimeState as LegacyRuntimeState


def canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def checksum(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def manifest_for(config, storage, *, legacy=False):
    if storage not in {"sqlite", "postgresql"}:
        raise ValueError("unsupported storage backend")

    manifest = json.loads(compatibility_manifest(config))
    if storage == "postgresql":
        manifest["storage_version"] = "c4-postgres-snapshot-1.0"

    if legacy:
        manifest["runtime_schema_fingerprint"] = checksum(
            canonical(LegacyRuntimeState.model_json_schema())
        )
    return canonical(manifest)


def validate_runtime(state):
    # Import lazily so normal application startup never invokes migration.
    from app.core.llm_provider import OpenAIExplanationProvider
    from app.dev_main import DevRuntime

    provider = OpenAIExplanationProvider(enabled=False)
    runtime = DevRuntime(
        provider,
        (),
        {},
        policy_config=state.policy.config,
    )
    try:
        runtime._restore(state)
        if runtime.export_state().model_dump(
            mode="json", round_trip=True
        ) != state.model_dump(mode="json", round_trip=True):
            raise StateStoreError(
                "restoration changed the proposed migrated state"
            )
    finally:
        runtime.close()
        provider.close()


def prepare_migration(row, storage, mode):
    revision, manifest_text, payload, stored_checksum = row
    if (
        type(revision) is not int
        or revision < 1
        or not isinstance(payload, str)
        or checksum(payload) != stored_checksum
    ):
        raise StateStoreError("missing or invalid snapshot/checksum")

    manifest = json.loads(manifest_text)
    config = PolicyConfig.model_validate_json(
        json.dumps(manifest["policy_config"])
    )
    if config.feedback_mode != mode:
        raise StateCompatibilityError("feedback mode does not match")

    current_manifest = manifest_for(config, storage)
    legacy_manifest = manifest_for(config, storage, legacy=True)

    if manifest == json.loads(current_manifest):
        state = RuntimeState.model_validate_json(payload)
        validate_runtime(state)
        return False, current_manifest, payload, state

    if manifest != json.loads(legacy_manifest):
        raise StateCompatibilityError(
            "snapshot is not the supported runtime 1.0 schema "
            "with the current policy and numerical environment"
        )

    LegacyRuntimeState.model_validate_json(payload)
    document = json.loads(payload)

    if document["format_version"] != "c4-runtime-state-1.0":
        raise StateCompatibilityError("unexpected source runtime version")

    document["format_version"] = "c4-runtime-state-1.1"
    migrated_payload = canonical(document)
    state = RuntimeState.model_validate_json(migrated_payload)

    if state.policy.config != config:
        raise StateCompatibilityError("payload and manifest policy differ")

    validate_runtime(state)
    return True, current_manifest, migrated_payload, state


def write_backup(path, storage, mode, row):
    path = Path(path)
    if not path.parent.is_dir():
        raise StateStoreError(
            "create the backup parent directory before migrating"
        )

    revision, manifest, payload, stored_checksum = row
    document = {
        "backup_format": "c4-runtime-migration-backup-1.0",
        "storage": storage,
        "feedback_mode": mode,
        "revision": revision,
        "manifest": manifest,
        "payload": payload,
        "checksum": stored_checksum,
    }

    # Exclusive creation prevents overwriting an earlier backup.
    with path.open("x", encoding="utf-8") as handle:
        handle.write(canonical(document))
        handle.flush()
        os.fsync(handle.fileno())


def report(changed, state):
    return {
        "migrated": changed,
        "runtime_format": state.format_version,
        "policy_run_id": state.policy.policy_run_id,
        "posterior_revision": state.policy.posterior_revision,
        "posterior_fingerprint": state.policy.posterior_fingerprint,
        "feature_dimension": state.policy.feature_dimension,
        "feature_schema_fingerprint": state.policy.feature_schema_fingerprint,
    }


def migrate_sqlite(path, backup_path, mode="simulation"):
    path = Path(path).resolve()
    if not path.is_file():
        raise StateStoreError("SQLite database does not exist")

    connection = sqlite3.connect(
        path.as_uri() + "?mode=rw",
        uri=True,
        isolation_level=None,
    )
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT revision, manifest, payload, checksum "
            "FROM c4_snapshot WHERE singleton=1"
        ).fetchone()
        if row is None:
            raise StateStoreError("SQLite snapshot does not exist")

        changed, manifest, payload, state = prepare_migration(
            row, "sqlite", mode
        )
        if changed:
            write_backup(backup_path, "sqlite", mode, row)
            cursor = connection.execute(
                "UPDATE c4_snapshot "
                "SET revision=?, manifest=?, payload=?, checksum=? "
                "WHERE singleton=1 AND revision=?",
                (
                    row[0] + 1,
                    manifest,
                    payload,
                    checksum(payload),
                    row[0],
                ),
            )
            if cursor.rowcount != 1:
                raise StateStoreError("SQLite migration update failed")

        connection.execute("COMMIT")
        return report(changed, state)
    except Exception:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()


def migrate_postgres(dsn, backup_path, mode="simulation"):
    import psycopg

    with psycopg.connect(
        dsn,
        autocommit=True,
        connect_timeout=5,
        options="-c statement_timeout=30000 -c lock_timeout=5000",
    ) as connection:
        with connection.transaction():
            row = connection.execute(
                "SELECT revision, manifest, payload, checksum "
                "FROM c4.research_runtime_state "
                "WHERE state_key=%s FOR UPDATE",
                (mode,),
            ).fetchone()
            if row is None:
                raise StateStoreError("PostgreSQL snapshot does not exist")

            changed, manifest, payload, state = prepare_migration(
                row, "postgresql", mode
            )
            if changed:
                write_backup(backup_path, "postgresql", mode, row)
                cursor = connection.execute(
                    "UPDATE c4.research_runtime_state "
                    "SET revision=%s, manifest=%s, payload=%s, checksum=%s "
                    "WHERE state_key=%s AND revision=%s",
                    (
                        row[0] + 1,
                        manifest,
                        payload,
                        checksum(payload),
                        mode,
                        row[0],
                    ),
                )
                if cursor.rowcount != 1:
                    raise StateStoreError("PostgreSQL migration update failed")

    return report(changed, state)


def main():
    parser = argparse.ArgumentParser(
        description="Back up and migrate one C4 runtime snapshot to 1.1."
    )
    backend = parser.add_mutually_exclusive_group(required=True)
    backend.add_argument("--sqlite", type=Path)
    backend.add_argument("--postgres", action="store_true")
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument(
        "--mode",
        choices=("simulation", "participant"),
        default="simulation",
    )
    args = parser.parse_args()

    try:
        if args.postgres:
            dsn = os.getenv("C4_DATABASE_URL")
            if not dsn:
                raise StateStoreError("C4_DATABASE_URL is not configured")
            result = migrate_postgres(dsn, args.backup, args.mode)
        else:
            result = migrate_sqlite(args.sqlite, args.backup, args.mode)
    except (StateStoreError, FileExistsError) as exc:
        parser.exit(2, f"Migration stopped: {exc}\n")
    except Exception as exc:
        parser.exit(
            2,
            "Migration failed without a committed update. "
            f"Error type: {type(exc).__name__}. "
            "Keep the database and any backup for diagnosis.\n",
        )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()