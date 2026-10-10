"""Page text to staged facts.

One call per page: the model reads the cleaned Markdown and returns what the page states
about ONE service (the seed says which). Every item must quote the page; an item whose
quote is not on the page is dropped and counted, not stored. Nothing here writes to the
graph: facts come out as 'pending' and wait for review.
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
    slug,
)

# Characters of page text sent to the model. Pages seen so far are about 18k including the
# menu; a page far beyond this is truncated and flagged rather than silently half-read.
MAX_PAGE_CHARS = 30_000

SYSTEM = """You extract facts about ONE Sri Lankan government service from a web page.

Return a single JSON object with exactly these keys:
  agency            string or null
  agency_evidence   string or null
  fees              list of {qualifier, amount_text, evidence}
  documents         list of {name, condition, evidence}
  prerequisites     list of {description, provided_by, evidence}
  processing_times  list of {qualifier, text, evidence}
  eligibility       string or null
  eligibility_evidence string or null

Rules:
- Copy fees, durations and document names EXACTLY as written. Do not convert, round,
  normalise or translate them.
- evidence is a sentence or line copied word for word from the page. If you cannot quote the
  page for an item, leave the item out.
- If a value is not stated on the page, return null or an empty list. Never infer or guess.
- qualifier is a short snake_case label for which variant this is, such as normal, urgent,
  minor_normal, replacement. Use the page's own distinctions.
- prerequisites are services or steps that must be COMPLETED FIRST, before this one can
  begin. Required documents are NOT prerequisites; put them in documents.
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


def _fact(service_id, predicate, qualifier, value, evidence, source_url, retrieved_at, **extra):
    parts = [service_id, predicate] + ([qualifier] if qualifier else [])
    return StagedFact(fact_id=":".join(parts), service_id=service_id, predicate=predicate,
                      qualifier=qualifier, value_text=value, source_url=source_url,
                      retrieved_at=retrieved_at, evidence=evidence, **extra)


def build_facts(data: PageExtraction, page_text: str, service_id: str, source_url: str,
                retrieved_at: str) -> tuple[list[StagedFact], list[dict]]:
    facts: list[StagedFact] = []
    dropped: list[dict] = []

    def keep(fact: StagedFact, evidence: str) -> None:
        if not is_grounded(evidence, page_text):
            dropped.append({"fact_id": fact.fact_id, "value": fact.value_text,
                            "reason": "evidence is not on the page"})
        else:
            facts.append(fact)

    args = (source_url, retrieved_at)
    if data.agency:
        keep(_fact(service_id, "agency", None, data.agency, data.agency_evidence or "", *args),
             data.agency_evidence or "")
    for f in data.fees:
        num, unit = parse_amount(f.amount_text)
        q = slug(f.qualifier) or "standard"
        keep(_fact(service_id, "fee", q, f.amount_text, f.evidence, *args, value_num=num, unit=unit),
             f.evidence)
    for d in data.documents:
        detail = {"condition": d.condition} if d.condition else {}
        keep(_fact(service_id, "document", slug(d.name), d.name, d.evidence, *args, detail=detail),
             d.evidence)
    for p in data.prerequisites:
        detail = {"provided_by": p.provided_by} if p.provided_by else {}
        keep(_fact(service_id, "prerequisite", slug(p.description), p.description, p.evidence,
                   *args, detail=detail), p.evidence)
    for t in data.processing_times:
        keep(_fact(service_id, "processing_time", slug(t.qualifier) or "standard", t.text,
                   t.evidence, *args), t.evidence)
    if data.eligibility:
        keep(_fact(service_id, "eligibility", None, data.eligibility,
                   data.eligibility_evidence or "", *args), data.eligibility_evidence or "")

    unique: dict[str, StagedFact] = {}
    for f in facts:  # one fact per position: the first statement on the page wins
        unique.setdefault(f.fact_id, f)
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
