"""Independent V2 API. Bind to loopback; capability tokens protect journey reads."""
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from app.v2.catalogue import Configuration, Context
from app.v2.runtime import Runtime, Conflict

class Request(BaseModel):
    model_config = ConfigDict(extra="forbid")

class Start(Request):
    procedure_id: str
    context: Context = Field(default_factory=Context)
    request_id: str = Field(min_length=8, max_length=128)

class Event(Request):
    event_id: str = Field(min_length=8, max_length=128)
    view_id: str
    type: Literal["action_visible", "opportunity_visible", "navigate", "detail_open", "detail_close", "recap_open", "source_open", "route_focus", "reason", "map_expand", "map_collapse"]
    action_id: str | None = None
    opportunity_id: str | None = None
    client_timestamp: str | None = None
    value: str | None = Field(default=None, max_length=100)

class Adjustment(Request):
    event_id: str = Field(min_length=8, max_length=128)
    view_id: str
    configuration: Configuration

class Rating(Request):
    view_id: str
    rating: Literal["about_right", "need_more", "too_much"]


def create_app(path=None, *, mode="simulation", seed=0, runtime=None, runtime_class=Runtime, workspace=False, preparation_options=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.runtime = runtime or runtime_class(path or Path(__file__).resolve().parents[2] / ".local" / "v2" / mode / "state.sqlite3", mode=mode, seed=seed)
        processor = None
        if workspace:
            database = app.state.runtime.db.execute("PRAGMA database_list").fetchone()[2]
            if database:
                from app.v2.preparation_jobs import PreparationProcessor
                from app.v2.registration import queue_preparation
                directory = Path(database).parent / "preparation"
                for entry in app.state.runtime.procedures.values():
                    if entry["preparation"]["missing"]:
                        queue_preparation(entry, directory)
                processor = PreparationProcessor(app.state.runtime, directory, **(preparation_options or {}))
                processor.start()
        app.state.preparation_processor = processor
        try:
            yield
        finally:
            if processor is not None:
                import asyncio
                await asyncio.to_thread(processor.close)
            if runtime is None:
                app.state.runtime.close()
    app = FastAPI(title="C4 V2 research", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"], allow_methods=["GET", "POST", "PATCH"], allow_headers=["Content-Type", "X-C4-Token"])
    def rt():
        return app.state.runtime
    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse(status_code=409 if isinstance(exc, Conflict) else 422, content={"detail": str(exc)})
    @app.exception_handler(PermissionError)
    async def forbidden(request, exc):
        return JSONResponse(status_code=403, content={"detail": str(exc)})
    @app.get("/v2/health")
    def health():
        return {"status": "ok", "origin": mode, "version": "c4-v2.1"}
    @app.get("/v2/procedures")
    def procedures():
        return [{"id": k, "title": p["document"]["title"], "synthetic": p["document"]["synthetic"]} for k, p in rt().procedures.items()]
    @app.get("/v2/policy")
    def policy():
        return rt().status()
    @app.post("/v2/journeys")
    def start(body: Start):
        if workspace:
            raise ValueError("use the workspace session guidance endpoint for identity-attributed selection")
        return rt().create(body.procedure_id, body.context, body.request_id)
    @app.get("/v2/journeys/{journey_id}")
    def read(journey_id: str, x_c4_token: str = Header()):
        return rt().read(journey_id, x_c4_token)
    @app.post("/v2/journeys/{journey_id}/events")
    def event(journey_id: str, body: Event, x_c4_token: str = Header()):
        return rt().event(journey_id, x_c4_token, body.model_dump(exclude_none=True))
    @app.post("/v2/journeys/{journey_id}/adjustments")
    def adjust(journey_id: str, body: Adjustment, x_c4_token: str = Header()):
        return rt().adjust(journey_id, x_c4_token, body.view_id, body.configuration, body.event_id)
    @app.post("/v2/journeys/{journey_id}/ratings")
    def rate(journey_id: str, body: Rating, x_c4_token: str = Header()):
        return rt().rate(journey_id, x_c4_token, body.view_id, body.rating)
    @app.get("/v2/journeys/{journey_id}/inspector")
    def inspector(journey_id: str, x_c4_token: str = Header()):
        return rt().inspect(journey_id, x_c4_token)
    if workspace:
        from app.v2.workspace_api import register_routes
        register_routes(app, rt)
    return app

app = create_app(os.getenv("C4_V2_DATABASE"), mode=os.getenv("C4_V2_MODE", "simulation"), seed=int(os.getenv("C4_V2_SEED", "0")))
