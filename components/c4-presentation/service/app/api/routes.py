from fastapi import APIRouter

from helaguide_common.contracts import Render, RenderRequest

from app.core import adapter

router = APIRouter(prefix="/v1", tags=["presentation"])


@router.post("/render", response_model=Render)
async def render(req: RenderRequest) -> Render:
    """A plan in, the same plan adapted for this citizen out."""
    return adapter.render(req)
