from typing import Literal

from fastapi import APIRouter, Query

from helaguide_common.contracts import Intent, UtteranceRequest

from app.core import pipeline
from app.models.details import ChatRequest, ChatResponse, CompletedRequest, DetailsRequest, IntentDetails

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


@router.get("/requests/completed", response_model=list[CompletedRequest], tags=["c1-internal"])
def completed_requests(
    session_id: str | None = None,
    endpoint: Literal["intent", "chat"] | None = None,
    intent: str | None = None,
    limit: int = Query(50, ge=1, le=500),
) -> list[CompletedRequest]:
    """C1-only: requests the chatbot completed (all slots filled and confirmed), newest first, with when.
    Saved by every /v1/intent, /v1/intent/details and /v1/chat turn; kept across restarts (C1_COMPLETED_DB)."""
    return pipeline.completed_requests(session_id, endpoint, intent, limit)
