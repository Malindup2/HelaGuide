"""Approve the clean facts automatically; hold only the exceptions for a person.

A fact is clean when every check below passes. The checks are deliberately strict: a held fact
costs a person a few seconds, a wrong approved fact costs trust in the graph. Anything held says
why, so the exceptions list can be read at a glance.

Auto-approved rows are recorded in review_log under the reviewer name AUTO, so they can always be
told apart from human decisions and sampled for an accuracy check.
"""

from __future__ import annotations

import random
import re
from collections import Counter
from dataclasses import dataclass

AUTO = "auto-rules"
AUTO_REASON = "auto: quote is on the page, known service, no conflict, no case condition"

# A brand-new service is approved without a person (it still needs real content: a fee, a
# document, a step or a time, which the extractor already requires). Set False to make a person
# confirm every new service name first.
AUTO_NEW_SERVICES = True

# What may be approved without a person. Eligibility is free text, so it always waits.
AUTO_PREDICATES = {"fee", "document", "prerequisite", "processing_time", "agency"}

_CONDITIONAL = re.compile(
    r"(?i)\b(if|unless|in the event|at the event|in case|provided that|when the|where the|"
    r"in lieu|on behalf|not presented)\b")
# A derived "requires service" link is wrong when the person already holds the item, or the
# whole process is about losing, returning or penalising.
_HOLDS_ALREADY = re.compile(
    r"(?i)\b(deceased|surrender|hand over|lost|late|penalty|fine|duplicate (?:copy|certificate|card))\b")
_FREE = re.compile(r"(?i)^\s*(foc|free( of charge)?|nil|no charge|exempt)\b")
_PLACEHOLDER = re.compile(r"[.…_]{4,}|\bn/?a\b|^\s*[\d.]+\s*$|^\s*(rs\.?|lkr)?\s*[.…_]+\s*$", re.I)
_DURATION = re.compile(r"(?i)\d|\b(hour|day|week|month|year|minute|immediate|same day|one)\b")


@dataclass
class Row:
    staged_id: int
    fact_id: str
    service_id: str
    predicate: str
    value_text: str
    value_num: float | None
    unit: str | None
    evidence: str
    detail: dict
    service_known: bool      # the service already has an approved fact
    approved_value: str | None  # value already approved for this exact position
    rivals: int              # other waiting rows for the same position with a different value


def classify(r: Row) -> tuple[bool, str]:
    """(auto-approvable, reason). The reason is the first check that failed, or why it passed."""
    if r.predicate not in AUTO_PREDICATES:
        return False, f"{r.predicate} is free text: a person reads it"
    if not r.service_known and not AUTO_NEW_SERVICES:
        return False, "new service: a person confirms the name before it exists in the graph"
    if r.rivals:
        return False, "conflict: another waiting value for the same position"
    if r.approved_value is not None and r.approved_value.strip() != r.value_text.strip():
        return False, "changed: replaces a value already in the graph"
    if not r.evidence.strip():
        return False, "no quote"
    if r.predicate == "fee":
        # A fee needs an amount (the currency may be missing: a table column header gives it),
        # or to say plainly that it is free. A row of dots or underscores is a blank.
        if re.search(r"[.…_]{4,}", r.value_text):
            return False, "the value is a blank or placeholder"
        if r.value_num is None and not _FREE.search(r.value_text):
            return False, "fee without an amount"
    elif _PLACEHOLDER.search(r.value_text):
        return False, "the value is a blank or placeholder"
    if r.predicate == "processing_time" and not _DURATION.search(r.value_text):
        return False, "not a duration"
    if r.predicate in ("document", "prerequisite") and not (3 <= len(r.value_text.strip()) <= 220):
        return False, "document or step text is too short or too long"
    if _CONDITIONAL.search(r.evidence) or _CONDITIONAL.search(r.value_text):
        return False, "applies only in some cases: the graph cannot express the condition yet"
    target = (r.detail.get("requires_service") or "").replace("svc:", "")
    if target and _HOLDS_ALREADY.search(r.evidence + " " + r.service_id):
        return False, "derived link may not mean 'get it first' here (item already held)"
    if target and target in r.service_id.replace("svc:", ""):
        return False, "the service is about the item itself, so 'requires' means you already hold it"
    return True, AUTO_REASON


_SQL = """
SELECT s.staged_id, s.fact_id, s.service_id, s.predicate, s.value_text, s.value_num, s.unit,
       s.evidence, s.detail,
       EXISTS (SELECT 1 FROM c2.staged_facts a
                WHERE a.service_id = s.service_id AND a.status = 'approved') AS known,
       (SELECT p.value_text FROM c2.staged_facts p
         WHERE p.fact_id = s.fact_id AND p.status = 'approved'
         ORDER BY p.staged_id DESC LIMIT 1) AS approved_value,
       (SELECT count(*) FROM c2.staged_facts o
         WHERE o.fact_id = s.fact_id AND o.status = 'pending'
           AND o.staged_id <> s.staged_id AND o.value_text <> s.value_text) AS rivals
FROM c2.staged_facts s
WHERE s.status = 'pending'
ORDER BY s.staged_id
"""


def load_pending(conn) -> list[Row]:
    out = []
    for (sid, fid, svc, pred, val, num, unit, ev, det, known, old, rivals) in conn.execute(_SQL):
        out.append(Row(sid, fid, svc, pred, val or "", float(num) if num is not None else None,
                       unit, ev or "", det if isinstance(det, dict) else {}, bool(known), old,
                       int(rivals)))
    return out


def run(dsn: str, apply: bool = False) -> dict:
    """Classify every waiting fact. With apply=True the clean ones are approved.

    Returns {"clean": n, "held": n, "reasons": {reason: n}, "approved": n, "held_ids": [...]}.
    """
    import psycopg

    from app.core.graph.review import ReviewStore

    with psycopg.connect(dsn) as conn:
        rows = load_pending(conn)
    verdicts = [(r, *classify(r)) for r in rows]
    clean = [r.staged_id for r, ok, _ in verdicts if ok]
    reasons = Counter(why for _, ok, why in verdicts if not ok)
    approved = 0
    if apply and clean:
        store = ReviewStore(dsn)
        try:
            approved, _ = store.decide_many(clean, "approved", AUTO, AUTO_REASON)
        finally:
            store.close()
    return {"clean": len(clean), "held": len(rows) - len(clean), "reasons": dict(reasons),
            "approved": approved,
            "held_ids": [r.staged_id for r, ok, _ in verdicts if not ok]}


def sample(dsn: str, n: int = 10, seed: int | None = None) -> list[dict]:
    """A random sample of auto-approved facts, to spot-check how accurate the rules are."""
    import psycopg

    with psycopg.connect(dsn) as conn:
        rows = conn.execute(
            """SELECT s.staged_id, s.fact_id, s.value_text, s.evidence, s.source_url
               FROM c2.staged_facts s JOIN c2.review_log l ON l.staged_id = s.staged_id
               WHERE l.reviewer = %s AND l.decision = 'approved'""", (AUTO,)).fetchall()
    rng = random.Random(seed)
    picked = rng.sample(rows, min(n, len(rows)))
    return [{"id": a, "fact_id": b, "value": c, "quote": d, "url": e} for a, b, c, d, e in picked]
