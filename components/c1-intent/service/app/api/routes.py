from fastapi import APIRouter

from helaguide_common.contracts import Intent, UtteranceRequest

from app.core import pipeline
from app.models.details import DetailsRequest, IntentDetails

router = APIRouter(prefix="/v1", tags=["intent"])


# plain `def`: the model runs on CPU and would block the event loop; FastAPI runs these in a thread pool
@router.post("/intent", response_model=Intent)
def resolve_intent(req: UtteranceRequest) -> Intent:
    """Raw citizen text in, identified service out."""
    return pipeline.resolve(req)


@router.post("/intent/details", response_model=IntentDetails, tags=["c1-internal"])
def resolve_intent_details(req: DetailsRequest) -> IntentDetails:
    """C1-only: the full analysis (internal intent, route, slots, language tags). Not part of the contract.
    Shares sessions with /v1/intent. bot_text is the bot's last question, if any."""
    return pipeline.resolve_details(req)
