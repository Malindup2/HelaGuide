from fastapi import APIRouter

from helaguide_common.contracts import Intent, UtteranceRequest

from app.core import pipeline

router = APIRouter(prefix="/v1", tags=["intent"])


# plain `def`: the model runs on CPU and would block the event loop; FastAPI runs these in a thread pool
@router.post("/intent", response_model=Intent)
def resolve_intent(req: UtteranceRequest) -> Intent:
    """Raw citizen text in, identified service out."""
    return pipeline.resolve(req)
