from fastapi import APIRouter, Path, status

from helaguide_common.contracts import FACT_ID, Feedback, TrustScore

from app.core import scoring

router = APIRouter(prefix="/v1", tags=["trust"])


@router.post("/feedback", status_code=status.HTTP_202_ACCEPTED)
async def submit_feedback(feedback: Feedback) -> dict:
    """A citizen report about one fact."""
    scoring.ingest(feedback)
    return {"accepted": feedback.feedback_id}


@router.get("/trust/{fact_id}", response_model=TrustScore)
async def get_trust(fact_id: str = Path(pattern=FACT_ID)) -> TrustScore:
    """Current confidence in one fact."""
    return scoring.trust_for(fact_id)
