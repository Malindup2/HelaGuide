from fastapi import APIRouter

from helaguide_common.contracts import Intent, UtteranceRequest

from app.core import pipeline
from app.models.details import ChatRequest, ChatResponse, DetailsRequest, IntentDetails

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


@router.post("/chat", response_model=ChatResponse, tags=["c1-internal"])
def chat(req: ChatRequest) -> ChatResponse:
    """C1-only: one chat turn with a natural reply. C1_DIALOGUE_MODE picks who replies: rules (default, the
    engine's own reply), llm, or hybrid (LLM + NLU hints + validator). Chat sessions are separate from /v1/intent."""
    return pipeline.resolve_chat(req)
