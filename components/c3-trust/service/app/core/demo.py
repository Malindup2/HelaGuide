"""
The brain of the citizen console (python -m app.cli.serve, page at /ui).

A tiny stand-in for what the integrated system will do: show a workflow made of facts (C2's plan, rendered by C4),
take a citizen's feedback, and show the workflow again. Everything real happens in the pipeline; this module only
prepares the screen content and the pre-written sample messages.

Why sample messages and not free typing: the demo must never depend on a live translation. Every Sinhala and Singlish
sample has a saved, reviewed translation in normalised_cache.json.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone

from app.core.lexicon import has_sinhala
from app.core.pipeline import ProcessResult, get_pipeline
from app.core.util import as_utc, fmt_value, iso, parse_dt
from app.models.internal import DemoFeedbackRequest

INITIAL_CLOCK = datetime(2026, 10, 19, 9, 0, tzinfo=timezone.utc)
UPDATE_CLOCK = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)      # the official page changes on 28 Oct 2026
TYPED_BASE = datetime(2026, 10, 26, 9, 0, tzinfo=timezone.utc)         # typed text is dated after the whole sample story

REASONS = {
    "service_unclear": "I could not tell which service this is about, so I changed nothing.",
    "ambiguous_fact": "Two facts looked equally likely, so I changed nothing rather than guess.",
    "translation_unavailable": "This message has no saved translation in the demo, so I changed nothing.",
    "nothing_in_graph_resembles_this": "Nothing in the guide matches this (for example a document that is not listed). "
                                       "Nothing was changed; the message is kept for review.",
    "service_has_no_facts": "The guide has no facts for this service yet. Nothing was changed.",
    "fact_not_registered": "That fact is not registered yet. Nothing was changed.",
}


def display_value(fv) -> str:
    if fv is None:
        return "-"
    if fv.predicate == "fee":
        return fmt_value(fv.value_num if fv.value_num is not None else fv.value_text, fv.unit)
    if fv.predicate == "processing_time" and fv.value_num is not None:
        n = int(fv.value_num) if float(fv.value_num).is_integer() else fv.value_num
        return f"{n} {fv.unit or 'days'}"
    return fv.value_text


class DemoService:
    def __init__(self, pipe):
        self.pipe = pipe
        self.lock = threading.RLock()
        data = pipe.s.data_dir
        self.spec = json.loads((data / "demo_workflow.json").read_text(encoding="utf-8"))
        msgs = json.loads((data / "feedback_freetext.json").read_text(encoding="utf-8"))["messages"]
        self.messages = {m["message_id"]: m for m in msgs}
        self.labels: dict[str, str] = {}
        for st in self.spec["steps"]:
            for f in st["facts"]:
                self.labels[f["fact_id"]] = f"{st['name']} · {f['label']}"
        self._reset_counters()

    def _reset_counters(self) -> None:
        self.clock = INITIAL_CLOCK
        self.counter = 0
        self.context: list[str] = []

    def label_for(self, fact_id: str | None) -> str:
        if not fact_id:
            return "-"
        if fact_id in self.labels:
            return self.labels[fact_id]
        v = self.pipe.repo.current_version(fact_id)
        return v.description if v else fact_id

    # ------------------------------------------------------------ the screen
    def _fact_state(self, fact_id: str, label: str) -> dict:
        v = self.pipe.repo.current_version(fact_id)
        e = self.pipe.exposure.explain(fact_id)
        return {"fact_id": fact_id, "label": label, "value": display_value(v), "confidence": e["confidence"],
                "confidence_pct": e["confidence_pct"], "warning_code": e["warning_code"],
                "report_count": e["report_count"], "verified_by_source": bool(e.get("verified_by_source")),
                "version_from": e.get("version_valid_from")}

    def workflow(self) -> dict:
        with self.lock:
            steps = [{"order": st["order"], "service_id": st["service_id"], "name": st["name"], "agency": st["agency"],
                      "facts": [self._fact_state(f["fact_id"], f["label"]) for f in st["facts"]]}
                     for st in self.spec["steps"]]
            self.context = [st["service_id"] for st in self.spec["steps"]]     # what the citizen is looking at now
            return {"title": self.spec["request"]["title"], "request": self.spec["request"]["label"], "steps": steps,
                    "brand": self.spec["brand"]}

    def personas(self) -> list[dict]:
        out = []
        for pid, note in self.spec["personas"].items():
            r = self.pipe.repo.get_reporter(pid)
            if r is None:
                continue
            out.append({"id": pid, "note": note, "a": r.a, "b": r.b, "reputation": round((r.a + 1) / (r.a + r.b + 2), 2),
                        "since": as_utc(r.created_at).date().isoformat()})
        return out

    def samples(self) -> dict:
        out = []
        for s in self.spec["samples"]:
            m = self.messages[s["id"]]
            out.append({"id": s["id"], "group": s["group"], "note": s["note"], "text": m["raw_text"],
                        "language": m["language"], "default_persona": m["session_id"],
                        "visit_date": m["entities"].get("visit_date")})
        return {"groups": self.spec["groups"], "samples": out}

    # ------------------------------------------------------------- feedback
    def submit(self, req: DemoFeedbackRequest) -> dict:
        with self.lock:
            if req.sample_id is None:                                         # the panel's own English text
                return self._submit_typed(req)
            m = self.messages[req.sample_id]                                  # KeyError -> 404 in the route
            if self.pipe.repo.get_reporter(req.persona_id) is None:
                raise KeyError(req.persona_id)
            ts = max(parse_dt(m["timestamp"]), self.clock + timedelta(minutes=1))   # time only moves forward
            self.clock = ts
            self.counter += 1
            entities = dict(m["entities"])
            if req.visit_date:
                entities["visit_date"] = req.visit_date.isoformat()
            entities["context_services"] = self.context or None
            payload = {"message_id": f"ui-{self.counter:04d}", "session_id": req.persona_id, "timestamp": iso(ts),
                       "language": m["language"], "raw_text": m["raw_text"], "text_en": None,
                       "intent": "feedback_discrepancy", "entities": entities}
            res = self.pipe.process_freetext(payload)
            return self._present(res, m, req)

    def _submit_typed(self, req: DemoFeedbackRequest) -> dict:
        """English text typed at the demo. It goes through exactly the same pipeline as a sample message:
        grounding, trust, independence, confidence. No translation is needed, so nothing depends on the internet."""
        text = " ".join((req.text or "").split())
        if len(text) < 8:
            raise ValueError("Write a little more: name the service and what it was about.")
        if has_sinhala(text):
            raise ValueError("Please write in English. Live translation is switched off in this demo.")
        if self.pipe.repo.get_reporter(req.persona_id) is None:
            raise KeyError(req.persona_id)
        ts = max(TYPED_BASE, self.clock + timedelta(minutes=1))                # time only moves forward
        self.clock = ts
        self.counter += 1
        visit = (ts.date() - timedelta(days=req.visit_days_ago)).isoformat() if req.visit_days_ago is not None else None
        payload = {"message_id": f"ui-{self.counter:04d}", "session_id": req.persona_id, "timestamp": iso(ts),
                   "language": "en", "raw_text": text, "text_en": None, "intent": "feedback_discrepancy",
                   "entities": {"service_id": None, "predicate_hint": None, "mentioned_value": None, "visit_date": visit,
                                "reporter_token": None, "context_services": self.context or None}}
        res = self.pipe.process_freetext(payload)
        return self._present(res, {"raw_text": text, "language": "en"}, req)

    def _present(self, res: ProcessResult, m: dict, req: DemoFeedbackRequest) -> dict:
        out = res.to_dict()
        g = res.grounding or {}
        cands = [{"fact_id": c["fact_id"], "label": self.label_for(c["fact_id"]), "score": c["score"]}
                 for c in (g.get("fact_candidates") or [])]
        if res.state == "grounded":
            note = f"Matched to {self.label_for(res.fact_id)}."
        else:
            note = REASONS.get(res.reason or "", "I could not use this message, so I changed nothing.")
        out["ui"] = {"message_text": m["raw_text"], "language": m["language"], "persona_id": req.persona_id,
                     "fact_label": self.label_for(res.fact_id), "fact_value": display_value(
                         self.pipe.repo.current_version(res.fact_id)) if res.fact_id else None,
                     "note": note, "candidates": cands,
                     "service_candidates": [{"service_id": c["service_id"], "score": c["score"]}
                                            for c in (g.get("service_candidates") or [])]}
        return out

    # --------------------------------------------------- the official source
    def official_update(self) -> dict:
        with self.lock:
            repo = self.pipe.repo
            before = {r.reporter_id: (r.a, r.b) for r in repo.all_reporters()}
            self.pipe.source.publish_updates(self.pipe.s.data_dir / "c2_facts_updates.json")
            results = self.pipe.sync_facts()
            self.clock = max(self.clock, UPDATE_CLOCK)
            changes = []
            for res in results:
                if not res.new_version:
                    continue
                versions = repo.versions(res.fact_id)
                changes.append({
                    "fact_id": res.fact_id, "label": self.label_for(res.fact_id),
                    "old_value": display_value(versions[-2]), "new_value": display_value(versions[-1]),
                    "confidence_pct": round(100 * (res.initial_confidence or 0)),
                    "verdicts": [{"report_id": v.report_id, "citizen": v.reporter_id, "claimed": v.claimed,
                                  "outcome": v.outcome, "a": round(v.da, 2), "b": round(v.db, 2)} for v in res.verdicts]})
            rep = []
            for r in repo.all_reporters():
                a0, b0 = before.get(r.reporter_id, (0, 0))
                if (r.a, r.b) != (a0, b0):
                    rep.append({"citizen": r.reporter_id, "before": round((a0 + 1) / (a0 + b0 + 2), 2),
                                "after": round((r.a + 1) / (r.a + r.b + 2), 2)})
            return {"changes": changes, "reputation": rep}

    def reset(self) -> dict:
        with self.lock:
            self.pipe.reset_demo_state()
            self._reset_counters()
            return {"ok": True}

    # ------------------------------------------------------------ the details
    def audit(self, fact_id: str) -> dict:
        repo = self.pipe.repo
        versions = repo.versions(fact_id)
        if not versions:
            raise KeyError(fact_id)
        vs = []
        for v in versions:
            rec = repo.get_confidence(fact_id, v.valid_from)
            vs.append({"from": iso(v.valid_from), "to": iso(v.valid_to), "value": display_value(v),
                       "confidence_pct": round(100 * rec.confidence, 1), "status": rec.status,
                       "reports": [{"message_id": r.message_id, "citizen": r.reporter_id, "kind": r.report_kind,
                                    "claim": r.claimed_value_raw, "trust": round(r.trust_t, 3),
                                    "independence": round(r.indep_i, 2), "state": r.state, "text": r.text_en or r.raw_text}
                                   for r in repo.reports_for(fact_id, v.valid_from)]})
        audit = [{"at": iso(r["at"]), "before": r["old"], "after": r["new"], "reason": r["reason"]}
                 for r in repo.audit_rows(fact_id)]
        return {"fact_id": fact_id, "label": self.label_for(fact_id), "versions": vs, "audit": audit}


_demo: DemoService | None = None


def get_demo() -> DemoService:
    global _demo
    pipe = get_pipeline()
    if _demo is None or _demo.pipe is not pipe:
        _demo = DemoService(pipe)
    return _demo
