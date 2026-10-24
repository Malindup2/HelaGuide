"""V2 guidance requested from saved workspace identity settings, kept for existing contracts.

Serves /workspace/sessions/{session_id}/guidance: the saved settings are resolved into the V2
context and a V2 journey is created. Mixed into app.host.identity.WorkspaceRuntime.
"""
from app.compat.v2_catalogue import Context
from app.host.store import Conflict


class V2WorkspaceGuidance:
    def resolve(self, session_id, procedure_id, overrides=None):
        from app.host.identity import RESOLVER
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
                from app.procedures.canonical import digest
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
