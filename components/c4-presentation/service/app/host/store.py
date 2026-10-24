"""One durable JSON record in one SQLite table: the persistence of the integrated workspace.

Revision counter, checksum, optimistic concurrency and full rollback. Owners supply the
initial record, its compatibility check, a restore step and a pre-commit step. The table and
record format are unchanged from the original V2 runtime, so existing databases still open.
"""
import copy
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from app.procedures.canonical import digest

C4_ROOT = Path(__file__).resolve().parents[3]


def now():
    return datetime.now(timezone.utc).isoformat()


class Conflict(ValueError):
    pass


class RecordStore:
    TABLE = "c4_v2_state"

    def _open(self, path):
        if str(path) != ":memory:":
            path = Path(path).resolve()
            if not path.is_relative_to(C4_ROOT) or "v2" not in path.parts:
                raise ValueError("V2 storage must be inside C4 in a v2 directory")
            path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        existing = {r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if existing and existing != {self.TABLE}:
            self.db.close()
            raise ValueError("refusing a database with non-V2 tables")
        self.db.execute(f"CREATE TABLE IF NOT EXISTS {self.TABLE} (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, payload TEXT NOT NULL, checksum TEXT NOT NULL)")
        self.db.commit()
        self.lock = threading.RLock()

    def _load(self, initial, compatible, error):
        row = self.db.execute(f"SELECT revision,payload,checksum FROM {self.TABLE} WHERE id=1").fetchone()
        if row:
            self.revision, payload, checksum = row
            self.state = json.loads(payload)
            if digest(self.state) != checksum or not compatible(self.state):
                self.db.close()
                raise ValueError(error)
        else:
            self.revision = 0
            self.state = initial()
            self.db.execute(f"INSERT INTO {self.TABLE} VALUES (1,0,?,?)", (json.dumps(self.state), digest(self.state)))
            self.db.commit()

    def _restore(self):
        pass

    def _before_commit(self):
        pass

    def _write(self, function):
        with self.lock:
            previous = copy.deepcopy(self.state)
            try:
                self.db.execute("BEGIN IMMEDIATE")
                current = self.db.execute(f"SELECT revision FROM {self.TABLE} WHERE id=1").fetchone()[0]
                if current != self.revision:
                    raise Conflict("concurrent writer changed state; reopen this runtime")
                result = function()
                self._before_commit()
                self.db.execute(f"UPDATE {self.TABLE} SET revision=?,payload=?,checksum=? WHERE id=1", (self.revision + 1, json.dumps(self.state, allow_nan=False), digest(self.state)))
                self.db.commit()
                self.revision += 1
                return copy.deepcopy(result)
            except Exception:
                self.db.rollback()
                self.state = previous
                self._restore()
                raise

    def close(self):
        self.db.close()
