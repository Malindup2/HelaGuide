"""
Module A: grounding. Turn one feedback message into the exact fact (and fact VERSION) it is about.

Structured path : the message already carries a fact_id. We check the fact exists and pick the
                  version that was valid when the citizen visited.
Free-text path  : we must FIND the fact. Two stages, each easy to explain:
    Stage 1  which SERVICE?   service hint from C1  >  text match  >  the session's last service  >  ask
    Stage 2  which FACT of that service?  a weighted score of
                 embedding similarity (the pretrained model)           w_e
                 does the kind of fact match (fee / document / ...)    w_p
                 does it match the variant (one day / minor / lost ..) w_q
                 is the stored value quoted back at us                 w_v
Decisions: grounded / clarification_needed (ask the citizen) / no_matching_fact (not in the graph).
Everything the decision used is kept in `trace`, so the demo can print the top candidates.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from app.core.catalog import ServiceCatalog
from app.core.config import C3Settings
from app.core.embeddings import Embedder
from app.core.lexicon import detect_predicate, qualifier_hits
from app.core.repo import Repo
from app.core.util import numbers_in
from app.models.internal import FactVersion


LIST_PREDICATES = {"document", "prerequisite"}

# Words that say nothing about WHICH document is meant. Everything else in a document's name is "distinctive":
# "Birth certificate" -> {birth}; "ICAO standard photograph from a registered studio" -> {icao, standard, photograph,
# registered, studio}. Compared by their first five letters so "photo" matches "photographs".
_GENERIC = {"the", "and", "for", "from", "with", "that", "this", "your", "you", "they", "them", "their", "have", "has",
            "had", "was", "were", "are", "not", "did", "does", "any", "also", "asked", "ask", "asking", "need", "needed",
            "required", "wanted", "want", "document", "documents", "form", "copy", "certificate", "certificates",
            "certified", "letter", "report", "reports", "card", "office", "guide", "mention", "which", "when", "what",
            "get", "got", "bring", "brought", "again", "only", "both", "each", "other", "some", "about", "into", "than"}


def distinctive_words(text: str) -> set[str]:
    out = set()
    for w in re.findall(r"[a-z]{3,}", (text or "").lower()):
        if w in _GENERIC:
            continue
        stem = w[:-1] if w.endswith("s") and len(w) > 3 else w
        out.add(stem[:5])
    return out


def document_is_listed(phrase_sim: float, shares_word: bool, tau_miss: float, tau_sure: float) -> bool:
    """Is the document the citizen mentions one of the listed documents?
    Yes if the similarity is high enough to trust on its own, or if it clears the floor AND they share a distinctive word."""
    return phrase_sim >= tau_sure or (shares_word and phrase_sim >= tau_miss)


def required_score(tau_f: float, relief: float, only_fact_of_its_kind: bool) -> float:
    """The fact score needed to ground. Lower when the service has only one fact of the kind being discussed."""
    return tau_f - (relief if only_fact_of_its_kind else 0.0)


@dataclass
class GroundingResult:
    state: str                              # grounded | clarification_needed | no_matching_fact
    fact_id: str | None = None
    valid_from: datetime | None = None
    service_id: str | None = None
    predicate: str | None = None
    service_source: str | None = None       # hint | text | session | structured
    reason: str | None = None
    trace: dict = field(default_factory=dict)


class GroundingEngine:
    def __init__(self, repo: Repo, catalog: ServiceCatalog, embedder: Embedder, settings: C3Settings):
        self.repo, self.catalog, self.embedder, self.s = repo, catalog, embedder, settings
        self.refresh()

    # ------------------------------------------------------------------ index
    def refresh(self) -> None:
        """Load the current facts and the service profiles into memory (called after every sync)."""
        self.facts: list[FactVersion] = self.repo.list_current_facts()
        self.by_service: dict[str, list[FactVersion]] = {}
        for f in self.facts:
            self.by_service.setdefault(f.service_id, []).append(f)
        services = [s for s in self.catalog.all() if s.service_id in self.by_service]
        self.services = services
        self.service_emb = self.embedder.encode([s.profile_text for s in services]) if services else np.zeros((0, 1))
        # For documents and prerequisites we also keep the embedding of the VALUE ALONE ("Birth certificate"),
        # without the service name that every description starts with. See the "not in the graph" check below.
        self.value_emb: dict[str, np.ndarray] = {}
        listed = [f for f in self.facts if f.predicate in LIST_PREDICATES]
        if listed:
            for f, v in zip(listed, self.embedder.encode([f.value_text for f in listed])):
                self.value_emb[f.fact_id] = v

    # ------------------------------------------------------------- structured
    def ground_structured(self, fact_id: str, when: datetime) -> GroundingResult:
        v = self.repo.version_at(fact_id, when)
        if v is None:
            return GroundingResult("no_matching_fact", reason="unknown_fact_id", trace={"fact_id": fact_id})
        return GroundingResult("grounded", v.fact_id, v.valid_from, v.service_id, v.predicate, "structured",
                               trace={"method": "structured: fact_id supplied by the interface"})

    # -------------------------------------------------------------- free text
    def _resolve_service(self, text_en: str, raw_text: str, hint: str | None, session_service: str | None,
                         context_services: list[str] | None = None):
        """Which service? Order: hint from C1, a single clear alias, the best text match, the screen context, the session."""
        trace: dict = {}
        if hint and hint in self.by_service:
            trace["service_candidates"] = [{"service_id": hint, "score": 1.0, "note": "hint from C1"}]
            return hint, "hint", trace
        q = self.embedder.encode([text_en])[0]
        rows = []
        for svc, emb in zip(self.services, self.service_emb):
            cos = float(np.dot(q, emb))
            alias = svc.alias_hit(raw_text, text_en)
            score = self.s.w_service_cos * cos + self.s.w_service_alias * (1.0 if alias else 0.0)
            rows.append({"service_id": svc.service_id, "score": round(score, 4), "cos": round(cos, 4),
                         "alias_hit": bool(alias)})
        rows.sort(key=lambda r: -r["score"])
        trace["service_candidates"] = rows[:3]
        hits = [r for r in rows if r["alias_hit"]]
        context = [c for c in (context_services or []) if c in self.by_service]
        if len(hits) == 1:                     # exactly one service is named: that is the service
            trace["note"] = "exactly one service name/alias found in the message"
            return hits[0]["service_id"], "alias", trace
        if len(hits) > 1 and context:          # several are named: prefer the one the citizen was just looking at
            on_screen = [r for r in hits if r["service_id"] in context]
            if len(on_screen) == 1:
                trace["note"] = "several services are named; the one on the citizen's screen was chosen"
                return on_screen[0]["service_id"], "context", trace
        if rows:
            top = rows[0]
            lead = top["score"] - (rows[1]["score"] if len(rows) > 1 else 0.0)
            trace["service_lead"] = round(lead, 4)
            if top["score"] >= self.s.tau_s and lead >= self.s.delta_s:
                return top["service_id"], "text", trace
        if len(context) == 1:                  # the citizen was looking at exactly one service
            trace["note"] = "service taken from the workflow on the citizen's screen"
            return context[0], "context", trace
        if session_service and session_service in self.by_service:
            trace["note"] = "service taken from an earlier message in the same session"
            return session_service, "session", trace
        return None, None, trace

    def _score_facts(self, service_id: str, text_en: str, raw_text: str, predicate: str | None,
                     hard_predicate: bool):
        cands = self.by_service[service_id]
        q = self.embedder.encode([text_en])[0]
        svc = self.catalog.get(service_id)
        quals = [c.qualifier for c in cands if c.qualifier]
        matched = qualifier_hits(f"{text_en} {raw_text}", list(set(quals)))
        nums = set(numbers_in(f"{text_en} {raw_text}"))
        rows = []
        for f in cands:
            cos = float(np.dot(q, f.embedding)) if f.embedding is not None else 0.0
            if predicate is None:
                p = 0.5
            else:
                p = 1.0 if f.predicate == predicate else 0.0
            if not f.qualifier:
                qs = 0.5
            elif matched:
                qs = 1.0 if f.qualifier in matched else 0.0
            else:
                default = (svc.default_qualifiers.get(f.predicate) if svc else None)
                qs = 0.7 if f.qualifier == default else 0.3
            vm = 1.0 if (f.value_num is not None and f.value_num in nums) else 0.0
            score = self.s.w_e * cos + self.s.w_p * p + self.s.w_q * qs + self.s.w_v * vm
            rows.append({"fact_id": f.fact_id, "score": round(score, 4), "cos": round(cos, 4), "pred": p,
                         "qual": qs, "value_quoted": vm, "predicate": f.predicate, "description": f.description})
        rows.sort(key=lambda r: -r["score"])
        return rows

    def ground_text(self, text_en: str | None, raw_text: str, *, service_hint: str | None = None,
                    predicate_hint: str | None = None, session_service: str | None = None,
                    context_services: list[str] | None = None, when: datetime) -> GroundingResult:
        if not text_en:
            return GroundingResult("clarification_needed", reason="translation_unavailable",
                                   trace={"note": "no English text, so the message could not be compared"})
        service_id, source, trace = self._resolve_service(text_en, raw_text, service_hint, session_service,
                                                          context_services)
        if service_id is None:
            return GroundingResult("clarification_needed", reason="service_unclear", trace=trace)
        svc_info = self.catalog.get(service_id)
        pred_texts = [svc_info.strip_aliases(text_en), svc_info.strip_aliases(raw_text)] if svc_info else [text_en, raw_text]
        detected, pscores = detect_predicate(pred_texts)
        predicate = predicate_hint or detected
        trace.update({"service_id": service_id, "service_source": source, "predicate_detected": detected,
                      "predicate_used": predicate, "predicate_hint": predicate_hint})
        rows = self._score_facts(service_id, text_en, raw_text, predicate, bool(predicate_hint))
        trace["fact_candidates"] = rows[:3]
        if not rows:
            return GroundingResult("no_matching_fact", service_id=service_id, predicate=predicate,
                                   service_source=source, reason="service_has_no_facts", trace=trace)
        top = rows[0]
        second = rows[1]["score"] if len(rows) > 1 else 0.0
        margin = top["score"] - second
        trace.update({"best_score": top["score"], "margin": round(margin, 4),
                      "thresholds": {"tau_f": self.s.tau_f, "delta_f": self.s.delta_f,
                                     "tau_miss_cos": self.s.tau_miss_cos}})
        # "Not in the graph" only makes sense for list-type facts: a document or prerequisite that is not
        # listed. A fee or a processing time is never "missing": the service either has one or it does not.
        #
        # The check looks at the DOCUMENT PHRASE only: the message without the service's own name, against the
        # document alone. (Every description starts with the service name and so does the citizen's message, so
        # comparing the whole texts makes every document of the service look similar to every complaint about it.)
        #
        # Similarity alone cannot tell "medical certificate" from "birth certificate": both say "certificate".
        # So a document counts as present if
        #     the similarity is high enough to trust on its own            (tau_doc_sure), or
        #     the similarity is at least tau_miss_cos AND the message shares a DISTINCTIVE word with the document.
        if predicate in LIST_PREDICATES:
            phrase = svc_info.strip_aliases(text_en) if svc_info else text_en
            if len(phrase.split()) < 3:
                phrase = text_en
            vec = self.value_emb.get(top["fact_id"])
            phrase_sim = float(np.dot(self.embedder.encode([phrase])[0], vec)) if vec is not None else top["cos"]
            top_fact = next((f for f in self.by_service[service_id] if f.fact_id == top["fact_id"]), None)
            shared = sorted(distinctive_words(phrase) & distinctive_words(top_fact.value_text)) if top_fact else []
            trace.update({"phrase_text": phrase, "phrase_similarity": round(phrase_sim, 4),
                          "shares_distinctive_word": bool(shared), "shared_words": shared})
            present = document_is_listed(phrase_sim, bool(shared), self.s.tau_miss_cos, self.s.tau_doc_sure)
            if not present:
                return GroundingResult("no_matching_fact", service_id=service_id, predicate=predicate,
                                       service_source=source, reason="nothing_in_graph_resembles_this", trace=trace)
        # If the service has exactly ONE fact of the kind being discussed (one fee, one processing time...) there is
        # nothing to choose between, so the absolute score may be lower. The margin rule still applies.
        competing = [r for r in rows if r["pred"] == 1.0]
        unique = predicate is not None and len(competing) == 1 and competing[0] is top
        need = required_score(self.s.tau_f, self.s.tau_f_unique_relief, unique)
        trace["only_fact_of_its_kind"] = unique
        trace["needed_score"] = round(need, 4)
        if top["score"] >= need and margin >= self.s.delta_f:
            v = self.repo.version_at(top["fact_id"], when)
            if v is None:
                return GroundingResult("no_matching_fact", service_id=service_id, reason="fact_not_registered", trace=trace)
            return GroundingResult("grounded", v.fact_id, v.valid_from, service_id, v.predicate, source, trace=trace)
        return GroundingResult("clarification_needed", service_id=service_id, predicate=predicate,
                               service_source=source, reason="ambiguous_fact", trace=trace)
