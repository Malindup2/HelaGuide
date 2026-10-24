"""Workspace identity: guest sessions, demo profiles and saved settings; no policy writer.

The workspace owns one record containing identity records and the legacy V2 research
records (app.host.store). WorkspaceIdentity holds only identity behaviour; the
WorkspaceRuntime assembly at the end adds the V2 journeys kept for existing contracts.
Legacy preferences are translated explicitly, never by arm position.
"""
import json
import copy
from pathlib import Path
from types import SimpleNamespace
from pydantic import BaseModel, ConfigDict, Field
from app.host.user_context import InMemoryContextService
from app.host.demo_profiles import create_profile, set_personalization, restore_profiles
from app.models.demo_profiles import DemoProfile, CreateDemoProfileRequest
from app.models.runtime_state import SessionState
from app.models.user_context import ContextUpdate, FamiliarityReport
from app.compat.v2_catalogue import Context
from app.host.store import Conflict, now

RESOLVER = "c4-effective-context-1.0"
IDENTITY_SCHEMA = "c4-workspace-identity-1.0"

class SettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=8, max_length=128)
    expected_revision: int = Field(ge=0)
    familiarity: list[FamiliarityReport] | None = None
    context: ContextUpdate = Field(default_factory=ContextUpdate)
    preferences: dict[str, str] | None = None
    locks: dict[str, str] | None = None


def legacy_choices(settings):
    """Compatible mappings only. Other meanings remain explicit review items."""
    prefs, locks, review = {}, {}, {}
    for kind, source, target in (("preferences", settings.preferences, prefs), ("locks", settings.locks, locks)):
        if source.presentation_mode is not None:
            target["navigation"] = source.presentation_mode.lower()
        if source.progressive_disclosure is not None:
            target["disclosure"] = "collapsed" if source.progressive_disclosure else "expanded"
        for name in ("previous_context_recap", "relationship_visual", "prerequisite_cue"):
            value = getattr(source, name)
            if value is not None:
                review[f"{kind}.{name}"] = value
    return prefs, locks, review


class WorkspaceIdentity:
    """Identity behaviour over the workspace record store (state, lock, _write, procedures)."""
    TABLE = "c4_workspace_state"

    def __init__(self, path=":memory:", **kwargs):
        if str(path) != ":memory:" and "workspace" not in Path(path).resolve().parts:
            raise ValueError("integrated storage must use a separate workspace directory")
        self._initial_procedures = kwargs.get("procedures")
        super().__init__(path, **kwargs)

    def _restore(self):
        super()._restore()
        if self._initial_procedures is not None:
            self.procedures = dict(self._initial_procedures)
        from app.procedures.registration import RegistrationPacket, register
        for packet in self.state.get("registrations", {}).values():
            entry = register(RegistrationPacket.model_validate(packet))
            self.procedures[entry["graph"].plan_id] = entry
        from app.preparation.overlay_drafts import resolve_artifact
        from app.compat.v2_documents import finalize
        for pid,artifact in self.state.get("approved_content",{}).items():
            if pid not in self.procedures:
                raise ValueError("approved content refers to an unknown procedure")
            self.procedures[pid] = finalize(resolve_artifact(self.procedures[pid]["graph"],artifact))
        saved = self.state.get("identity", {})
        if saved and saved.get("schema") != IDENTITY_SCHEMA:
            raise ValueError("unsupported workspace identity schema")
        self.contexts = InMemoryContextService.from_state(tuple(SessionState.model_validate_json(json.dumps(v)) for v in saved.get("sessions", [])))
        self.profiles = restore_profiles(tuple(DemoProfile.model_validate_json(json.dumps(v)) for v in saved.get("profiles", [])), self.contexts)

    def _identity(self):
        return self.state.setdefault("identity", {"schema": IDENTITY_SCHEMA, "sessions": [], "profiles": [], "settings": {}, "requests": {}, "imports": []})

    def _save_identity(self):
        saved = self._identity()
        saved["sessions"] = [s.model_dump(mode="json") for s in self.contexts.export_state()]
        saved["profiles"] = [p.model_dump(mode="json") for p in self.profiles.values()]

    def identity_change(self, fn):
        def change():
            result = fn()
            self._save_identity()
            return result
        return self._write(change)

    def session(self, session_id):
        return self.contexts.get_session(session_id)

    def profile_response(self, profile_id):
        with self.lock:
            if profile_id not in self.profiles:
                raise ValueError("unknown demo profile")
            profile = self.profiles[profile_id]
            return {"profile": profile.model_dump(mode="json"), "session": self.session(profile.session_id).model_dump(mode="json")}

    def create_session(self):
        return self.identity_change(lambda: self.contexts.create_session().model_dump(mode="json"))

    def create_profile(self, request: CreateDemoProfileRequest):
        # Reuse V1's validated onboarding, idempotency and service-scoped answers.
        proxy = SimpleNamespace(profiles=self.profiles, contexts=self.contexts, session=self.session,
            procedures={k:(p["graph"], None, None) for k,p in self.procedures.items()})
        return self.identity_change(lambda: create_profile(proxy, request).model_dump(mode="json"))

    def personalization(self, profile_id, request):
        def change():
            result = set_personalization(self, profile_id, request)
            if not result.profile.personalization_enabled:
                for journey in self.state["journeys"].values():
                    if (journey.get("identity") or {}).get("session_id") == result.profile.session_id:
                        journey["learning_revoked"] = True
            return result.model_dump(mode="json")
        return self.identity_change(change)

    def settings(self, session_id):
        with self.lock:
            session = self.session(session_id)
            native = self.state.get("identity", {}).get("settings", {}).get(session_id, {})
            prefs, locks, review = legacy_choices(session.settings)
            return {"session": session.model_dump(mode="json"), "preferences": native.get("preferences", prefs),
                    "locks": native.get("locks", locks), "legacy_review": {} if native.get("legacy_reviewed") else review,
                    "resolver_version": RESOLVER, "settings_revision": session.revision + native.get("revision", 0)}

    def update_settings(self, session_id, patch: SettingsPatch):
        # Legacy meanings are accepted only through the explicit import adapter.
        if {"preferences","locks"} & patch.context.model_fields_set:
            raise ValueError("use versioned V2 preferences/locks fields, not legacy context choices")
        # Dictionaries are full replacements, making explicit clearing reliable.
        for mapping in (patch.preferences, patch.locks):
            if mapping is not None:
                Context(preferences=mapping)
        def change():
            saved = self._identity()
            key = f"{session_id}:{patch.request_id}"
            payload = patch.model_dump(mode="json")
            if key in saved["requests"]:
                if saved["requests"][key] != payload:
                    raise Conflict("settings request ID reused with different data")
                return self.settings(session_id)
            current = self.session(session_id)
            before_effective = self.settings(session_id)
            if patch.context.familiarity is not None and patch.context.familiarity.service_id not in {p["graph"].requested_service_id for p in self.procedures.values()}:
                raise ValueError("unknown familiarity service")
            if self.settings(session_id)["settings_revision"] != patch.expected_revision:
                raise Conflict("settings revision changed; reload before editing")
            # V1's service enforces partial merge and records before/after values.
            updated = self.contexts.update_context(session_id, patch.context, expected_revision=current.revision)
            if patch.preferences is not None:
                nav=patch.preferences.get("navigation")
                disclosure=patch.preferences.get("disclosure")
                updated=self.contexts.update_context(session_id, ContextUpdate(preferences={
                    "presentation_mode":nav.upper() if nav else None,
                    "progressive_disclosure":disclosure=="collapsed" if disclosure else None}), expected_revision=updated.revision)
            if patch.familiarity is not None:
                services={p["graph"].requested_service_id for p in self.procedures.values()}
                ids=[r.service_id for r in patch.familiarity]
                if len(ids)!=len(set(ids)) or not set(ids)<=services:
                    raise ValueError("unknown or duplicate familiarity service")
                for report in patch.familiarity:
                    updated=self.contexts.update_context(session_id, ContextUpdate(familiarity=report), expected_revision=updated.revision)
            native = saved["settings"].setdefault(session_id, {})
            for name in ("preferences", "locks"):
                value = getattr(patch, name)
                if value is not None:
                    native[name] = value
            if patch.preferences is not None and patch.locks is not None:
                native["legacy_reviewed"] = True
            native["revision"] = native.get("revision", 0) + 1
            if current.settings.accessibility != updated.settings.accessibility or before_effective["locks"] != self.settings(session_id)["locks"]:
                for journey in self.state["journeys"].values():
                    if (journey.get("identity") or {}).get("session_id")==session_id:
                        journey["constraints_revoked"]=True
                        journey["learning_revoked"]=True
            saved["requests"][key] = payload
            saved.setdefault("settings_events", []).append({"session_id": session_id, "request_id":patch.request_id,
                "at":now(), "before":current.model_dump(mode="json"), "after":updated.model_dump(mode="json"),
                "native":dict(native), "reward":None})
            return self.settings(session_id)
        return self.identity_change(change)

    def register_procedure(self, packet):
        from app.procedures.registration import register
        entry=register(packet)
        pid=entry["graph"].plan_id
        payload=packet.model_dump(mode="json")
        def change():
            stored=self.state.setdefault("registrations",{})
            if pid in self.procedures:
                if stored.get(pid)==payload:
                    return self.procedures[pid]["preparation"]
                raise Conflict("procedure already registered; use a new versioned Plan identity")
            stored[pid]=payload
            self.procedures[pid]=entry
            return entry["preparation"]
        return self._write(change)

    def publish_wording(self, procedure_id, artifact):
        from app.preparation.overlay_drafts import resolve_artifact
        from app.compat.v2_documents import finalize
        from app.procedures.canonical import Overlay
        def change():
            if procedure_id not in self.procedures:
                raise ValueError("unknown procedure")
            original=self.procedures[procedure_id]
            prepared=resolve_artifact(original["graph"],artifact)
            # Wording publication is not a back door for generated graph edges.
            base=original.get("overlay") or Overlay(graph_fingerprint=original["document"]["graph_fingerprint"],reviewer="source registry")
            skip={"reviewer","variants","optional_content_ids"}
            if base.model_dump(exclude=skip)!=prepared["overlay"].model_dump(exclude=skip):
                raise ValueError("wording publication cannot change verified relationships")
            entry=finalize(prepared)
            self.state.setdefault("approved_content",{})[procedure_id]=copy.deepcopy(artifact)
            self.procedures[procedure_id]=entry
            return entry["preparation"]
        return self._write(change)


from app.compat.v2_runtime import Runtime  # noqa: E402  (assembly of the kept V2 contracts)
from app.compat.v2_workspace import V2WorkspaceGuidance  # noqa: E402


class WorkspaceRuntime(WorkspaceIdentity, V2WorkspaceGuidance, Runtime):
    """The live workspace: identity, plus the V2 journeys and policy served by /v2/* and
    /workspace/sessions/{id}/guidance, on one unchanged SQLite record."""
