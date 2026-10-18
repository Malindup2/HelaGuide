"""
Module C, Algorithm 2: the diminishing-returns confidence update (DRCU).

    E_d  = sum of T*I over the best dispute report of each citizen
    E_s  = sum of T*I over the best support report of each citizen
    E    = max(0, E_d - gamma * E_s)
    conf = c0 * exp(-lambda * E)                       STANDARD form: exponential decay

    lambda = ln(c0 / theta_esc) / k                    CUSTOM: calibration-by-design

CALIBRATION BY DESIGN. lambda is not guessed and not fitted to data. It is solved from a plain
policy sentence: "k fully credible, independent reports must take a fact from c0 down to
theta_esc."  With c0 = 0.90, theta_esc = 0.50, k = 3:  lambda = ln(1.8) / 3 = 0.196.

The function recomputes from scratch every time, from all active reports, so late reports,
version changes and later reviewer decisions are all handled by simply running it again.
"""
from __future__ import annotations

import math
from datetime import datetime

from app.core.config import C3Settings
from app.core.repo import Repo
from app.models.internal import ConfidenceRecord, ReportRow


def calibrate_lambda(c0: float, theta: float, k: int) -> float:
    """Solve  theta = c0 * exp(-lambda * k)  for lambda."""
    if not (0 < theta < c0):
        raise ValueError("need 0 < theta_esc < c0")
    if k < 1:
        raise ValueError("k must be at least 1")
    return math.log(c0 / theta) / k


def confidence_from_evidence(c0: float, E: float, lam: float) -> float:
    return c0 * math.exp(-lam * max(E, 0.0))


def best_per_reporter(reports: list[ReportRow], kind: str) -> list[ReportRow]:
    """One report per citizen counts: the strongest one. Repeating yourself adds nothing."""
    best: dict[str, ReportRow] = {}
    for r in reports:
        if r.report_kind != kind:
            continue
        cur = best.get(r.reporter_id)
        if cur is None or r.trust_t * r.indep_i > cur.trust_t * cur.indep_i:
            best[r.reporter_id] = r
    return list(best.values())


def evidence(settings: C3Settings, reports: list[ReportRow]) -> dict:
    disputes = best_per_reporter(reports, "dispute")
    supports = best_per_reporter(reports, "support")
    E_d = sum(r.trust_t * r.indep_i for r in disputes)
    E_s = sum(r.trust_t * r.indep_i for r in supports)
    E = max(0.0, E_d - settings.gamma * E_s)
    return {"E_d": E_d, "E_s": E_s, "E": E, "n_dispute": len(disputes), "n_support": len(supports),
            "dispute_ids": [r.report_id for r in disputes], "support_ids": [r.report_id for r in supports]}


def status_for(settings: C3Settings, conf: float) -> str:
    if conf < settings.theta_esc:
        return "flagged"
    if conf < settings.active_cut:
        return "disputed"
    return "active"


def recompute(repo: Repo, settings: C3Settings, fact_id: str, valid_from: datetime, when: datetime,
              trigger: ReportRow | None = None) -> tuple[ConfidenceRecord, float, dict]:
    """Recompute one fact version's confidence. Returns (record, old confidence, evidence)."""
    rec = repo.get_confidence(fact_id, valid_from)
    if rec is None:
        raise KeyError(f"no confidence record for {fact_id} @ {valid_from}")
    old = rec.confidence
    active = repo.reports_for(fact_id, valid_from, states=["active"])
    ev = evidence(settings, active)
    lam = settings.lam
    new = confidence_from_evidence(rec.base_confidence, ev["E"], lam)
    rec.confidence = new
    rec.status = status_for(settings, new)
    if trigger and trigger.report_kind == "dispute" and trigger.indep_i >= 0.5 and (old - new) >= settings.min_step:
        rec.drop_events += 1
    rec.last_updated = when
    rec.last_reason = (f"{ev['n_dispute']} dispute / {ev['n_support']} support reports; "
                       f"E_d={ev['E_d']:.3f} E_s={ev['E_s']:.3f} E={ev['E']:.3f}; lambda={lam:.4f}")
    repo.save_confidence(rec)
    if trigger is not None:
        repo.add_audit(fact_id, valid_from, old, new, rec.last_reason, [trigger.report_id], when)
    return rec, old, ev
