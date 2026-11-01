"""
Completed service requests, saved to SQLite so they outlive the in-memory sessions (sessions.py) and can be listed
with GET /v1/requests/completed.

A request is saved on the first turn it is complete: ready (all slots filled and confirmed), or filed in
completed_requests when the citizen moved on to another service. completed_at keeps that first time; a later change
to the saved request (a correction after the confirmation) updates its slots and updated_at.

C1_COMPLETED_DB   path of the SQLite file (default components/c1-intent/var/completed_requests.sqlite3, relative
                  paths from the working directory); "off" turns saving off

Slot values are saved as the tracker filled them. PostgreSQL schema `c1` is the planned home for this in the
deployed stack.
"""
import json
import os
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from app.core.dst import KG_SERVICE_IDS

COMPONENT_DIR = Path(__file__).resolve().parents[3]      # components/c1-intent/
DEFAULT_DB = COMPONENT_DIR / "var" / "completed_requests.sqlite3"
ENDPOINTS = ("intent", "chat")      # intent: /v1/intent and /v1/intent/details (shared sessions); chat: /v1/chat

SCHEMA = """
CREATE TABLE IF NOT EXISTS completed_requests (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT NOT NULL,
    endpoint     TEXT NOT NULL,
    intent       TEXT NOT NULL,
    service_id   TEXT,
    slots        TEXT NOT NULL,     -- JSON object
    conditions   TEXT NOT NULL,     -- JSON object
    turn_id      INTEGER NOT NULL,  -- the turn the request was first complete
    completed_at TEXT NOT NULL,     -- UTC, ISO 8601
    updated_at   TEXT NOT NULL,
    UNIQUE (session_id, endpoint, intent)
);
CREATE INDEX IF NOT EXISTS completed_requests_at ON completed_requests (completed_at);
"""

UPSERT = """
INSERT INTO completed_requests (session_id, endpoint, intent, service_id, slots, conditions, turn_id, completed_at,
                                updated_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (session_id, endpoint, intent) DO UPDATE SET
    service_id = excluded.service_id, slots = excluded.slots, conditions = excluded.conditions,
    updated_at = excluded.updated_at
WHERE slots != excluded.slots OR conditions != excluded.conditions
"""


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json(d):
    return json.dumps(d, ensure_ascii=False, sort_keys=True)     # sorted, so an unchanged request compares equal


def finished(state):
    """The requests a turn's engine-style result shows as complete: (intent, service_id, slots, conditions)."""
    done = [(r["intent"], r["service_id"], r["slots"], r["conditions"]) for r in state["completed_requests"]]
    active = state["active_intent"]
    if state["ready"] and active:
        done.append((active, KG_SERVICE_IDS.get(active), state["slots"], state["conditions"]))
    return done


class CompletedStore:
    def __init__(self, path, clock=_now):
        self.path = Path(path)
        self.clock = clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            conn.executescript(SCHEMA)

    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        return conn

    def record(self, session_id, endpoint, state):
        """Save the requests this turn shows as complete. -> how many rows were added or changed."""
        done = finished(state)
        if not done:
            return 0
        now = self.clock()
        rows = [(session_id, endpoint, intent, service_id, _json(slots), _json(conditions), state["turn_id"], now, now)
                for intent, service_id, slots, conditions in done]
        with closing(self._connect()) as conn, conn:
            before = conn.total_changes
            conn.executemany(UPSERT, rows)
            return conn.total_changes - before

    def list(self, session_id=None, endpoint=None, intent=None, limit=50):
        """Saved requests, newest first."""
        where, args = [], []
        for col, value in (("session_id", session_id), ("endpoint", endpoint), ("intent", intent)):
            if value is not None:
                where.append(f"{col} = ?")
                args.append(value)
        sql = "SELECT * FROM completed_requests" + (f" WHERE {' AND '.join(where)}" if where else "") + \
              " ORDER BY completed_at DESC, id DESC LIMIT ?"
        with closing(self._connect()) as conn:
            rows = conn.execute(sql, [*args, limit]).fetchall()
        return [{**dict(r), "slots": json.loads(r["slots"]), "conditions": json.loads(r["conditions"])} for r in rows]


_stores = {}
_stores_lock = threading.Lock()


def get_store():
    """The store for C1_COMPLETED_DB (read on every call, so tests can monkeypatch it), or None when it is "off"."""
    raw = os.environ.get("C1_COMPLETED_DB", "").strip()
    if raw.lower() == "off":
        return None
    path = Path(raw) if raw else DEFAULT_DB
    with _stores_lock:
        if path not in _stores:
            _stores[path] = CompletedStore(path)
        return _stores[path]
