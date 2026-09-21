from fastapi import FastAPI

from helaguide_common.config import get_settings
from helaguide_common.logging import setup_logging

from app.api.routes import router

settings = get_settings(service_name="c2-knowledge-graph")
log = setup_logging(settings.service_name, settings.log_level)

app = FastAPI(
    title="HelaGuide · Knowledge Graph and Service Orchestration Engine",
    version="0.1.0",
    description="Acquires government service pages, detects what changed, maintains a versioned knowledge graph, and turns a service into a dependency-ordered plan.",
)
app.include_router(router)


@app.get("/health", tags=["ops"])
async def health() -> dict:
    return {"service": "c2-knowledge-graph", "status": "ok", "stub_mode": settings.stub_mode}
