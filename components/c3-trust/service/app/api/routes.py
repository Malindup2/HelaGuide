from pathlib import Path as FsPath

from fastapi import APIRouter, HTTPException, Path, status
from fastapi.responses import FileResponse

from helaguide_common.config import get_settings
from helaguide_common.contracts import FACT_ID, Feedback, TrustScore

from app.core import scoring
from app.models.internal import DemoFeedbackRequest, FreeTextFeedback

router = APIRouter(prefix="/v1", tags=["trust"])
internal = APIRouter(prefix="/internal", tags=["c3-private"])
ui = APIRouter(tags=["c3-demo"])
demo = APIRouter(prefix="/internal/demo", tags=["c3-demo"])

UI_FILE = FsPath(__file__).resolve().parents[1] / "ui" / "index.html"


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


# ---------------------------------------------------------------------------
# The citizen console (python -m app.cli.serve): a page and the routes it uses. C3-private, real mode only.
# ---------------------------------------------------------------------------
@ui.get("/ui", include_in_schema=False)
def citizen_console():
    """The HelaGuide citizen console for demonstrating component 3 on its own."""
    return FileResponse(UI_FILE, media_type="text/html")


@demo.get("/workflow")
def demo_workflow() -> dict:
    """The mock workflow ("How do I get a passport?") with the live confidence of every fact."""
    _require_real_mode()
    from app.core.demo import get_demo
    return get_demo().workflow()


@demo.get("/personas")
def demo_personas() -> list:
    _require_real_mode()
    from app.core.demo import get_demo
    return get_demo().personas()


@demo.get("/samples")
def demo_samples() -> dict:
    _require_real_mode()
    from app.core.demo import get_demo
    return get_demo().samples()


@demo.post("/feedback")
def demo_feedback(req: DemoFeedbackRequest) -> dict:
    """Submit one pre-written sample message, or typed English text, as one of the demo citizens."""
    _require_real_mode()
    from app.core.demo import get_demo
    try:
        return get_demo().submit(req)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown sample or citizen: {exc}") from exc
    except ValueError as exc:                                                  # typed text the demo cannot take
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@demo.post("/official-update")
def demo_official_update() -> dict:
    """Simulate the official source publishing new values (C2 in the integrated system)."""
    _require_real_mode()
    from app.core.demo import get_demo
    return get_demo().official_update()


@demo.post("/reset")
def demo_reset() -> dict:
    _require_real_mode()
    from app.core.demo import get_demo
    return get_demo().reset()


@demo.get("/audit/{fact_id}")
def demo_audit(fact_id: str = Path(pattern=FACT_ID)) -> dict:
    """Versions, reports and the audit trail of one fact."""
    _require_real_mode()
    from app.core.demo import get_demo
    try:
        return get_demo().audit(fact_id)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown fact: {exc}") from exc
