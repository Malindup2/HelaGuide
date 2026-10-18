"""
The whole PP1 flow for ONE feedback message, in the order the modules run:

   normalise (translate to English)  ->  A grounding  ->  B trust score  ->  D duplicate check
   ->  store the report  ->  C confidence update  ->  G what would be shown

Two entry points feed the same flow:
   process_structured : the contract `feedback` message (C4 -> C3), which already names the fact
   process_freetext   : the message C1 would forward (C3-private proposal), which must be grounded

Both are turned into one `Incoming` object first, so nothing after that step knows which path
a report came from.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, time, timezone
from pathlib import Path

from sqlalchemy.engine import Engine

from app.core import confidence as conf_mod
from app.core import db
from app.core.catalog import ServiceCatalog
from app.core.config import C3Settings
from app.core.dedup import claim_key, claims_disagree, independence
from app.core.embeddings import Embedder, get_embedder
from app.core.exposure import Exposure
from app.core.factsource import FactSource, build_source
from app.core.grounding import GroundingEngine, GroundingResult
from app.core.lexicon import extract_claimed, infer_kind
from app.core.normaliser import Normaliser
from app.core.registry import Registry
from app.core.repo import Repo
from app.core.trust import msrt
from app.core.util import as_utc, parse_dt, text_hash
from app.models.internal import FreeTextFeedback, Incoming, Reporter, ReportRow

log = logging.getLogger(__name__)


@dataclass
class ProcessResult:
    message_id: str
    path: str
    state: str                                  # grounded | clarification_needed | no_matching_fact | duplicate_message
    reporter_id: str | None = None
    report_id: str | None = None
    fact_id: str | None = None
    reason: str | None = None
    text_en: str | None = None
    norm_backend: str | None = None
    kind: str | None = None
    claimed: str | None = None
    grounding: dict = field(default_factory=dict)
    trust: dict = field(default_factory=dict)
    independence: dict = field(default_factory=dict)
    confidence: dict = field(default_factory=dict)
    exposure: dict = field(default_factory=dict)
    claims_disagree: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class Pipeline:
    def __init__(self, settings: C3Settings, engine: Engine, embedder: Embedder | None = None,
                 source: FactSource | None = None, catalog: ServiceCatalog | None = None,
                 normaliser: Normaliser | None = None):
        self.s = settings
        self.engine = engine
        self.repo = Repo(engine)
        self.embedder = embedder or get_embedder(settings)
        self.source = source or build_source(settings)
        self.catalog = catalog or ServiceCatalog(settings.data_dir / "service_aliases.json")
        self.normaliser = normaliser or Normaliser(settings)
        self.registry = Registry(self.repo, self.embedder, self.catalog, settings)
        self.grounding = GroundingEngine(self.repo, self.catalog, self.embedder, settings)
        self.exposure = Exposure(self.repo, settings)

    # ------------------------------------------------------------ set-up ---
    @classmethod
    def build(cls, settings: C3Settings, reset: bool = False) -> "Pipeline":
        engine = db.make_engine(settings.database_url)
        db.reset_db(engine) if reset else db.init_db(engine)
        return cls(settings, engine)

    def load_reporters(self, path: Path | None = None) -> int:
        path = path or (self.s.data_dir / "reporters.json")
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for r in data["reporters"]:
            self.repo.upsert_reporter(Reporter(reporter_id=r["reporter_id"], created_at=parse_dt(r["created_at"]),
                                               a=float(r["a"]), b=float(r["b"])))
        return len(data["reporters"])

    def sync_facts(self):
        results = self.registry.sync(self.source)
        self.grounding.refresh()
        return results

    def reset_demo_state(self) -> None:
        """Back to the clean starting state: C3's own tables recreated, a fresh copy of the mock graph,
        reporters reloaded, every fact registered at its starting confidence."""
        db.reset_db(self.engine)
        self.source = build_source(self.s)
        self.load_reporters()
        self.sync_facts()

    # --------------------------------------------------------- entry points ---
    def process_structured(self, feedback: dict, extras: dict | None = None) -> ProcessResult:
        extras = extras or {}
        inc = Incoming(
            message_id=feedback["feedback_id"], path="structured",
            reporter_id=extras.get("reporter_token") or feedback["session_id"],
            submitted_at=parse_dt(feedback["submitted_at"]), raw_text=feedback["text"],
            fact_id=feedback["fact_id"], claimed_hint=feedback.get("proposed_value"),
            visit_date=_d(extras.get("visit_date")))
        return self.process(inc)

    def process_freetext(self, message: dict) -> ProcessResult:
        m = FreeTextFeedback(**message)
        e = m.entities
        inc = Incoming(
            message_id=m.message_id, path="freetext", reporter_id=e.reporter_token or m.session_id,
            submitted_at=as_utc(m.timestamp), raw_text=m.raw_text, language=m.language, text_en=m.text_en,
            service_hint=e.service_id, predicate_hint=e.predicate_hint, claimed_hint=e.mentioned_value,
            visit_date=e.visit_date, context_services=e.context_services)
        inc.session_id = m.session_id  # type: ignore[attr-defined]
        return self.process(inc)

    # ------------------------------------------------------------ the flow ---
    def process(self, inc: Incoming) -> ProcessResult:
        res = ProcessResult(message_id=inc.message_id, path=inc.path, state="", reporter_id=inc.reporter_id)
        if self.repo.get_report_by_message(inc.message_id) or self.repo.get_unresolved_by_message(inc.message_id):
            res.state = "duplicate_message"
            res.reason = "this message_id was already processed"
            return res
        rid = "r_" + text_hash(inc.message_id)[:8]
        res.report_id = rid
        session_id = getattr(inc, "session_id", inc.reporter_id)

        # 1. normalise: plain English for everything that follows
        norm = self.normaliser.normalise(inc.raw_text, inc.language, inc.text_en)
        res.text_en, res.norm_backend = norm.text_en, norm.backend
        lang = norm.language

        # 2. A: grounding
        when = datetime.combine(inc.visit_date, time(12, 0), tzinfo=timezone.utc) if inc.visit_date else inc.submitted_at
        if inc.fact_id:
            if self.repo.current_version(inc.fact_id) is None:
                self._lazy_register(inc.fact_id)
            g = self.grounding.ground_structured(inc.fact_id, when)
        else:
            g = self.grounding.ground_text(
                norm.text_en, inc.raw_text, service_hint=inc.service_hint, predicate_hint=inc.predicate_hint,
                session_service=self.repo.get_session_service(session_id),
                context_services=inc.context_services, when=when)
        res.grounding = {"state": g.state, "reason": g.reason, "service_id": g.service_id,
                         "service_source": g.service_source, **g.trace}
        if g.service_id:
            self.repo.set_session_service(session_id, g.service_id, inc.submitted_at)
        if g.state != "grounded":
            res.state, res.reason = g.state, g.reason
            self.repo.insert_unresolved(rid, inc.message_id, inc.path, inc.reporter_id, inc.raw_text, norm.text_en,
                                        g.service_id, g.predicate, g.state, g.reason or "", res.grounding,
                                        inc.submitted_at)
            return res
        res.state, res.fact_id = "grounded", g.fact_id
        version = self.repo.get_version(g.fact_id, g.valid_from)          # type: ignore[arg-type]
        stored_num = version.value_num if version else None

        # 3. the claim and the kind of report
        text = norm.text_en or inc.raw_text
        claimed_num, claimed_raw = extract_claimed(text, inc.raw_text, stored_num, inc.claimed_hint)
        kind = infer_kind(text, claimed_num, stored_num)
        if kind == "support" and claimed_num is None and version is not None:
            claimed_num, claimed_raw = stored_num, version.value_text
        res.kind, res.claimed = kind, claimed_raw

        # 4. B: trust score
        reporter = self.repo.ensure_reporter(inc.reporter_id, inc.submitted_at)
        age_days = max(0.0, (inc.submitted_at - reporter.created_at).total_seconds() / 86400)
        gap = (inc.submitted_at.date() - inc.visit_date).days if inc.visit_date else None
        tr = msrt(self.s, reporter.a, reporter.b, age_days, gap, text, inc.raw_text, claimed_num,
                  inc.visit_date is not None)
        res.trust = {"T": round(tr.T, 4), "R": round(tr.R, 4), "S": round(tr.S, 4), "C": round(tr.C, 4),
                     "V": round(tr.V, 4), "v_imputed": tr.v_imputed, "age_days": round(age_days, 1),
                     "a": reporter.a, "b": reporter.b, "features": tr.features,
                     "weights": [round(x, 3) for x in tr.weights]}

        # 5. D: duplicates and independence
        emb = self.embedder.encode([text])[0]
        earlier = [r for r in self.repo.reports_for(g.fact_id, g.valid_from, states=["active"])   # type: ignore[arg-type]
                   if r.submitted_at <= inc.submitted_at]
        I, dup, near = independence(self.s, emb, inc.reporter_id, kind, earlier)
        res.independence = {"I": round(I, 4), "dup_count": dup, "near_duplicates": near}

        # 6. store the report
        row = ReportRow(
            report_id=rid, message_id=inc.message_id, path=inc.path, reporter_id=inc.reporter_id,
            raw_text=inc.raw_text, text_en=norm.text_en, language=lang, fact_id=g.fact_id,                 # type: ignore[arg-type]
            fact_valid_from=g.valid_from, discrepancy_type=g.predicate or "", report_kind=kind,           # type: ignore[arg-type]
            claimed_value_raw=claimed_raw, claimed_num=claimed_num, claimed_key=claim_key(claimed_num, claimed_raw),
            visit_date=inc.visit_date, submitted_at=inc.submitted_at, trust_t=tr.T, sig_r=tr.R, sig_s=tr.S,
            sig_c=tr.C, sig_v=tr.V, v_imputed=tr.v_imputed, dup_count=dup, indep_i=I, state="active",
            embedding=emb, trace=res.grounding)
        self.repo.insert_report(row)

        # 7. C: confidence update (recomputed from all active reports)
        rec, old, ev = conf_mod.recompute(self.repo, self.s, g.fact_id, g.valid_from, inc.submitted_at, row)   # type: ignore[arg-type]
        active = self.repo.reports_for(g.fact_id, g.valid_from, states=["active"])                          # type: ignore[arg-type]
        res.claims_disagree = claims_disagree(self.s, active)
        res.confidence = {"old": round(old, 4), "new": round(rec.confidence, 4), "pct": round(100 * rec.confidence),
                          "status": rec.status, "E_d": round(ev["E_d"], 4), "E_s": round(ev["E_s"], 4),
                          "E": round(ev["E"], 4), "drop_events": rec.drop_events}
        # 8. G: what a citizen would be shown now
        res.exposure = self.exposure.explain(g.fact_id)                                                      # type: ignore[arg-type]
        return res

    def _lazy_register(self, fact_id: str) -> None:
        fact = self.source.get_fact(fact_id)
        if fact:
            self.registry.register(fact)
            self.grounding.refresh()


def _d(v):
    from app.core.util import parse_date
    return parse_date(v)


# ----------------------------------------------------------------- shared instance
_instance: Pipeline | None = None


def get_pipeline() -> Pipeline:
    """The pipeline used by the HTTP routes (real mode). Built on first use."""
    global _instance
    if _instance is None:
        from app.core.config import get_c3_settings
        _instance = Pipeline.build(get_c3_settings())
        if _instance.repo.list_current_facts() == []:
            _instance.sync_facts()
            _instance.load_reporters()
    return _instance


def set_pipeline(p: Pipeline | None) -> None:
    global _instance
    _instance = p
