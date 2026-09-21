from fastapi import FastAPI

from helaguide_common.config import get_settings
from helaguide_common.logging import setup_logging

from app.api.routes import router

settings = get_settings(service_name="c4-presentation")
log = setup_logging(settings.service_name, settings.log_level)

app = FastAPI(
    title="HelaGuide · Context-Aware Adaptive Guidance Presentation Engine",
    version="0.1.0",
    description="Decides how to present a plan to this citizen: detail level, wording, voice, based on behavioural signals.",
)
app.include_router(router)


@app.get("/health", tags=["ops"])
async def health() -> dict:
    return {"service": "c4-presentation", "status": "ok", "stub_mode": settings.stub_mode}
