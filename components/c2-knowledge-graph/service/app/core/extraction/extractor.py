"""Page text to staged facts.

One call per page: the model reads the cleaned Markdown and returns what the page states
about ONE service (the seed says which). Every item must quote the page; an item whose
quote is not found on the page is dropped and counted, not stored. Nothing here writes to the
graph: facts come out as 'pending' and wait for review.

The model supplies wording. Identity does not come from it: names, variants and fee labels
are canonicalised in vocabulary.py, so the same position gets the same fact_id on every run.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from pydantic import ValidationError

from app.core.acquisition.discover import strip_menus
from app.core.extraction.llm import LLM, LLMError
from app.core.extraction.ontology import (
    SERVICE_ID,
    PageExtraction,
    StagedFact,
    is_grounded,
    parse_amount,
)
from app.core.extraction.vocabulary import (
    canonical_document,
    canonical_qualifier,
    canonical_variant,
)

# Characters of page text sent to the model. Pages seen so far are about 18k including the
# menu; a page far beyond this is truncated and flagged rather than silently half-read.
MAX_PAGE_CHARS = 30_000

SYSTEM = """You extract facts about ONE Sri Lankan government service from a web page.

Return a single JSON object with exactly these keys:
  agency            string or null
  agency_evidence   string or null
  fees              list of {qualifier, variant, kind, amount_text, evidence}
  documents         list of {name, variant, condition, evidence}
  prerequisites     list of {description, variant, provided_by, evidence}
  processing_times  list of {qualifier, variant, text, evidence}
  eligibility       string or null
  eligibility_evidence string or null

Rules:
- Copy fees, durations and document names EXACTLY as written. Do not convert, round,
  normalise or translate them.
- evidence is a sentence or line copied word for word from the page. If you cannot quote the
  page for an item, leave the item out.
- If a value is not stated on the page, return null or an empty list. Never infer or guess.
- One page often covers several cases of the same service (for example ordinary, minor,
  lost, replacement, diplomatic or official passports). Set variant to the case an item
  belongs to, using the same label every time for the same case. Use null only when the item
  applies to every case.
- qualifier is a short label for which amount this is, such as normal or urgent.
- kind is "surcharge" when the page says an amount is added to another fee ("in addition
  to"), otherwise "base".
- prerequisites are services or steps that must be COMPLETED FIRST, before this one can
  begin (for example "obtain a police report before applying"). Required documents are NOT
  prerequisites; put them in documents.
- If the page does not describe the requested service, return empty lists.
"""


@dataclass
class ExtractionResult:
    facts: list[StagedFact] = field(default_factory=list)
    dropped: list[dict] = field(default_factory=list)  # items whose quote was not on the page
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = ""
    truncated: bool = False
    error: str = ""


def _join(*parts: str | None) -> str:
    return "_".join(p for p in parts if p)


def build_facts(data: PageExtraction, page_text: str, service_id: str, source_url: str,
                retrieved_at: str) -> tuple[list[StagedFact], list[dict]]:
    facts: list[StagedFact] = []
    dropped: list[dict] = []

    def make(predicate, qualifier, value, evidence, **extra) -> StagedFact:
        fid = ":".join([service_id, predicate] + ([qualifier] if qualifier else []))
        return StagedFact(fact_id=fid, service_id=service_id, predicate=predicate,
                          qualifier=qualifier, value_text=value, source_url=source_url,
                          retrieved_at=retrieved_at, evidence=evidence, **extra)

    def grounded(fact_id: str, value: str, evidence: str) -> bool:
        if is_grounded(evidence, page_text):
            return True
        dropped.append({"fact_id": fact_id, "value": value, "reason": "evidence is not on the page"})
        return False

    if data.agency and grounded(f"{service_id}:agency", data.agency, data.agency_evidence or ""):
        facts.append(make("agency", None, data.agency, data.agency_evidence))

    for f in data.fees:
        num, unit = parse_amount(f.amount_text)
        variant = canonical_variant(f.variant)
        q = _join(variant, canonical_qualifier(f.qualifier))
        detail = {"kind": "surcharge" if f.kind == "surcharge" else "base"}
        if variant:
            detail["variant"] = variant
        if grounded(f"{service_id}:fee:{q}", f.amount_text, f.evidence):
            facts.append(make("fee", q, f.amount_text, f.evidence, value_num=num, unit=unit,
                              detail=detail))

    for t in data.processing_times:
        variant = canonical_variant(t.variant)
        q = _join(variant, canonical_qualifier(t.qualifier))
        if grounded(f"{service_id}:processing_time:{q}", t.text, t.evidence):
            facts.append(make("processing_time", q, t.text, t.evidence,
                              detail={"variant": variant} if variant else {}))

    # A document named on several cases of the page is ONE fact that lists the cases it
    # applies to, so the same paper is not stored once per case.
    documents: dict[str, StagedFact] = {}
    for d in data.documents:
        canon = canonical_document(d.name)
        fid = f"{service_id}:document:{canon.key}"
        if not grounded(fid, d.name, d.evidence):
            continue
        variant = canonical_variant(d.variant)
        fact = documents.get(canon.key)
        if fact is None:
            fact = make("document", canon.key, d.name, d.evidence,
                        detail={"applies_to": [], "conditions": []})
            if canon.service_id:
                fact.detail["service_id"] = canon.service_id
            documents[canon.key] = fact
        applies = fact.detail["applies_to"]
        if variant and variant not in applies:
            applies.append(variant)
        if d.condition and d.condition not in fact.detail["conditions"]:
            fact.detail["conditions"].append(d.condition)
        if not variant:
            fact.detail["applies_to_all"] = True
    facts.extend(documents.values())

    # Prerequisites: stated by the model, plus any document that is itself a service
    # (derived deterministically; this is what links svc:passport to svc:nic).
    prereqs: dict[str, StagedFact] = {}
    for p in data.prerequisites:
        canon = canonical_document(p.description)
        fid = f"{service_id}:prerequisite:{canon.key}"
        if not grounded(fid, p.description, p.evidence):
            continue
        detail = {"origin": "stated"}
        if canon.service_id:
            detail["requires_service"] = canon.service_id
        if p.provided_by:
            detail["provided_by"] = p.provided_by
        if p.variant:
            detail["applies_to"] = [canonical_variant(p.variant)]
        prereqs.setdefault(canon.key, make("prerequisite", canon.key, p.description,
                                           p.evidence, detail=detail))
    for key, doc in documents.items():
        required = doc.detail.get("service_id")
        if required and required != service_id and key not in prereqs:
            prereqs[key] = make("prerequisite", key, required, doc.evidence, detail={
                "origin": "derived_from_document", "requires_service": required,
                "document": doc.value_text, "applies_to": list(doc.detail["applies_to"]),
                "applies_to_all": doc.detail.get("applies_to_all", False)})
    facts.extend(prereqs.values())

    if data.eligibility and grounded(f"{service_id}:eligibility", data.eligibility,
                                     data.eligibility_evidence or ""):
        facts.append(make("eligibility", None, data.eligibility, data.eligibility_evidence))

    unique: dict[str, StagedFact] = {}
    for f in facts:  # one fact per position: the first statement on the page wins
        first = unique.setdefault(f.fact_id, f)
        if first is not f and first.value_text != f.value_text:
            # The page states this position twice with different values. Kept visible,
            # never silently resolved.
            dropped.append({"fact_id": f.fact_id, "value": f.value_text,
                            "reason": f"position already holds {first.value_text!r}"})
    return list(unique.values()), dropped


def extract_page(text: str, *, service_id: str, agency: str, source_url: str,
                 retrieved_at: str, llm: LLM) -> ExtractionResult:
    if not SERVICE_ID.match(service_id):
        raise ValueError(f"service id must look like svc:passport, got {service_id!r}")

    body = strip_menus(text)
    result = ExtractionResult()
    if len(body) > MAX_PAGE_CHARS:
        body, result.truncated = body[:MAX_PAGE_CHARS], True

    user = (f"Service: {service_id}\nAgency (from the seed list): {agency}\n"
            f"Page: {source_url}\n\n--- PAGE START ---\n{body}\n--- PAGE END ---")
    try:
        reply = llm.complete(SYSTEM, user)
    except LLMError as e:
        result.error = f"llm: {e}"
        return result
    result.prompt_tokens, result.completion_tokens = reply.prompt_tokens, reply.completion_tokens
    result.model = reply.model

    try:
        data = PageExtraction.model_validate(json.loads(reply.text))
    except (json.JSONDecodeError, ValidationError) as e:
        result.error = f"model output did not match the schema: {type(e).__name__}"
        return result

    result.facts, result.dropped = build_facts(data, body, service_id, source_url, retrieved_at)
    return result
