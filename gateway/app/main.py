from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from helaguide_common.config import get_settings
from helaguide_common.logging import setup_logging

from app.routes import guidance, ops

settings = get_settings(service_name="gateway")
log = setup_logging(settings.service_name, settings.log_level)

app = FastAPI(
    title="HelaGuide · Gateway",
    version="0.1.0",
    description="Composes the four components into one citizen-facing API.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(ops.router)
app.include_router(guidance.router)
