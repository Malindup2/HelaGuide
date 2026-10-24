"""Local research trace routes. GET handlers never create or update domain records."""

from fastapi import APIRouter, Response

from app.legacy.pipeline_trace import build_pipeline_trace, build_trace_index
from app.models.pipeline_trace import PipelineTrace, PipelineTraceIndex


def register_pipeline_trace_routes(application, runtime):
    router = APIRouter(tags=["pipeline-trace"])

    @router.get("/dev/v1/sessions/{session_id}/pipeline-traces", response_model=PipelineTraceIndex)
    def index(session_id: str, response: Response):
        current = runtime()
        with current.lock:
            current.assert_available()
            result = build_trace_index(current, session_id)
            response.headers["Cache-Control"] = "no-store"
            return result

    @router.get("/dev/v1/sessions/{session_id}/presentations/{exposure_id}/pipeline-trace",
                response_model=PipelineTrace)
    def trace(session_id: str, exposure_id: str, response: Response):
        current = runtime()
        with current.lock:
            current.assert_available()
            result = build_pipeline_trace(current, session_id, exposure_id)
            response.headers["Cache-Control"] = "no-store"
            return result

    application.include_router(router)
