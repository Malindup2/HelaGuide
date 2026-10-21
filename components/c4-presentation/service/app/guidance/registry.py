"""Isolated versioned wording registry. No policy tables or automatic approval."""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from app.guidance.content import GuidanceContent, validate_content
from app.guidance.sources import digest

CONTENT_SCHEMA = "c4-guidance-content-3.0"
REGISTRY_SCHEMA = "c4-prepared-registry-1.0"


def cache_key(source, language):
    return digest({"procedure": source.graph.plan_id, "graph": source.graph_fingerprint,
                   "relationships": source.relationship_fingerprint, "language": language, "schema": CONTENT_SCHEMA})


def semantic_body(content):
    def strip(value):
        if isinstance(value, dict):
            return {k: strip(v) for k, v in value.items() if k not in ("status", "review")}
        if isinstance(value, list):
            return [strip(v) for v in value]
        return value
    return strip(content.model_dump(mode="json"))


class ContentRegistry:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        c4 = Path(__file__).resolve().parents[3]
        if not self.directory.is_relative_to(c4) or "prepared-content" not in self.directory.parts:
            raise ValueError("use a dedicated C4/prepared-content directory; never a policy database")
        self.directory.mkdir(parents=True, exist_ok=True)
        self.database = self.directory / "registry.sqlite3"
        with self.connect() as db:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables and "registry_manifest" not in tables:
                raise ValueError("refusing an unrelated existing database")
            if tables and db.execute("SELECT schema FROM registry_manifest").fetchone() != (REGISTRY_SCHEMA,):
                raise ValueError("incompatible content registry")
            db.execute("CREATE TABLE IF NOT EXISTS registry_manifest(schema TEXT NOT NULL)")
            if not tables:
                db.execute("INSERT INTO registry_manifest VALUES (?)", (REGISTRY_SCHEMA,))
            db.execute("CREATE TABLE IF NOT EXISTS artifacts(id TEXT PRIMARY KEY, cache_key TEXT NOT NULL, state TEXT NOT NULL, body TEXT NOT NULL, review_kind TEXT, parent TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS publications(cache_key TEXT PRIMARY KEY, artifact_id TEXT NOT NULL)")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def _write(self, source, content, state, kind=None, parent=None):
        body = content.model_dump(mode="json")
        identifier = digest({"body": body, "state": state, "review_kind": kind, "parent": parent})
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO artifacts VALUES (?,?,?,?,?,?)", (identifier, cache_key(source, content.language), state, json.dumps(body), kind, parent))
        return identifier

    def draft(self, source, content):
        validate_content(source, content)
        def reviewed(value):
            if isinstance(value, dict):
                return value.get("status") == "reviewed" or any(reviewed(v) for v in value.values())
            return isinstance(value, list) and any(reviewed(v) for v in value)
        if content.review is not None or reviewed(content.model_dump(mode="json")):
            raise ValueError("draft cannot self-declare review")
        return self._write(source, content, "draft")

    def inspect(self, identifier):
        with self.connect() as db:
            row = db.execute("SELECT state,body,review_kind,parent FROM artifacts WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise ValueError("unknown content artifact")
        state, body, kind, parent = row
        content = GuidanceContent.model_validate_json(body)
        original_state = "reviewed" if state == "published" else state
        if identifier != digest({"body": content.model_dump(mode="json"), "state": original_state, "review_kind": kind, "parent": parent}):
            raise ValueError("changed stored content artifact")
        return {"id": identifier, "state": state, "content": content, "review_kind": kind, "parent": parent,
                "provisional": state == "draft"}

    def review(self, source, draft_id, content, *, kind):
        original = self.inspect(draft_id)
        if original["state"] != "draft" or semantic_body(original["content"]) != semantic_body(content):
            raise ValueError("review must match a stored draft exactly apart from review/status")
        validate_content(source, content)
        if not content.review or content.review.status != "reviewed":
            raise ValueError("named statement-level source review required")
        if kind not in ("internal_fictional_author", "human_source_fidelity"):
            raise ValueError("unknown review kind")
        if kind == "internal_fictional_author" and not source.graph.synthetic:
            raise ValueError("internal fictional review cannot approve government guidance")
        return self._write(source, content, "reviewed", kind, draft_id)

    def publish(self, source, identifier):
        artifact = self.inspect(identifier)
        if artifact["state"] not in ("reviewed", "published"):
            raise ValueError("only reviewed content can be published")
        validate_content(source, artifact["content"])
        key = cache_key(source, artifact["content"].language)
        with self.connect() as db:
            db.execute("INSERT INTO publications VALUES (?,?) ON CONFLICT(cache_key) DO UPDATE SET artifact_id=excluded.artifact_id", (key, identifier))
            db.execute("UPDATE artifacts SET state='published' WHERE id=?", (identifier,))
        return identifier

    def get(self, source, language="en"):
        with self.connect() as db:
            row = db.execute("SELECT artifact_id FROM publications WHERE cache_key=?", (cache_key(source, language),)).fetchone()
        if row is None:
            return None
        artifact = self.inspect(row[0])
        if artifact["state"] != "published" or artifact["content"].language != language:
            raise ValueError("invalid publication index")
        validate_content(source, artifact["content"])
        return artifact
