"""
Module R: the fact registry and C3's ownership of confidence.

C2 owns fact CREATION. C3 owns each fact's CONFIDENCE and status (README ownership rule).
So whenever C3 learns about a fact version it creates that version's confidence record here.

A fact_id survives a value change (it comes from graph position, never from the value), so a
fact VERSION is identified by (fact_id, valid_from). A new version starts with fresh confidence
and the citizen reports made about the old version receive a verdict (Algorithm 0b).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlparse

from app.core.catalog import ServiceCatalog
from app.core.config import C3Settings
from app.core.embeddings import Embedder
from app.core.repo import Repo
from app.core.util import as_utc, parse_dt, to_number
from app.models.internal import ConfidenceRecord, FactVersion

log = logging.getLogger(__name__)


@dataclass
class Verdict:
    report_id: str
    reporter_id: str
    claimed: str | None
    outcome: str            # verified_by_source | contradicted_by_source | superseded
    da: float = 0.0
    db: float = 0.0


@dataclass
class RegisterResult:
    fact_id: str
    created: bool = False
    new_version: bool = False
    verdicts: list[Verdict] = field(default_factory=list)
    initial_confidence: float | None = None


def initial_confidence(settings: C3Settings, connection_unverified: bool) -> float:
    """Algorithm 0a."""
    c0 = settings.c_base
    if connection_unverified:
        c0 *= settings.phi_unv
    return c0


def values_match(claimed_num: float | None, claimed_key: str, new_value_num: float | None, new_value_text: str) -> bool:
    if claimed_num is not None and new_value_num is not None:
        return abs(claimed_num - new_value_num) < 1e-9
    return bool(claimed_key) and claimed_key != "unspecified" and \
        claimed_key.replace(" ", "") == (new_value_text or "").lower().replace(" ", "")


class Registry:
    def __init__(self, repo: Repo, embedder: Embedder, catalog: ServiceCatalog, settings: C3Settings):
        self.repo, self.embedder, self.catalog, self.settings = repo, embedder, catalog, settings

    # ------------------------------------------------------------------ build
    def _to_version(self, fact: dict) -> FactVersion:
        value = fact["value"]
        host = urlparse(fact.get("source_url") or "").hostname or ""
        qualifier = fact["fact_id"].split(":")[3] if fact["fact_id"].count(":") >= 3 else None
        desc = self.catalog.describe(fact["service_id"], fact["predicate"], qualifier, value, fact.get("unit"))
        return FactVersion(
            fact_id=fact["fact_id"], service_id=fact["service_id"], predicate=fact["predicate"],
            qualifier=qualifier, value_text=str(value),
            value_num=to_number(value) if fact["predicate"] in ("fee", "processing_time") else None,
            unit=fact.get("unit"), description=desc, source_url=fact.get("source_url"),
            retrieved_at=parse_dt(fact["retrieved_at"]) if fact.get("retrieved_at") else None,
            valid_from=parse_dt(fact["valid_from"]),
            valid_to=parse_dt(fact["valid_to"]) if fact.get("valid_to") else None,
            connection_unverified=host in set(self.settings.unverified_hosts))

    # --------------------------------------------------------------- register
    def register(self, fact: dict) -> RegisterResult:
        v = self._to_version(fact)
        res = RegisterResult(fact_id=v.fact_id)
        if self.repo.get_version(v.fact_id, v.valid_from):
            return res                                            # already known: nothing to do
        v.embedding = self.embedder.encode([v.description])[0]
        prev = self.repo.current_version(v.fact_id)
        c0 = initial_confidence(self.settings, v.connection_unverified)
        if prev and prev.valid_from < v.valid_from:
            # a NEW VERSION of a fact we already track
            self.repo.close_version(prev.fact_id, prev.valid_from, v.valid_from)
            self.repo.insert_version(v)
            res.new_version = True
            res.verdicts = self._verdicts(prev, v)
            verified = any(x.outcome == "verified_by_source" for x in res.verdicts)
            self.repo.insert_confidence(ConfidenceRecord(
                fact_id=v.fact_id, valid_from=v.valid_from, base_confidence=c0, confidence=c0,
                status="active", drop_events=0, verified_by_source=verified, last_updated=v.valid_from,
                last_reason=f"new version from source (value {prev.value_text} -> {v.value_text}); "
                            f"{len(res.verdicts)} earlier reports judged"))
            self.repo.add_audit(v.fact_id, v.valid_from, None, c0,
                                f"new version: initial confidence {c0:.2f}; value {prev.value_text} -> {v.value_text}",
                                [x.report_id for x in res.verdicts], v.valid_from)
        else:
            self.repo.insert_version(v)
            res.created = True
            self.repo.insert_confidence(ConfidenceRecord(
                fact_id=v.fact_id, valid_from=v.valid_from, base_confidence=c0, confidence=c0, status="active",
                last_updated=v.valid_from, last_reason="initial confidence (Algorithm 0a)"))
            self.repo.add_audit(v.fact_id, v.valid_from, None, c0, "initial confidence (Algorithm 0a)", [], v.valid_from)
        res.initial_confidence = c0
        return res

    def sync(self, source) -> list[RegisterResult]:
        results = [self.register(f) for f in source.list_facts()]
        n_new = sum(r.created for r in results)
        n_ver = sum(r.new_version for r in results)
        log.info("registry sync: %d new facts, %d new versions", n_new, n_ver)
        return results

    # ------------------------------------------------------- Algorithm 0b
    def _verdicts(self, prev: FactVersion, new: FactVersion) -> list[Verdict]:
        """Judge the reports made about the previous version against the new official value."""
        out: list[Verdict] = []
        day = as_utc(new.valid_from).date()
        for r in self.repo.reports_for(prev.fact_id, prev.valid_from, states=["active"]):
            if r.claimed_key == "unspecified" and r.claimed_num is None:
                self.repo.set_report_state(r.report_id, "superseded")
                out.append(Verdict(r.report_id, r.reporter_id, None, "superseded"))
                continue
            if values_match(r.claimed_num, r.claimed_key, new.value_num, new.value_text):
                da, dbad, outcome = self.settings.reward_a * r.indep_i, 0.0, "verified_by_source"
            else:
                da, dbad, outcome = 0.0, self.settings.penalty_b, "contradicted_by_source"
            self.repo.set_report_state(r.report_id, outcome)
            da2, db2 = self.repo.apply_reputation(r.reporter_id, da, dbad, day, self.settings.delta_max)
            out.append(Verdict(r.report_id, r.reporter_id, r.claimed_value_raw, outcome, da2, db2))
        return out
