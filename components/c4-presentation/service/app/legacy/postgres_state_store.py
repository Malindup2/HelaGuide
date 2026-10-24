"""PostgreSQL snapshot storage for the independent C4 research prototype.

Only c4.research_runtime_state is managed here.
Existing C1/C3 tables and the team's skeleton C4 tables are not modified.

The caller serializes runtime operations. This adapter additionally locks
its connection and uses revision checks to reject stale processes.

JSON checksums detect accidental corruption, not malicious database editing.
"""

import hashlib
import json
from threading import RLock

from app.legacy.state_store import (
    StateCompatibilityError,
    StateStoreError,
    compatibility_manifest,
)
from app.models.policy import PolicyConfig
from app.models.runtime_state import RuntimeState


def _checksum(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class PostgreSQLStateStore:
    def __init__(self, dsn: str, config: PolicyConfig):
        if not isinstance(dsn, str) or not dsn.strip():
            raise StateStoreError("C4 PostgreSQL connection configuration is missing")

        try:
            import psycopg
        except ImportError:
            raise StateStoreError(
                "Install C4's postgres extra before selecting PostgreSQL storage"
            ) from None

        self._driver = psycopg
        self._lock = RLock()
        self.connection = None
        self.state_key = config.feedback_mode

        manifest = json.loads(compatibility_manifest(config))
        manifest["storage_version"] = "c4-postgres-snapshot-1.0"
        self.manifest = json.dumps(
            manifest,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )

        try:
            self.connection = psycopg.connect(
                dsn,
                autocommit=True,
                connect_timeout=5,
                application_name="helaguide-c4",
                options="-c statement_timeout=15000 -c lock_timeout=5000",
            )

            with self.connection.transaction():
                with self.connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT 1 FROM pg_namespace WHERE nspname = %s",
                        ("c4",),
                    )
                    if cursor.fetchone() is None:
                        raise StateStoreError(
                            "The configured database needs its C4 schema initialized"
                        )

                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS c4.research_runtime_state (
                            state_key TEXT PRIMARY KEY
                                CHECK (state_key IN ('simulation', 'participant')),
                            revision BIGINT NOT NULL CHECK (revision >= 0),
                            manifest TEXT NOT NULL,
                            payload TEXT,
                            checksum TEXT,
                            CHECK (
                                (
                                    revision = 0
                                    AND payload IS NULL
                                    AND checksum IS NULL
                                )
                                OR
                                (
                                    revision > 0
                                    AND payload IS NOT NULL
                                    AND checksum IS NOT NULL
                                )
                            )
                        )
                        """
                    )
                    cursor.execute(
                        """
                        INSERT INTO c4.research_runtime_state (
                            state_key, revision, manifest, payload, checksum
                        )
                        VALUES (%s, 0, %s, NULL, NULL)
                        ON CONFLICT (state_key) DO NOTHING
                        """,
                        (self.state_key, self.manifest),
                    )
                    cursor.execute(
                        """
                        SELECT manifest
                        FROM c4.research_runtime_state
                        WHERE state_key = %s
                        """,
                        (self.state_key,),
                    )
                    row = cursor.fetchone()
                    if row is None or row[0] != self.manifest:
                        raise StateCompatibilityError(
                            "PostgreSQL state is incompatible with this policy, "
                            "feature schema or numerical environment"
                        )

        except StateStoreError:
            self.close()
            raise
        except psycopg.Error:
            self.close()
            raise StateStoreError(
                "C4 PostgreSQL initialization failed; verify the connection, "
                "schema and permissions"
            ) from None
        except Exception:
            self.close()
            raise

    def _row(self, *, for_update=False):
        suffix = " FOR UPDATE" if for_update else ""
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT revision, manifest, payload, checksum
                FROM c4.research_runtime_state
                WHERE state_key = %s
                """ + suffix,
                (self.state_key,),
            )
            row = cursor.fetchone()

        if row is None:
            raise StateStoreError("C4 PostgreSQL state row is missing")
        if row[1] != self.manifest:
            raise StateCompatibilityError(
                "C4 PostgreSQL compatibility manifest changed"
            )
        return row

    def load(self) -> tuple[int, RuntimeState | None]:
        with self._lock:
            try:
                revision, manifest, payload, checksum = self._row()
                if revision == 0:
                    if payload is not None or checksum is not None:
                        raise StateStoreError("invalid empty PostgreSQL snapshot")
                    return 0, None

                if (
                    payload is None
                    or checksum is None
                    or _checksum(payload) != checksum
                ):
                    raise StateStoreError("PostgreSQL snapshot checksum mismatch")

                return revision, RuntimeState.model_validate_json(payload)

            except StateStoreError:
                raise
            except self._driver.Error:
                raise StateStoreError("cannot read C4 PostgreSQL state") from None
            except (ValueError, TypeError):
                raise StateStoreError(
                    "PostgreSQL snapshot does not contain valid C4 state"
                ) from None

    def assert_revision(self, expected_revision: int) -> None:
        with self._lock:
            try:
                revision, manifest, payload, checksum = self._row()
                if revision != expected_revision:
                    raise StateStoreError(
                        "PostgreSQL state changed in another process; "
                        "restart this instance"
                    )
            except StateStoreError:
                raise
            except self._driver.Error:
                raise StateStoreError(
                    "cannot verify C4 PostgreSQL state revision"
                ) from None

    def save(self, state: RuntimeState, expected_revision: int) -> int:
        if type(expected_revision) is not int or expected_revision < 0:
            raise StateStoreError("invalid expected PostgreSQL revision")

        payload = state.model_dump_json(round_trip=True)
        checksum = _checksum(payload)
        next_revision = expected_revision + 1

        with self._lock:
            try:
                with self.connection.transaction():
                    revision, manifest, old_payload, old_checksum = self._row(
                        for_update=True
                    )
                    if revision != expected_revision:
                        raise StateStoreError(
                            "PostgreSQL state changed in another process; "
                            "restart this instance"
                        )

                    with self.connection.cursor() as cursor:
                        cursor.execute(
                            """
                            UPDATE c4.research_runtime_state
                            SET revision = %s,
                                manifest = %s,
                                payload = %s,
                                checksum = %s
                            WHERE state_key = %s
                            RETURNING revision
                            """,
                            (
                                next_revision,
                                self.manifest,
                                payload,
                                checksum,
                                self.state_key,
                            ),
                        )
                        row = cursor.fetchone()
                        if row is None or row[0] != next_revision:
                            raise StateStoreError(
                                "C4 PostgreSQL state update was not confirmed"
                            )

                # The transaction has committed before returning success.
                return next_revision

            except StateStoreError:
                raise
            except self._driver.Error:
                raise StateStoreError(
                    "C4 PostgreSQL commit failed; restart before further operations"
                ) from None

    def close(self):
        with self._lock:
            if self.connection is not None:
                self.connection.close()