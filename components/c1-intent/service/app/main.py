from fastapi import FastAPI

from helaguide_common.config import get_settings
from helaguide_common.logging import setup_logging

from app.api.routes import router

settings = get_settings(service_name="c1-intent")
log = setup_logging(settings.service_name, settings.log_level)

app = FastAPI(
    title="HelaGuide · Multilingual Conversational Intent and Entity Understanding Engine",
    version="0.1.0",
    description="Turns a citizen's raw text (Sinhala, English or code-switched, multi-turn) into an identified service and entities.",
)
app.include_router(router)


@app.get("/health", tags=["ops"])
async def health() -> dict:
    return {"service": "c1-intent", "status": "ok", "stub_mode": settings.stub_mode}
