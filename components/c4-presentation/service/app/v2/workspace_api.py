"""Identity compatibility endpoints for the existing citizen workspace."""
from pydantic import BaseModel, ConfigDict, Field
from app.models.demo_profiles import CreateDemoProfileRequest, PersonalizationRequest
from app.v2.identity import SettingsPatch

class ReviewedWording(BaseModel):
    model_config=ConfigDict(extra="forbid")
    artifact: dict

class GuidanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    procedure_id: str
    request_id: str = Field(min_length=8, max_length=128)
    expected_revision: int = Field(ge=0)
    capability_token: str | None = Field(default=None,min_length=32,max_length=128)
    overrides: dict = Field(default_factory=dict)


def register_routes(app, runtime):
    @app.get("/health")
    def health():
        return {"service":"c4-independent-dev", "status":"ok", "storage":"isolated workspace SQLite", "exposure_requires_acknowledgment":True, "version":"c4-workspace-1.0"}

    @app.get("/dev/v1/procedures")
    def procedures():
        return [{"procedure_id":k, "plan_id":p["graph"].plan_id, "title":p["document"]["title"],
            "requested_service_id":p["graph"].requested_service_id, "synthetic":p["graph"].synthetic,
            "disclaimer":p["graph"].disclaimer, "action_ids":[a.action_id for a in p["graph"].actions],
            "completeness":p["graph"].completeness.model_dump(), "features":p["measurements"].model_dump(mode="json")}
            for k,p in runtime().procedures.items()]

    @app.get("/dev/v1/demo-profiles")
    def profiles():
        with runtime().lock:
            return [p.model_dump(mode="json") for p in runtime().profiles.values()]

    @app.post("/dev/v1/demo-profiles")
    def create_profile(body: CreateDemoProfileRequest):
        return runtime().create_profile(body)

    @app.get("/dev/v1/demo-profiles/{profile_id}")
    def profile(profile_id: str):
        return runtime().profile_response(profile_id)

    @app.patch("/dev/v1/demo-profiles/{profile_id}/personalization")
    def personalization(profile_id: str, body: PersonalizationRequest):
        return runtime().personalization(profile_id, body)

    @app.post("/dev/v1/sessions")
    def guest():
        return runtime().create_session()

    @app.get("/dev/v1/sessions/{session_id}")
    def session(session_id: str):
        return runtime().session(session_id).model_dump(mode="json")

    @app.get("/workspace/sessions/{session_id}/settings")
    def settings(session_id: str):
        return runtime().settings(session_id)

    @app.patch("/workspace/sessions/{session_id}/settings")
    def edit(session_id: str, body: SettingsPatch):
        return runtime().update_settings(session_id, body)

    @app.post("/workspace/sessions/{session_id}/guidance")
    def guidance(session_id: str, body: GuidanceRequest):
        return runtime().guidance(session_id, body.procedure_id, body.request_id, body.expected_revision, body.overrides, body.capability_token)

    from app.v2.registration import RegistrationPacket
    @app.post("/workspace/procedures")
    def register(body: RegistrationPacket):
        result=runtime().register_procedure(body)
        from app.v2.registration import queue_preparation
        if result["missing"]:
            database=runtime().db.execute("PRAGMA database_list").fetchone()[2]
            if database:
                from pathlib import Path
                queue_preparation(runtime().procedures[result["procedure_id"]],Path(database).parent/"preparation")
        return result

    @app.post("/workspace/procedures/{procedure_id}/wording")
    def publish(procedure_id: str,body: ReviewedWording):
        return runtime().publish_wording(procedure_id,body.artifact)

    @app.get("/workspace/preparation")
    def preparation():
        from app.v2.registration import preparation_status
        return [preparation_status(p) for p in runtime().procedures.values()]
