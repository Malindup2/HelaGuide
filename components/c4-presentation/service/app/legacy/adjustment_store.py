"""Atomic view-sidecar transactions. Does not alter the policy-state schema.

Back up this SQLite file together with the policy database and wording views.
The independent prototype supports one backend process, like its policy store.
"""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from app.preparation.explanations import _digest
from app.legacy.state_store import StateStoreError
from app.models.adjustments import ViewLedger


class AdjustmentStore:
    def __init__(self, path=None):
        if path is not None:
            Path(path).resolve().parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(path) if path else ":memory:", isolation_level=None, check_same_thread=False)
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.execute("CREATE TABLE IF NOT EXISTS c4_view_ledgers (identity TEXT PRIMARY KEY, payload TEXT NOT NULL, checksum TEXT NOT NULL)")

    @contextmanager
    def transaction(self):
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            yield
            self.connection.execute("COMMIT")
        except sqlite3.Error:
            if self.connection.in_transaction:
                self.connection.execute("ROLLBACK")
            raise StateStoreError("adjustment storage unavailable; refresh before retrying") from None
        except Exception:
            if self.connection.in_transaction:
                self.connection.execute("ROLLBACK")
            raise

    @staticmethod
    def key(spec, run):
        return _digest(["c4-adjustments-1.0", run, spec.session_id, spec.exposure_id, spec.presentation_id])

    def read(self, spec, run):
        try:
            row = self.connection.execute("SELECT payload,checksum FROM c4_view_ledgers WHERE identity=?", (self.key(spec, run),)).fetchone()
            if row is None:
                return ViewLedger(session_id=spec.session_id, exposure_id=spec.exposure_id, presentation_id=spec.presentation_id, policy_run_id=run)
            ledger = ViewLedger.model_validate_json(row[0], strict=True)
            if row[1] != _digest(ledger.model_dump(mode="json", round_trip=True)) or (ledger.session_id, ledger.exposure_id, ledger.presentation_id, ledger.policy_run_id) != (spec.session_id, spec.exposure_id, spec.presentation_id, run):
                raise ValueError("attribution or checksum")
            return ledger
        except (sqlite3.Error, ValueError):
            raise StateStoreError("cannot restore valid adjustment history") from None

    def save(self, spec, ledger):
        payload = ledger.model_dump(mode="json", round_trip=True)
        self.connection.execute("INSERT INTO c4_view_ledgers VALUES (?,?,?) ON CONFLICT(identity) DO UPDATE SET payload=excluded.payload,checksum=excluded.checksum",
                                (self.key(spec, ledger.policy_run_id), json.dumps(payload, ensure_ascii=False, allow_nan=False), _digest(payload)))

    def close(self):
        self.connection.close()
