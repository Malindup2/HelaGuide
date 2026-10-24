"""Durable offline preparation bridge; never publishes or writes policy state.

Live generation is opt-in. Failed/interrupted provider calls require explicit
retry, avoiding silent repeated paid requests after a crash.
"""
import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from app.procedures.scaffolds import graph_fingerprint
from app.procedures.canonical import Overlay, digest, validate_overlay
from app.models.procedure_graph import CanonicalProcedureGraph
from app.preparation.overlay_drafts import prepare


def job_entry(payload):
    graph = CanonicalProcedureGraph.model_validate_json(json.dumps(payload["graph"]))
    if payload["procedure_id"] != graph.plan_id or payload["graph_fingerprint"] != graph_fingerprint(graph):
        raise ValueError("preparation job source mismatch")
    overlay = Overlay.model_validate(payload["base_overlay"]) if payload.get("base_overlay") else None
    if overlay:
        validate_overlay(graph, overlay)
    return graph, overlay


@contextmanager
def job_lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as file:
        file.seek(0, 2)
        if file.tell() == 0:
            file.write(b"0"); file.flush()
        file.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            file.seek(0)
            if os.name == "nt":
                msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(file.fileno(), fcntl.LOCK_UN)


class PreparationProcessor:
    def __init__(self, runtime, directory, *, enabled=False, provider_factory=None, interval=2, handlers=None):
        self.handlers = handlers or {}
        self.runtime = runtime
        self.directory = Path(directory).resolve()
        root = Path(__file__).resolve().parents[3]
        if not self.directory.is_relative_to(root) or "v2" not in self.directory.parts:
            raise ValueError("preparation storage must stay inside C4/v2")
        self.directory.mkdir(parents=True, exist_ok=True)
        self.database = self.directory / "processing.sqlite3"
        self.enabled = enabled
        self.provider_factory = provider_factory
        self.interval = interval
        self.stop_event = threading.Event()
        self.wake_event = threading.Event()
        self.thread = None
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS preparation_jobs (id TEXT PRIMARY KEY, payload TEXT NOT NULL, status TEXT NOT NULL, draft TEXT, error_code TEXT, updated_at TEXT NOT NULL)")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def update(self, key, status, *, draft=None, error=None):
        with self.connect() as db:
            db.execute("UPDATE preparation_jobs SET status=?,draft=?,error_code=?,updated_at=? WHERE id=?",
                       (status, draft, error, datetime.now(timezone.utc).isoformat(), key))

    def scan(self):
        # Legacy queued JSON files remain intact; database holds processing state.
        for file in sorted(self.directory.glob("*.json")):
            try:
                payload = json.loads(file.read_text(encoding="utf-8-sig"))
                if payload.get("status") != "pending_review_preparation":
                    continue
                handler = self.handlers.get(payload.get("content_schema"))
                if payload.get("content_schema") and handler is None:
                    continue  # Unknown schemas must never enter the legacy generator.
                if handler is not None:
                    handler.validate_job(payload)
                    key = handler.key(payload)
                else:
                    graph, overlay = job_entry(payload)
                    key = digest({"graph": graph.model_dump(mode="json"), "overlay": overlay.model_dump(mode="json") if overlay else None, "missing": payload["missing"]})
                with self.connect() as db:
                    db.execute("INSERT OR IGNORE INTO preparation_jobs VALUES (?,?, 'queued', NULL, NULL, ?)",
                               (key, json.dumps(payload), datetime.now(timezone.utc).isoformat()))
            except (ValueError, KeyError):
                # Invalid/partial files are never sent to a provider.
                continue

        # Reconcile publication after restart or a crash between the two stores.
        # The runtime's reviewed registry, not a worker result, is authoritative.
        with self.runtime.lock:
            approved = dict(self.runtime.state.get("approved_content", {}))
            prepared = {pid for pid, entry in self.runtime.procedures.items() if not entry["preparation"]["missing"]}
        with self.connect() as db:
            for key, text in db.execute("SELECT id,payload FROM preparation_jobs WHERE status!='processing'").fetchall():
                payload = json.loads(text)
                handler = self.handlers.get(payload.get("content_schema"))
                if handler is not None:
                    if handler.published(payload):
                        db.execute("UPDATE preparation_jobs SET status='published' WHERE id=?", (key,))
                    continue
                artifact = approved.get(payload["procedure_id"])
                if payload["procedure_id"] in prepared and artifact and artifact.get("source_fingerprint") == payload["graph_fingerprint"]:
                    db.execute("UPDATE preparation_jobs SET status='published' WHERE id=?", (key,))

    def jobs(self):
        with self.connect() as db:
            rows = db.execute("SELECT id,payload,status,error_code,updated_at FROM preparation_jobs ORDER BY id").fetchall()
        return [{"id": k, "procedure_id": json.loads(p)["procedure_id"], "graph_fingerprint": json.loads(p)["graph_fingerprint"],
                 "status": s, "error_code": e, "updated_at": t, "generation_enabled": self.enabled, "content_schema":json.loads(p).get("content_schema","legacy-v2"), "language":json.loads(p).get("language","en")} for k,p,s,e,t in rows]

    def draft(self, key):
        with self.connect() as db:
            row = db.execute("SELECT status,draft FROM preparation_jobs WHERE id=?", (key,)).fetchone()
        if not row or row[0] != "pending_review" or not row[1]:
            raise ValueError("job has no completed pending draft")
        return json.loads(row[1])

    def retry(self, key):
        # OS lock prevents retry while another process is making the paid call.
        with job_lock(self.directory / "locks" / (digest(key) + ".lock")):
            with self.connect() as db:
                row = db.execute("SELECT status FROM preparation_jobs WHERE id=?", (key,)).fetchone()
                if not row or row[0] not in ("failed", "processing"):
                    raise ValueError("only failed or interrupted processing jobs can be explicitly retried")
                db.execute("UPDATE preparation_jobs SET status='queued',error_code=NULL WHERE id=?", (key,))
        self.wake_event.set()

    def current(self, payload):
        handler = self.handlers.get(payload.get("content_schema"))
        if handler is not None:
            return handler.current(payload)
        with self.runtime.lock:
            entry = self.runtime.procedures.get(payload["procedure_id"])
            if entry is None:
                return False
            overlay = entry.get("overlay")
            return (graph_fingerprint(entry["graph"]) == payload["graph_fingerprint"]
                    and (overlay.model_dump(mode="json") if overlay else None) == payload.get("base_overlay")
                    and bool(entry["preparation"]["missing"]))

    def process_once(self):
        self.scan()
        if not self.enabled:
            return False
        with self.connect() as db:
            candidates = db.execute("SELECT id,payload FROM preparation_jobs WHERE status='queued' ORDER BY id").fetchall()
        for key, text in candidates:
            try:
                with job_lock(self.directory / "locks" / (digest(key) + ".lock")):
                    with self.connect() as db:
                        claimed = db.execute("UPDATE preparation_jobs SET status='processing' WHERE id=? AND status='queued'", (key,)).rowcount
                    if not claimed:
                        continue
                    payload = json.loads(text)
                    if not self.current(payload):
                        self.update(key, "stale"); continue
                    provider = None
                    try:
                        provider = self.provider_factory()
                        handler = self.handlers.get(payload.get("content_schema"))
                        if handler is not None:
                            artifact = handler.prepare(payload, provider)
                        else:
                            graph, overlay = job_entry(payload)
                            artifact = prepare(graph, provider, overlay)
                        if self.current(payload):
                            self.update(key, "pending_review", draft=json.dumps(artifact))
                        else:
                            self.update(key, "stale")
                    except Exception:
                        # Never persist exception bodies, prompts or credentials.
                        self.update(key, "failed", error="preparation_failed_requires_explicit_retry")
                    finally:
                        if provider is not None:
                            try:
                                provider.close()
                            except Exception:
                                pass
                    return True
            except OSError:
                continue  # Another worker owns this job.
        return False

    def run(self):
        while not self.stop_event.is_set():
            try:
                worked = self.process_once()
            except Exception:
                worked = False  # A queue I/O error must not stop citizen guidance.
            if not worked:
                self.wake_event.wait(self.interval)
                self.wake_event.clear()

    def start(self):
        self.scan()
        if self.enabled:
            self.thread = threading.Thread(target=self.run, name="c4-wording-preparation", daemon=True)
            self.thread.start()

    def close(self):
        self.stop_event.set(); self.wake_event.set()
        if self.thread:
            self.thread.join()  # Provider has a bounded timeout; runtime closes afterwards.
