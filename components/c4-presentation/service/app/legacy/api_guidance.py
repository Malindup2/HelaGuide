"""Profile-aware frontend entry point for standard or adaptive guidance."""

from fastapi import APIRouter, HTTPException

from app.legacy.guidance_access import guidance_status, require_personalization
from app.legacy.standard_guidance import build_standard_guidance
from app.models.guidance import (
    AdaptiveGuidanceResponse,
    GuidanceRequest,
    GuidanceResponse,
    GuidanceStatus,
    StandardGuidanceResponse,
)


def register_guidance_routes(application, runtime, select_presentation):
    router = APIRouter(tags=["guidance"])

    @router.get(
        "/dev/v1/sessions/{session_id}/guidance-status",
        response_model=GuidanceStatus,
    )
    def status(session_id: str):
        current = runtime()
        with current.lock:
            return guidance_status(current, session_id)

    @router.post(
        "/dev/v1/sessions/{session_id}/guidance",
        response_model=GuidanceResponse,
    )
    def get_guidance(session_id: str, request: GuidanceRequest):
        current = runtime()
        with current.lock:
            status = guidance_status(current, session_id)
            if request.expected_revision != status.session_revision:
                raise HTTPException(409, "session revision changed")
            if status.profile_id is not None:
                if request.expected_profile_revision != status.profile_revision:
                    raise HTTPException(
                        409,
                        "profile revision changed or was not supplied",
                    )
            elif request.expected_profile_revision is not None:
                raise HTTPException(409, "this session has no demo profile")

            if status.personalization_enabled:
                require_personalization(current, session_id)
                if request.standard_writing_style != "plain":
                    raise HTTPException(
                        422,
                        "standard_writing_style applies only to standard guidance",
                    )
                selected = select_presentation(session_id, request)
                return AdaptiveGuidanceResponse(
                    **status.model_dump(),
                    spec=selected.spec,
                    stale_for_display=selected.stale_for_display,
                    wording=selected.wording,
                )

            if request.focus_action_id is not None:
                raise HTTPException(
                    422,
                    "focus_action_id applies only to adaptive guidance",
                )
            graph, _, safety = current.procedure(request.procedure_id)
            wording, _ = current.wording_views.prepare(graph, writing_style=request.standard_writing_style)
            guidance = build_standard_guidance(
                graph,
                current.explanations,
                safety=safety,
                writing_style=request.standard_writing_style,
            )
            return StandardGuidanceResponse(
                **status.model_dump(),
                guidance=guidance,
                wording=wording,
            )

    application.include_router(router)
