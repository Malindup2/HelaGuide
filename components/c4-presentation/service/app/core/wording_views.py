"""Immutable UI wording snapshots beside the unchanged policy-state database.

Snapshots bind to an existing presentation; they create no new policy offer,
exposure, action-display event or learning reward. Old presentations without
a wording snapshot keep their original source rendering.
"""

from typing import Literal

from app.core.explanation_store import ArtifactStoreError, ExplanationArtifactStore, parse_artifact_json
from app.core.explanations import OutputRejected, _digest
from app.core.prepared_wording import wording_digest
from app.core.state_store import StateStoreError
from app.core.wording_service import PreparedWordingStore, resolve_wording
from app.models.prepared_wording import WordingArtifact, WordingResolution, WordingStyle
from app.models.procedure_graph import GraphRecord


class WordingView(GraphRecord):
    schema_version: Literal["c4-presentation-wording-1.0"] = "c4-presentation-wording-1.0"
    session_id: str
    presentation_id: str
    exposure_id: str
    graph_fingerprint: str
    writing_style: WordingStyle
    wording: WordingResolution
    artifact: WordingArtifact | None


class StoredView(GraphRecord):
    view: WordingView
    checksum: str


class CapturedStore:
    def __init__(self, artifact=None, error=None):
        self.artifact = artifact
        self.error = error

    def read(self, key):
        if self.error is not None:
            raise self.error
        return self.artifact


class WordingViews:
    def __init__(self, prepared_directory=None, snapshot_directory=None, demo_directory=None):
        self.prepared = None if prepared_directory is None else PreparedWordingStore(prepared_directory)
        self.files = None if snapshot_directory is None else ExplanationArtifactStore(snapshot_directory)
        self.memory = {}
        self.demo = None if demo_directory is None else PreparedWordingStore(demo_directory)

    def prepare(self, graph, *, writing_style="plain"):
        if self.prepared is None and self.demo is None:
            return None, None
        from app.core.prepared_wording import prepare_wording_packet, wording_key

        key = wording_key(prepare_wording_packet(graph, writing_style=writing_style))
        artifact, error = None, None
        try:
            artifact = self.prepared.read(key) if self.prepared is not None else None
            # Only absent production bundles use demo data. Invalid or pending
            # production content must remain a visible source fallback.
            if artifact is None and self.demo is not None:
                artifact = self.demo.read(key)
                if artifact is not None and artifact.origin != "demo_mock":
                    raise OutputRejected("demo_registry_requires_mock_origin")
        except (ArtifactStoreError, OutputRejected) as exc:
            error = exc
        # Resolve from one captured record, avoiding races with an editor's save.
        wording = resolve_wording(graph, CapturedStore(artifact, error), writing_style=writing_style,
                                  allow_demo_mock=self.demo is not None)
        if wording.artifact_digest is None:
            artifact = None
        return wording, artifact

    @staticmethod
    def key(spec):
        return _digest(["c4-presentation-wording-1.0", spec.session_id, spec.exposure_id, spec.presentation_id])

    def capture(self, spec, prepared, *, writing_style):
        wording, artifact = prepared
        if wording is None:
            return
        view = WordingView(
            session_id=spec.session_id, presentation_id=spec.presentation_id,
            exposure_id=spec.exposure_id, graph_fingerprint=spec.graph_fingerprint,
            writing_style=writing_style, wording=wording, artifact=artifact,
        )
        self._validate(spec, view)
        key = self.key(spec)
        stored = StoredView(view=view, checksum=_digest(view.model_dump(mode="json")))
        try:
            if self.files is not None:
                # This identity is unique. Never rewrite an existing presentation.
                existing = self.files.read_text(key)
                if existing is not None and existing != stored.model_dump_json(indent=2):
                    raise ArtifactStoreError("wording_view_already_exists")
                self.files.write_text(key, stored.model_dump_json(indent=2))
            else:
                if key in self.memory and self.memory[key] != stored:
                    raise ArtifactStoreError("wording_view_already_exists")
                self.memory[key] = stored
        except ArtifactStoreError:
            raise StateStoreError("cannot persist the presentation wording snapshot") from None

    def _validate(self, spec, view):
        if (view.session_id != spec.session_id or view.presentation_id != spec.presentation_id
            or view.exposure_id != spec.exposure_id or view.graph_fingerprint != spec.graph_fingerprint):
            raise StateStoreError("presentation wording attribution differs")
        graph = spec.explanation.source.graph
        # Missing/invalid content is frozen as source fallback. Do not adopt a
        # newly reviewed artifact while restoring an earlier presentation.
        expected = resolve_wording(graph, CapturedStore(view.artifact), writing_style=view.writing_style,
                                   allow_demo_mock=view.artifact is not None and view.artifact.origin == "demo_mock")
        if view.artifact is None:
            if (view.wording.artifact_digest is not None or view.wording.items != expected.items
                or view.wording.request_key != expected.request_key
                or view.wording.graph_fingerprint != expected.graph_fingerprint):
                raise StateStoreError("saved fallback wording differs from original sources")
        elif view.wording != expected or view.wording.artifact_digest != wording_digest(view.artifact):
            raise StateStoreError("saved reviewed wording differs from its artifact")

    def read(self, spec):
        view = self.read_view(spec)
        return None if view is None else view.wording

    def read_view(self, spec):
        """Read validated historical provenance without consulting today's registry."""
        key = self.key(spec)
        try:
            if self.files is None:
                stored = self.memory.get(key)
            else:
                text = self.files.read_text(key)
                stored = None if text is None else parse_artifact_json(StoredView, text)
            if stored is None:
                return None  # Legacy presentation: never decorate it retroactively.
            if stored.checksum != _digest(stored.view.model_dump(mode="json")):
                raise StateStoreError("presentation wording checksum mismatch")
            self._validate(spec, stored.view)
            return stored.view
        except (ArtifactStoreError, OutputRejected):
            raise StateStoreError("cannot restore valid presentation wording") from None
