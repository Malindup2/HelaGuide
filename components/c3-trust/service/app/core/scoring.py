"""
C3 research logic. Replace the stub with: embed feedback, cluster similar reports,
filter duplicates and coordinated reports, score confidence, emit corrections to C2.
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
    raise NotImplementedError("feedback ingestion not implemented yet")


def trust_for(fact_id: str) -> TrustScore:
    if get_settings().stub_mode:
        sample = load_example("trust")
        if fact_id == sample["fact_id"]:
            return TrustScore(**sample)
        return TrustScore(fact_id=fact_id, confidence=1.0, status="ok", report_count=0,
                          updated_at=datetime.now(timezone.utc))
    raise NotImplementedError("trust scoring not implemented yet")
