"""V1 profile services integrated with V2 selection; no V1 policy writer.

The workspace owns one snapshot containing identity records and V2 research
records. Legacy preferences are translated explicitly, never by arm position.
"""
import json
import copy
from pathlib import Path
from types import SimpleNamespace
from pydantic import BaseModel, ConfigDict, Field
from app.core.user_context import InMemoryContextService
from app.core.demo_profiles import create_profile, set_personalization, restore_profiles
from app.models.demo_profiles import DemoProfile, CreateDemoProfileRequest
from app.models.runtime_state import SessionState
from app.models.user_context import ContextUpdate, FamiliarityReport
from app.v2.catalogue import Context
from app.v2.runtime import Runtime, Conflict, now
from app.v2.content import digest

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


class WorkspaceRuntime(Runtime):
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
        from app.v2.registration import RegistrationPacket, register
        for packet in self.state.get("registrations", {}).values():
            entry = register(RegistrationPacket.model_validate(packet))
            self.procedures[entry["graph"].plan_id] = entry
        from app.v2.preparation import resolve_artifact
        from app.v2.registration import finalize
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

    def resolve(self, session_id, procedure_id, overrides=None):
        if procedure_id not in self.procedures:
            raise ValueError("unknown procedure")
        if overrides:
            Context(**overrides)  # Validate types before inspecting nested maps.
        session = self.session(session_id)
        graph = self.procedures[procedure_id]["graph"]
        saved = self.settings(session_id)
        if any(k.startswith("locks.") for k in saved["legacy_review"]) and "locks" not in self.state.get("identity", {}).get("settings", {}).get(session_id, {}):
            raise ValueError("legacy hard requirements need explicit V2 review before adaptive use")
        access = session.settings.accessibility
        values = {"familiarity":session.settings.familiarity_for(graph.requested_service_id),
            "confidence":session.settings.navigation_capability, "preferences":saved["preferences"], "locks":saved["locks"],
            "no_map":not access.allow_relationship_visuals, "no_guided":not access.allow_guided_navigation,
            "no_collapsed":not access.allow_collapsed_content}
        owner=next((p for p in self.profiles.values() if p.session_id==session_id),None)
        origins = {k:"saved_profile" if owner else "guest_session" for k in values}
        origins["familiarity"] = "saved_service_report" if any(r.service_id==graph.requested_service_id for r in session.settings.familiarity) else "unknown"
        origins["confidence"] = "saved_general_default" if values["confidence"] is not None else "unknown"
        for name, value in (overrides or {}).items():
            if name not in ("familiarity", "confidence", "preferences", "locks"):
                raise ValueError("request overrides cannot weaken saved accessibility")
            if name == "preferences":
                value = {**values["preferences"], **value}
            if name == "locks":
                if any(k in values["locks"] and values["locks"][k] != v for k,v in value.items()):
                    raise ValueError("request override conflicts with a saved hard requirement")
                value = {**values["locks"], **value}
            values[name], origins[name] = value, "explicit_request"
        context = Context(**values)
        profile = next((p for p in self.profiles.values() if p.session_id == session_id), None)
        return context, {"resolver_version":RESOLVER, "session_id":session_id, "profile_id":profile.profile_id if profile else None,
            "context_revision":session.revision, "settings_revision":saved["settings_revision"], "profile_revision":profile.revision if profile else None,
            "requested_service_id":graph.requested_service_id, "values":context.model_dump(), "sources":origins,
            "legacy_review":saved["legacy_review"], "history_policy":"PP2 abstains; evidence retained separately"}

    def guidance(self, session_id, procedure_id, request_id, expected_revision, overrides=None, capability_token=None):
        with self.lock:
            session = self.session(session_id)
            if capability_token:
                from app.v2.content import digest
                import secrets
                existing=next((j for j in self.state["journeys"].values() if j["request_id"]==request_id),None)
                if existing:
                    if secrets.compare_digest(existing["token_hash"],digest(capability_token)) and (existing.get("identity") or {}).get("session_id")==session_id and existing["document"]["id"]==procedure_id:
                        return {"token":capability_token, **self.public(existing)}
                    raise Conflict("guidance request ID reused with different scope or capability")
            if self.settings(session_id)["settings_revision"] != expected_revision:
                raise Conflict("context changed; reload saved settings before requesting guidance")
            context, trace = self.resolve(session_id, procedure_id, overrides)
            profile = next((p for p in self.profiles.values() if p.session_id == session_id), None)
            adaptive = bool(profile and profile.personalization_enabled)
            if not adaptive:
                # Preserve standard guest/no-personalization semantics. Accessibility
                # remains binding; preferences and ratings do not select standard aids.
                context = Context(locks=context.locks, no_map=context.no_map, no_guided=context.no_guided, no_collapsed=context.no_collapsed)
                trace["selection_context"] = context.model_dump()
            return self.create(procedure_id, context, request_id, metadata=trace, standard=not adaptive, capability_token=capability_token)

    def register_procedure(self, packet):
        from app.v2.registration import register
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
        from app.v2.preparation import resolve_artifact
        from app.v2.registration import finalize
        from app.v2.content import Overlay
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
