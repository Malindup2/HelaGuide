"""Prepared-first content resolution; no policy selection or learning state writes."""
import json
import os
import sqlite3
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4
from app.guidance.catalogue import Configuration
from app.guidance.preparation import generate
from app.guidance.flavours import FLAVOUR_30
from app.guidance.sources import ProcedureSource
from app.v2.preparation_jobs import PreparationProcessor


@dataclass(frozen=True)
class PreparationSettings:
    mode: str = "demo"
    llm_enabled: bool = False
    on_miss: bool = False

    def __post_init__(self):
        if self.mode not in ("demo", "dynamic"):
            raise ValueError("content mode must be demo or dynamic")

    @property
    def generation_enabled(self):
        return self.mode == "dynamic" and self.llm_enabled and self.on_miss

    @classmethod
    def from_environment(cls):
        def flag(name):
            value = os.getenv(name, "false").lower()
            if value not in ("true", "false"):
                raise ValueError(name + " must be true or false")
            return value == "true"
        return cls(os.getenv("C4_PREPARED_CONTENT_MODE", "demo"), flag("C4_LLM_ENABLED"), flag("C4_PREPARATION_ON_MISS"))


class ContentPreparation:
    """A handler for the EXISTING durable queue/worker, not another worker engine."""
    def __init__(self, runtime, directory, *, settings=None, provider_factory=None, flavour=None):
        self.runtime = runtime
        self.flavour = flavour or FLAVOUR_30
        self.settings = settings or PreparationSettings()
        self.registry = self.flavour.make_registry(directory)
        self.processor = PreparationProcessor(runtime, self.registry.directory / "v2" / "jobs",
            enabled=self.settings.generation_enabled, provider_factory=provider_factory,
            handlers={self.flavour.content_schema: self})

    def source(self, procedure_id):
        with self.runtime.lock:
            entry = self.runtime.procedures.get(procedure_id)
            if entry is None:
                raise ValueError("unknown registered procedure")
            source = ProcedureSource(graph=entry["graph"], relationships=entry.get("overlay"))
        source.validate()
        return source

    def validate_job(self, payload):
        if payload.get("content_schema") != self.flavour.content_schema:
            raise ValueError("unsupported preparation schema")
        source = ProcedureSource.model_validate_json(json.dumps(payload["source"]))
        source.validate()
        if not isinstance(payload.get("language"), str) or not re.fullmatch(r"[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", payload["language"]):
            raise ValueError("invalid job language")
        if payload["procedure_id"] != source.graph.plan_id or payload["graph_fingerprint"] != source.graph_fingerprint:
            raise ValueError("job source mismatch")
        if self.key(payload) != payload["job_id"]:
            raise ValueError("changed preparation job")
        return source

    def key(self, payload):
        source = ProcedureSource.model_validate_json(json.dumps(payload["source"]))
        return self.flavour.cache_key(source, payload["language"])

    def published(self, payload):
        try:
            source = self.validate_job(payload)
            return self.registry.get(source, payload["language"]) is not None
        except ValueError:
            return False

    def current(self, payload):
        try:
            queued = self.validate_job(payload)
            source = self.source(payload["procedure_id"])
            return self.flavour.cache_key(source, payload["language"]) == self.flavour.cache_key(queued, payload["language"]) and self.registry.get(source, payload["language"]) is None
        except ValueError:
            return False

    def prepare(self, payload, provider):
        source = self.validate_job(payload)
        if self.flavour.name != "3.0":
            raise ValueError("content " + self.flavour.name + " is prepared offline and reviewed by name; no automatic generation")
        content, metadata = generate(source, payload["language"], provider)
        identifier = self.registry.draft(source, content)
        return {"status": "draft", "provisional": True, "artifact_id": identifier,
                "content": content.model_dump(mode="json"), **metadata}

    def enqueue(self, source, language):
        key = self.flavour.cache_key(source, language)
        payload = {"status": "pending_review_preparation", "job_id": key, "procedure_id": source.graph.plan_id,
                   "graph_fingerprint": source.graph_fingerprint, "content_schema": self.flavour.content_schema,
                   "language": language, "source": source.model_dump(mode="json")}
        target = self.processor.directory / (key + ".json")
        temporary = self.processor.directory / ("." + uuid4().hex + ".tmp")
        try:
            temporary.write_text(json.dumps(payload), encoding="utf-8")
            # Identical deterministic snapshots are safe under concurrent replace.
            try:
                os.link(temporary, target)  # Atomic immutable snapshot; no concurrent overwrite.
            except FileExistsError:
                pass
        finally:
            temporary.unlink(missing_ok=True)
        self.processor.scan()  # INSERT OR IGNORE is the durable concurrency boundary.
        self.processor.wake_event.set()
        return key

    def resolve(self, procedure_id, *, language="en", enqueue_on_miss=True):
        """Resolve one source/publication snapshot for composition and frozen journeys."""
        if not re.fullmatch(r"[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", language):
            raise ValueError("unsupported language tag")
        source = self.source(procedure_id)
        artifact = None
        error = None
        try:
            artifact = self.registry.get(source, language)
        except (ValueError, OSError, sqlite3.Error):
            error = "published_content_unavailable"
        job = None
        if artifact is None and enqueue_on_miss:
            try:
                job = self.enqueue(source, language)
            except (OSError, ValueError, sqlite3.Error):
                error = "preparation_queue_unavailable"
        job_state = None
        if job:
            try:
                job_state = next((j["status"] for j in self.processor.jobs() if j["id"] == job), "queued")
            except sqlite3.Error:
                error = "preparation_status_unavailable"
        metadata = {"content_state": "published" if artifact else "source_fallback",
                    "preparation_state": "published" if artifact else ("draft" if job_state == "pending_review" else (job_state or "pending")),
                    "job_state": job_state, "job_id": job, "error_code": error,
                    "generation_enabled": self.settings.generation_enabled, "mode": self.settings.mode,
                    "language": language, "fallback_language": "source_language" if not artifact else None,
                    "content_schema": self.flavour.content_schema, "artifact_id": artifact["id"] if artifact else None,
                    "review_kind": artifact["review_kind"] if artifact else None}
        metadata['source_kind'] = 'fictional' if source.graph.synthetic else 'bounded_official_source_snapshot'
        metadata['content_origin'] = artifact['content'].origin if artifact else 'source_preserving'
        review = artifact['content'].review if artifact else None
        metadata['source_review'] = {'reviewer':review.reviewer,'reviewed_at':review.reviewed_at.isoformat(),'scope_note':review.scope_note,'independent_government_validation':False} if review else None
        return source, artifact, metadata

    def request(self, procedure_id, *, language="en", configuration=None):
        source, artifact, metadata = self.resolve(procedure_id, language=language)
        content = artifact["content"] if artifact else None
        candidates = self.flavour.evaluate(source, content)
        requested = configuration or Configuration()
        selected = next(c for c in candidates if c.configuration == requested)
        if not selected.feasible:
            requested = Configuration()  # Compatibility content-preview endpoint only.
        return {**metadata, "selection_origin": "content_preview_no_learning",
                "requested_configuration_feasible": selected.feasible, "unavailable_reasons": list(selected.reasons),
                "capabilities": [{"configuration": c.configuration.model_dump(), "feasible": c.feasible, "reasons": list(c.reasons)} for c in candidates],
                "document": self.flavour.compose(source, content, requested)}

    def start(self):
        self.processor.start()

    def close(self):
        self.processor.close()
