"""Explicit controls for adaptive presentations, separate from policy selection."""
from fastapi import APIRouter, HTTPException, Response
from app.legacy import adjustments
from app.models.adjustments import AdjustmentState, ViewRequest, ViewDisplayRequest, ViewRatingRequest, ViewPreferenceRequest
from app.models.user_context import ContextUpdate, SoftPreferences, PreferenceChange, GuestSession


def register_adjustment_routes(application, runtime):
    router = APIRouter(tags=["presentation-adjustments"])
    base = "/dev/v1/sessions/{session_id}/presentations/{exposure_id}/views"

    @router.get(base, response_model=AdjustmentState)
    def get_views(session_id: str, exposure_id: str, response: Response):
        current = runtime()
        with current.lock:
            current.assert_available()
            root = current.presentation(session_id, exposure_id)
            response.headers["Cache-Control"] = "no-store"
            return adjustments.state(current, root)

    def mutate(session_id, exposure_id, request, operation):
        current = runtime()
        with current.lock:
            current.assert_available()
            root = current.presentation(session_id, exposure_id)
            with current.adjustments.transaction():
                return operation(current, root, request)

    @router.post(base, response_model=AdjustmentState)
    def adjust(session_id: str, exposure_id: str, request: ViewRequest):
        return mutate(session_id, exposure_id, request, adjustments.adjust)

    @router.post(base + "/display", response_model=AdjustmentState)
    def display(session_id: str, exposure_id: str, request: ViewDisplayRequest):
        return mutate(session_id, exposure_id, request, adjustments.display)

    @router.post(base + "/rating", response_model=AdjustmentState)
    def rating(session_id: str, exposure_id: str, request: ViewRatingRequest):
        return mutate(session_id, exposure_id, request, adjustments.rate)

    @router.post(base + "/preferences", response_model=GuestSession)
    def preferences(session_id: str, exposure_id: str, request: ViewPreferenceRequest):
        current = runtime()
        with current.change():
            root = current.presentation(session_id, exposure_id)
            ledger = adjustments.read(current, root)
            view = next((v for v in ledger.views if v.view_id == request.view_id), None)
            if view is None:
                raise HTTPException(409, "unknown manual view")
            # Deterministic event identity binds retries to this view and target preferences.
            from hashlib import sha256
            event_id = "event:" + sha256((exposure_id + request.view_id + request.request_id).encode()).hexdigest()[:32]
            values = view.configuration.model_dump(exclude={"configuration_id"})
            existing = next((e for e in current.contexts.event_history(session_id) if e.event_id == event_id), None)
            if existing:
                if not isinstance(existing, PreferenceChange) or existing.sequence != request.expected_session_revision + 1 or any(getattr(existing.after.preferences, key) != val for key, val in values.items()):
                    raise HTTPException(409, "preference retry differs from original request")
                return current.session(session_id)
            if request.view_id != adjustments.current_id(ledger) or not any(d.view_id == request.view_id for d in ledger.displays):
                raise HTTPException(409, "save preferences only from the current acknowledged view")
            if current.response(root).stale_for_display:
                raise HTTPException(409, "settings or routing changed; request fresh guidance")
            session = current.session(session_id)
            if all(getattr(session.settings.preferences, key) == val for key, val in values.items()):
                return session
            if session.revision != request.expected_session_revision:
                raise HTTPException(409, "session revision changed")
            return current.contexts.update_context(session_id, ContextUpdate(preferences=SoftPreferences(**values)),
                expected_revision=request.expected_session_revision, event_id=event_id)

    application.include_router(router)
