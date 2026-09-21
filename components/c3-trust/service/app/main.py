from fastapi import FastAPI

from helaguide_common.config import get_settings
from helaguide_common.logging import setup_logging

from app.api.routes import router

settings = get_settings(service_name="c3-trust")
log = setup_logging(settings.service_name, settings.log_level)

app = FastAPI(
    title="HelaGuide · Civic Trust and Knowledge Verification Engine",
    version="0.1.0",
    description="Scores citizen feedback, detects duplicate and coordinated reports, and emits verified corrections.",
)
app.include_router(router)


@app.get("/health", tags=["ops"])
async def health() -> dict:
    return {"service": "c3-trust", "status": "ok", "stub_mode": settings.stub_mode}
