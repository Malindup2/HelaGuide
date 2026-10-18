"""
C3 entry points used by the HTTP routes.

STUB_MODE=true  : answer with the canned samples in contracts/examples (what the other
                  components test against). Keep this working.
STUB_MODE=false : the real PP1 logic in app/core/pipeline.py.

The research logic itself lives in the other modules of app/core/ (grounding, trust, dedup,
confidence, registry, exposure, pipeline).
"""
import logging
from datetime import datetime, timezone

from helaguide_common.config import get_settings
from helaguide_common.contracts import Feedback, TrustScore
from helaguide_common.examples import load_example

log = logging.getLogger(__name__)


def ingest(feedback: Feedback) -> None:
    if get_settings().stub_mode:
        log.info("stub: received feedback %s on %s", feedback.feedback_id, feedback.fact_id)
        return
    from app.core.pipeline import get_pipeline
    result = get_pipeline().process_structured(feedback.model_dump(mode="json"))
    log.info("feedback %s -> %s (%s)", feedback.feedback_id, result.state, result.reason)


def trust_for(fact_id: str) -> TrustScore:
    if get_settings().stub_mode:
        sample = load_example("trust")
        if fact_id == sample["fact_id"]:
            return TrustScore(**sample)
        return TrustScore(fact_id=fact_id, confidence=1.0, status="ok", report_count=0,
                          updated_at=datetime.now(timezone.utc))
    from app.core.pipeline import get_pipeline
    return get_pipeline().exposure.contract_trust(fact_id)
