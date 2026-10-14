"""
Module G: what C3 tells the rest of the system about a fact.

The confidence PERCENTAGE is always returned and always shown. Only the WARNING depends on the
history of the fact:
    conf < theta_esc                                   -> VERIFY_BEFORE_VISIT   (strong, always shown)
    >= n_drops confidence-lowering updates and
       conf < active_cut                               -> LOW_CONFIDENCE
    a new version the official source has just
       confirmed, with no new disputes                 -> VERIFIED_BY_SOURCE    (positive note)
    otherwise                                          -> NONE

The contract `trust` message has no warning field, so it carries the same decision in `status`:
    "disputed"            = show the warning (LOW_CONFIDENCE or VERIFY_BEFORE_VISIT)
    "verified_correction" = VERIFIED_BY_SOURCE
    "ok"                  = no warning
`explain()` returns the richer private answer used by the demo and the reviewer tools.
"""
from __future__ import annotations

from datetime import datetime, timezone

from helaguide_common.contracts import TrustScore

from app.core.config import C3Settings
from app.core.confidence import best_per_reporter
from app.core.dedup import claim_groups, claims_disagree
from app.core.repo import Repo
from app.core.util import iso
from app.models.internal import ConfidenceRecord


def warning_code(settings: C3Settings, rec: ConfidenceRecord) -> str:
    if rec.confidence < settings.theta_esc:
        return "VERIFY_BEFORE_VISIT"
    if rec.drop_events >= settings.n_drops and rec.confidence < settings.active_cut:
        return "LOW_CONFIDENCE"
    if rec.verified_by_source and rec.drop_events == 0:
        return "VERIFIED_BY_SOURCE"
    return "NONE"


def contract_status(code: str) -> str:
    if code in ("VERIFY_BEFORE_VISIT", "LOW_CONFIDENCE"):
        return "disputed"
    if code == "VERIFIED_BY_SOURCE":
        return "verified_correction"
    return "ok"


class Exposure:
    def __init__(self, repo: Repo, settings: C3Settings):
        self.repo, self.s = repo, settings

    def explain(self, fact_id: str) -> dict:
        v = self.repo.current_version(fact_id)
        rec = self.repo.get_confidence(fact_id, v.valid_from) if v else None
        if v is None or rec is None:
            return {"fact_id": fact_id, "known": False, "confidence": self.s.c_base,
                    "confidence_pct": round(100 * self.s.c_base), "internal_status": "unknown",
                    "warning_code": "NONE", "report_count": 0, "claims_disagree": False,
                    "updated_at": None, "version_valid_from": None}
        active = self.repo.reports_for(fact_id, v.valid_from, states=["active"])
        disputers = best_per_reporter(active, "dispute")
        code = warning_code(self.s, rec)
        last = max((r.submitted_at for r in active), default=None)
        return {
            "fact_id": fact_id, "known": True, "stored_value": v.value_text, "unit": v.unit,
            "confidence": round(rec.confidence, 4), "confidence_pct": round(100 * rec.confidence),
            "base_confidence": rec.base_confidence, "internal_status": rec.status,
            "warning_code": code, "contract_status": contract_status(code),
            "warning_params": {"report_count": len(disputers), "last_report_date": iso(last)},
            "report_count": len(disputers), "drop_events": rec.drop_events,
            "claims_disagree": claims_disagree(self.s, active),
            "claim_groups": {k: sorted(w) for k, w in claim_groups(active).items()},
            "verified_by_source": rec.verified_by_source,
            "updated_at": iso(rec.last_updated), "version_valid_from": iso(v.valid_from),
            "last_reason": rec.last_reason,
        }

    def contract_trust(self, fact_id: str) -> TrustScore:
        e = self.explain(fact_id)
        updated = e["updated_at"] or datetime.now(timezone.utc).isoformat()
        return TrustScore(fact_id=fact_id, confidence=e["confidence"],
                          status=e.get("contract_status", "ok"), report_count=e["report_count"],
                          updated_at=updated)

    def batch(self, fact_ids: list[str]) -> list[TrustScore]:
        return [self.contract_trust(f) for f in fact_ids]
