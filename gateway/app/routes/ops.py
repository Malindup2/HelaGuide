import httpx
from fastapi import APIRouter

from app.clients import services

router = APIRouter(tags=["ops"])


@router.get("/health")
async def health() -> dict:
    return {"service": "gateway", "status": "ok"}


@router.get("/health/all")
async def health_all() -> dict:
    """Checks every component. Useful the first time you run docker compose."""
    async with httpx.AsyncClient() as client:
        return {"gateway": "ok", **(await services.health(client))}
