"""Opt-in backend content verification routes; no new application or policy."""
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from app.guidance.catalogue import Configuration

class ContentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    procedure_id: str
    language: str = Field(default="en", pattern=r"^[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")
    configuration: Configuration | None = None


def register_routes(app):
    def service():
        result = getattr(app.state, "prepared_content", None)
        if result is None:
            raise HTTPException(404, "controlled prepared-content integration is disabled")
        return result

    @app.get("/workspace/content/status")
    def status():
        prepared = service()
        return {"mode": prepared.settings.mode, "generation_enabled": prepared.settings.generation_enabled,
                "on_miss": prepared.settings.on_miss, "content_schema": "c4-guidance-content-3.0",
                "selection_origin": "content_preview_no_learning", "review_required": True}

    @app.post("/workspace/content/guidance")
    def request_content(body: ContentRequest):
        return service().request(body.procedure_id, language=body.language, configuration=body.configuration)

    @app.get("/workspace/content/jobs")
    def jobs():
        return service().processor.jobs()

    @app.get("/workspace/content/jobs/{job_id}/draft")
    def draft(job_id: str):
        return {"label": "Provisional researcher preview; NOT published citizen guidance",
                "provisional": True, "artifact": service().processor.draft(job_id)}
