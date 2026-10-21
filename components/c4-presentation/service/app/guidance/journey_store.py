"""Isolated revised API records, never a policy/snapshot writer."""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from app.guidance.sources import digest

STORE_SCHEMA="c4-guidance-api-store-1.0"

class JourneyStore:
    def __init__(self,directory):
        self.directory=Path(directory).resolve()
        root=Path(__file__).resolve().parents[3]
        if not self.directory.is_relative_to(root) or "frontend-api" not in self.directory.parts:
            raise ValueError("guidance records need a dedicated C4/frontend-api directory")
        self.directory.mkdir(parents=True,exist_ok=True)
        self.path=self.directory/"journeys.sqlite3"
        with self.transaction() as db:
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables and ("api_manifest" not in tables or db.execute("SELECT schema FROM api_manifest").fetchone()!=(STORE_SCHEMA,)):
                raise ValueError("refusing unrelated or incompatible database")
            db.execute("CREATE TABLE IF NOT EXISTS api_manifest(schema TEXT NOT NULL)")
            if not tables:db.execute("INSERT INTO api_manifest VALUES (?)",(STORE_SCHEMA,))
            db.execute("CREATE TABLE IF NOT EXISTS journeys(id TEXT PRIMARY KEY,session_id TEXT,request_id TEXT,signature TEXT,token_hash TEXT,body TEXT,checksum TEXT,UNIQUE(session_id,request_id))")
            db.execute("CREATE TABLE IF NOT EXISTS operations(journey_id TEXT,event_id TEXT,signature TEXT,record TEXT,receipt TEXT,PRIMARY KEY(journey_id,event_id))")
            db.execute("CREATE TABLE IF NOT EXISTS settings(session_id TEXT PRIMARY KEY,body TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS settings_requests(session_id TEXT,request_id TEXT,signature TEXT,PRIMARY KEY(session_id,request_id))")

    @contextmanager
    def transaction(self):
        db=sqlite3.connect(self.path,timeout=10)
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except Exception:
            db.rollback();raise
        finally:db.close()

    def read(self,row):
        if row is None:return None
        result=json.loads(row[0])
        if digest(result)!=row[1]:raise ValueError("guidance record checksum mismatch")
        return result

    def get(self,db,jid):
        return self.read(db.execute("SELECT body,checksum FROM journeys WHERE id=?",(jid,)).fetchone())

    def save(self,db,journey):
        db.execute("UPDATE journeys SET body=?,checksum=? WHERE id=?",(json.dumps(journey),digest(journey),journey['id']))

    def settings(self,db,sid):
        row=db.execute("SELECT body FROM settings WHERE session_id=?",(sid,)).fetchone()
        return json.loads(row[0]) if row else {"schema_version":"c4-settings-3.0","revision":0,"preferences":{},"locks":{},"accessibility":{},"legacy_lock_ack":None}
