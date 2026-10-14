from fastapi import APIRouter, HTTPException, Path, status

from helaguide_common.config import get_settings
from helaguide_common.contracts import FACT_ID, Feedback, TrustScore

from app.core import scoring
from app.models.internal import FreeTextFeedback

router = APIRouter(prefix="/v1", tags=["trust"])
internal = APIRouter(prefix="/internal", tags=["c3-private"])


@router.post("/feedback", status_code=status.HTTP_202_ACCEPTED)
def submit_feedback(feedback: Feedback) -> dict:
    """A citizen report about one fact (the contract message, C4 -> C3)."""
    scoring.ingest(feedback)
    return {"accepted": feedback.feedback_id}


@router.get("/trust/{fact_id}", response_model=TrustScore)
def get_trust(fact_id: str = Path(pattern=FACT_ID)) -> TrustScore:
    """Current confidence in one fact."""
    return scoring.trust_for(fact_id)


# ---------------------------------------------------------------------------
# C3-private routes (not part of contracts/): free-text feedback and the explain view.
# They need the real logic, so they refuse to run while STUB_MODE is true.
# ---------------------------------------------------------------------------
def _require_real_mode():
    if get_settings().stub_mode:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "This route needs the real C3 logic. Start the service with STUB_MODE=false.")


@internal.post("/freetext-feedback")
def freetext_feedback(message: FreeTextFeedback) -> dict:
    """Free-text feedback as C1 would forward it. Grounds it to a fact, then scores it."""
    _require_real_mode()
    from app.core.pipeline import get_pipeline
    return get_pipeline().process_freetext(message.model_dump(mode="json")).to_dict()


@internal.get("/explain/{fact_id}")
def explain(fact_id: str = Path(pattern=FACT_ID)) -> dict:
    """The full picture for one fact: percentage, internal status, warning code, reasons."""
    _require_real_mode()
    from app.core.pipeline import get_pipeline
    return get_pipeline().exposure.explain(fact_id)


@internal.post("/sync")
def sync_facts() -> dict:
    """Re-read the facts from the fact source and register any new versions."""
    _require_real_mode()
    from app.core.pipeline import get_pipeline
    results = get_pipeline().sync_facts()
    return {"facts": len(results), "new": sum(r.created for r in results),
            "new_versions": sum(r.new_version for r in results)}
