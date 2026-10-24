"""Atomic SQLite snapshots for a single-process C4 research application.

The database contains trusted local application state, not executable objects.
No pickle is used. JSON checksums detect accidental corruption, not malicious
tampering by someone who can rewrite the database.
"""

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pydantic
import scipy

from app.legacy.v1_policy import (
    FEATURE_DIMENSION,
    FEATURE_SCHEMA_FINGERPRINT,
    FEATURE_SCHEMA_VERSION,
)
from app.models.policy import PolicyConfig
from app.models.runtime_state import RuntimeState
from app.errors import StateStoreError


class StateCompatibilityError(StateStoreError):
    """Saved data requires an explicit compatible version or migration."""


def _canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _checksum(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compatibility_manifest(config: PolicyConfig) -> str:
    return _canonical(
        {
            "storage_version": "c4-sqlite-snapshot-1.0",
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "feature_schema_fingerprint": FEATURE_SCHEMA_FINGERPRINT,
            "feature_dimension": FEATURE_DIMENSION,
            "policy_config": config.model_dump(mode="json"),
            "runtime_schema_fingerprint": _checksum(
                _canonical(RuntimeState.model_json_schema())
            ),
            "python": list(sys.version_info[:2]),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "pydantic": pydantic.__version__,
        }
    )


class SQLiteStateStore:
    def __init__(self, path: str | Path, config: PolicyConfig):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest = compatibility_manifest(config)

        self.connection = sqlite3.connect(
            str(self.path),
            timeout=10.0,
            isolation_level=None,
            check_same_thread=False,
        )
        try:
            self.connection.execute("PRAGMA synchronous=FULL")
            self.connection.execute("BEGIN IMMEDIATE")
            tables = {
                row[0]
                for row in self.connection.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            }
            if tables and tables != {"c4_snapshot"}:
                raise StateCompatibilityError(
                    "database is not a recognized C4 snapshot database"
                )

            if not tables:
                self.connection.execute(
                    """
                    CREATE TABLE c4_snapshot (
                        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                        revision INTEGER NOT NULL,
                        manifest TEXT NOT NULL,
                        payload TEXT NOT NULL,
                        checksum TEXT NOT NULL
                    )
                    """
                )

            row = self.connection.execute(
                "SELECT manifest FROM c4_snapshot WHERE singleton=1"
            ).fetchone()
            if row is not None and row[0] != self.manifest:
                raise StateCompatibilityError(
                    "stored state is incompatible with this configuration, "
                    "schema or numerical environment; preserve the database "
                    "and choose a separate database or explicit migration"
                )
            self.connection.execute("COMMIT")
        except Exception:
            if self.connection.in_transaction:
                self.connection.execute("ROLLBACK")
            self.connection.close()
            raise

    def load(self) -> tuple[int, RuntimeState | None]:
        try:
            row = self.connection.execute(
                "SELECT revision, manifest, payload, checksum "
                "FROM c4_snapshot WHERE singleton=1"
            ).fetchone()
            if row is None:
                return 0, None
            revision, manifest, payload, checksum = row
            if manifest != self.manifest:
                raise StateCompatibilityError("stored compatibility manifest changed")
            if _checksum(payload) != checksum:
                raise StateStoreError("stored snapshot checksum mismatch")
            return revision, RuntimeState.model_validate_json(payload)
        except StateStoreError:
            raise
        except (sqlite3.Error, ValueError, TypeError):
            raise StateStoreError("cannot read a valid C4 state snapshot") from None

    def assert_revision(self, expected_revision: int) -> None:
        try:
            row = self.connection.execute(
                "SELECT revision FROM c4_snapshot WHERE singleton=1"
            ).fetchone()
            actual = 0 if row is None else row[0]
            if actual != expected_revision:
                raise StateStoreError(
                    "database changed in another process; restart this instance"
                )
        except sqlite3.Error:
            raise StateStoreError("cannot verify stored state revision") from None

    def save(self, state: RuntimeState, expected_revision: int) -> int:
        # Excludes computed output-only fields throughout nested models.
        payload = state.model_dump_json(round_trip=True)
        checksum = _checksum(payload)
        next_revision = expected_revision + 1

        try:
            self.connection.execute("BEGIN IMMEDIATE")
            self.assert_revision(expected_revision)
            self.connection.execute(
                """
                INSERT INTO c4_snapshot (
                    singleton, revision, manifest, payload, checksum
                ) VALUES (1, ?, ?, ?, ?)
                ON CONFLICT(singleton) DO UPDATE SET
                    revision=excluded.revision,
                    manifest=excluded.manifest,
                    payload=excluded.payload,
                    checksum=excluded.checksum
                """,
                (next_revision, self.manifest, payload, checksum),
            )
            self.connection.execute("COMMIT")
            return next_revision
        except Exception as exc:
            if self.connection.in_transaction:
                try:
                    self.connection.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
            if isinstance(exc, StateStoreError):
                raise
            raise StateStoreError(
                "state commit failed; restart before further operations"
            ) from None

    def close(self):
        self.connection.close()