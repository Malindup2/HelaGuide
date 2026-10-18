"""
Module D (PP1 part), Algorithm 3a: near-duplicate detection, independence weights, claim groups.

Why it matters: ten copies of one story are not ten witnesses. Each report gets an
independence weight  I = rho ** dup  where dup is the number of EARLIER reports, by OTHER
citizens, whose text is almost the same (cosine similarity >= tau_dup).

Agreement is NOT penalised: three different citizens saying "12,000" in their own words each
keep I = 1. Claim groups are only used to notice when citizens disagree with each other.

Not in PP1: attack detection (burst, new-account flood), quarantine. Those are PP2.
"""
from __future__ import annotations

import numpy as np

from app.core.config import C3Settings
from app.models.internal import ReportRow


def independence(settings: C3Settings, new_embedding: np.ndarray | None, reporter_id: str, kind: str,
                 earlier: list[ReportRow]) -> tuple[float, int, list[dict]]:
    """Returns (I, dup_count, the near-duplicates found)."""
    near = []
    if new_embedding is not None:
        for r in earlier:
            if r.reporter_id == reporter_id or r.report_kind != kind or r.embedding is None:
                continue
            sim = float(np.dot(new_embedding, r.embedding))
            if sim >= settings.tau_dup:
                near.append({"report_id": r.report_id, "similarity": round(sim, 3)})
    return settings.rho ** len(near), len(near), near


def claim_key(claimed_num: float | None, claimed_raw: str | None) -> str:
    if claimed_num is not None:
        return f"num:{claimed_num:g}"
    if claimed_raw:
        return "txt:" + " ".join(claimed_raw.lower().split())
    return "unspecified"


def claim_groups(reports: list[ReportRow]) -> dict[str, set[str]]:
    """claim -> the set of different citizens who made it (disputes only, specific claims only)."""
    groups: dict[str, set[str]] = {}
    for r in reports:
        if r.report_kind != "dispute" or r.claimed_key == "unspecified":
            continue
        groups.setdefault(r.claimed_key, set()).add(r.reporter_id)
    return groups


def claims_disagree(settings: C3Settings, reports: list[ReportRow]) -> bool:
    """True when two or more different claims are each backed by n_supp or more citizens."""
    strong = [k for k, who in claim_groups(reports).items() if len(who) >= settings.n_supp]
    return len(strong) >= 2
