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
import re
from dataclasses import dataclass, field

from pydantic import ValidationError

from app.core.acquisition.discover import strip_menus
from app.core.extraction.llm import LLM, LLMError
from app.core.extraction.ontology import (
    SERVICE_ID,
    _sentences,
    DocumentItem,
    FeeItem,
    PageExtraction,
    PrerequisiteItem,
    StagedFact,
    TimeItem,
    is_grounded,
    normalise_for_match,
    parse_amount,
    slug,
)
from app.core.extraction.vocabulary import (
    canonical_condition,
    canonical_document,
    canonical_qualifier,
    canonical_variant,
    known_variant,
)

# Characters of page text sent to the model. Pages seen so far are about 18k including the
# menu; a page far beyond this is truncated and flagged rather than silently half-read.
MAX_PAGE_CHARS = 30_000

SYSTEM = """You extract facts about ONE Sri Lankan government service from a web page.

Return a single JSON object with exactly these keys:
  agency            string or null
  agency_evidence   string or null
  fees              list of {qualifier, variant, condition, kind, amount_text, evidence}
  documents         list of {name, variant, condition, evidence}
  prerequisites     list of {description, variant, provided_by, evidence}
  processing_times  list of {qualifier, variant, condition, text, evidence}
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
- qualifier is a short label for which amount this is, such as normal or urgent, or
  one_day for a one-day service.
- For processing_times, text is the duration only ("3 days", "one day", "30 working days"),
  never a sentence; the sentence goes in evidence.
- condition separates amounts that differ only by a validity period or a time window, for
  example "3 years" and "10 years", or "within one year of issue" and "after one year".
  Give every such amount its own item with its own condition; never merge them.
- kind is "surcharge" when the page says an amount is added to another fee ("in addition
  to"), "penalty" for a fine charged for a failure or an offence, otherwise "base". For a
  penalty, put the reason in condition ("failure to obtain within the time limit").
- prerequisites are services or steps that must be COMPLETED FIRST, before this one can
  begin (for example "obtain a police report before applying"). Required documents are NOT
  prerequisites; put them in documents.
- Who must apply, sign or consent (for example "both parents or the legal guardian") is
  eligibility, not a prerequisite.
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
    raw_reply: str = ""  # exactly what the model returned, kept so a fix can re-process it
    sections: list = field(default_factory=list)  # one entry per service found, in sections mode


_MD_LINK = re.compile(r"\[([^\]]{0,160})\]\(\s*([^)\s][^)]*?)\s*\)")
_FORM_FILE = re.compile(r"(?i)\.(pdf|docx?)(\?|#|$)")


def _clean_url(raw: str) -> str:
    """Some agency sites write paths with backslashes and spaces; make it a fetchable URL."""
    from urllib.parse import quote

    url = re.sub(r"(?<!:)/{2,}", "/", raw.strip().replace("\\", "/"))  # "assets\\x" -> "assets/x"
    return quote(url, safe=":/?&=%#+,;@!$'()*~[]-._")


def forms_on_the_line(page_text: str, evidence: str) -> list[dict]:
    """Links to documents (PDF, Word) on the page line the quote came from.

    The model quotes the sentence; the link sits beside it in the saved Markdown. We read the
    link from the page itself, never from the model, so a form's address cannot be invented.
    """
    key = normalise_for_match(_MD_LINK.sub(r"\1", evidence or ""))[:60]
    if len(key) < 12:
        return []
    for line in (page_text or "").splitlines():
        if key in normalise_for_match(_MD_LINK.sub(r"\1", line)):
            out, seen = [], set()
            for label, url in _MD_LINK.findall(line):
                url = _clean_url(url)
                if _FORM_FILE.search(url) and url not in seen:
                    seen.add(url)
                    text = " ".join(label.split()).strip("()[] ")
                    kind = "specimen" if re.search(r"(?i)specimen|sample", text) else "form"
                    out.append({"label": text, "url": url, "kind": kind})
            return out
    return []


_POSTAGE = re.compile(r"(?i)\b(registered post|postage|by post|sending\b.*\bpost)\b")

_LISTS = {"fees": FeeItem, "documents": DocumentItem, "prerequisites": PrerequisiteItem,
          "processing_times": TimeItem}


def parse_extraction(raw) -> tuple[PageExtraction, list[dict]]:
    """Read the model's JSON item by item. A malformed item is dropped and reported; the
    rest of the page is kept. Models that think less make more small slips of this kind."""
    if not isinstance(raw, dict):
        raise ValueError("model output is not a JSON object")
    problems: list[dict] = []
    clean: dict = {}
    for key in ("agency", "agency_evidence", "eligibility", "eligibility_evidence"):
        v = raw.get(key)
        clean[key] = v.strip() if isinstance(v, str) and v.strip() else None
    for key, model in _LISTS.items():
        value = raw.get(key) or []
        if not isinstance(value, list):
            problems.append({"fact_id": key, "value": str(value)[:60],
                             "reason": "expected a list from the model"})
            value = []
        items = []
        for i, item in enumerate(value):
            try:
                items.append(model.model_validate(item))
            except ValidationError as e:
                err = e.errors()[0]
                where = ".".join(str(p) for p in err["loc"])
                problems.append({"fact_id": f"{key}[{i}]", "value": str(item)[:60],
                                 "reason": f"item did not match the schema: {where}: {err['msg']}"})
        clean[key] = items
    return PageExtraction(**clean), problems


def _variant(label: str | None, *fallbacks: str | None) -> str | None:
    """The model's variant, or one the quote itself names. Without this, an item the model
    left unlabelled gets a different fact_id from the same item on another run."""
    found = canonical_variant(label)
    if found:
        return found
    for text in fallbacks:
        found = known_variant(text)
        if found:
            return found
    return None


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
        if not (value or "").strip():
            dropped.append({"fact_id": fact_id, "value": "", "evidence": evidence,
                            "reason": "the page states no value here (the model returned none)"})
            return False
        if is_grounded(evidence, page_text, value):
            return True
        dropped.append({"fact_id": fact_id, "value": value, "evidence": evidence,
                        "reason": "evidence is not on the page"})
        return False

    if data.agency and grounded(f"{service_id}:agency", data.agency, data.agency_evidence or ""):
        facts.append(make("agency", None, data.agency, data.agency_evidence))

    for f in data.fees:
        num, unit = parse_amount(f.amount_text)
        variant = _variant(f.variant, f.qualifier, f.evidence)
        condition = canonical_condition(f.condition)
        if _POSTAGE.search(f.evidence or ""):
            label = "postage"
        elif f.kind == "penalty":
            label = "penalty"
        else:
            label = canonical_qualifier(f.qualifier)
        q = _join(variant, label, condition)
        detail = {"kind": f.kind if f.kind in ("surcharge", "penalty") else "base"}
        if variant:
            detail["variant"] = variant
        if condition:
            detail["condition"] = f.condition
        if grounded(f"{service_id}:fee:{q}", f.amount_text, f.evidence):
            facts.append(make("fee", q, f.amount_text, f.evidence, value_num=num, unit=unit,
                              detail=detail))

    for t in data.processing_times:
        variant = _variant(t.variant, t.qualifier, t.evidence)
        condition = canonical_condition(t.condition)
        q = _join(variant, canonical_qualifier(t.qualifier), condition)
        detail = {k: v for k, v in (("variant", variant), ("condition", t.condition)) if v}
        if grounded(f"{service_id}:processing_time:{q}", t.text, t.evidence):
            facts.append(make("processing_time", q, t.text, t.evidence, detail=detail))

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
        for form in forms_on_the_line(page_text, d.evidence):
            known = fact.detail.setdefault("forms", [])
            if form["url"] not in {x["url"] for x in known}:
                known.append(form)
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
        if canon.service_id and canon.service_id != service_id:  # never its own prerequisite
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

    if data.eligibility_evidence:
        sentence = (_sentences(data.eligibility_evidence) or [data.eligibility_evidence])[0].strip()
        if grounded(f"{service_id}:eligibility", sentence, data.eligibility_evidence):
            facts.append(make("eligibility", None, sentence, data.eligibility_evidence))

    unique: dict[str, StagedFact] = {}
    for f in facts:  # one fact per position: the first statement on the page wins
        first = unique.setdefault(f.fact_id, f)
        same_amount = (first.value_num is not None and first.value_num == f.value_num
                       and first.unit == f.unit)
        if first is not f and first.value_text != f.value_text and not same_amount:
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
    result.raw_reply = reply.text

    try:
        data, malformed = parse_extraction(json.loads(reply.text))
    except (json.JSONDecodeError, ValueError) as e:
        result.error = f"model output did not match the schema: {type(e).__name__}: {str(e)[:120]}"
        return result

    result.facts, result.dropped = build_facts(data, body, service_id, source_url, retrieved_at)
    result.dropped = malformed + result.dropped
    return result


# --------------------------------------------------------------------------- sections mode
SYSTEM_SECTIONS = """You extract facts about the Sri Lankan government services described on ONE web page.

A page often covers SEVERAL separate services, each under its own heading. Return a single JSON
object with one key, "services": a list with one object per distinct service on the page.
Each object has these keys:
  title                 the heading of that part of the page, as written
  slug                  a short snake_case id for the service in the agency's own words,
                        such as nic_translation or nic_number_verification
  is_service            true if a citizen can apply for or obtain it; false for contact
                        details, complaints, news, or a pointer to another agency's service
  agency                string or null
  agency_evidence       string or null
  fees                  list of {qualifier, variant, condition, kind, amount_text, evidence}
  documents             list of {name, variant, condition, evidence}
  prerequisites         list of {description, variant, provided_by, evidence}
  processing_times      list of {qualifier, variant, condition, text, evidence}
  eligibility           string or null
  eligibility_evidence  string or null

Rules:
- Put every fact under the service whose heading it sits beneath. Never mix two services.
- Copy fees, durations and document names EXACTLY as written. Do not convert or translate.
- evidence is a sentence or line copied word for word from the page. If you cannot quote the
  page for an item, leave the item out.
- If a value is not stated, return null or an empty list. Never infer or guess.
- variant is the case an item belongs to inside a service (ordinary, minor, lost...), or null.
- condition separates amounts that differ only by a validity period or time window.
- kind is "surcharge" for an amount added to another fee, "penalty" for a fine, else "base".
- Required documents are NOT prerequisites. A prerequisite is a service or step done FIRST.
- For processing_times, text is the duration only ("3 days"), never a sentence.
"""


# A service enters review only if the page states at least one of these for it. A heading with
# nothing but an agency or an eligibility sentence is a label, not a service worth staging.
CONTENT_PREDICATES = {"fee", "document", "prerequisite", "processing_time"}


def _service_id_for(block: dict, taken: set[str], known: frozenset[str] = frozenset()) -> str:
    raw = str(block.get("slug") or block.get("title") or "service")
    base = "svc:" + (slug(raw.replace("svc:", ""), 60) or "service")
    if base in known:  # several parts of the page are about a service the graph already has
        return base
    sid, n = base, 2
    while sid in taken:
        sid, n = f"{base}_{n}", n + 1
    taken.add(sid)
    return sid


def build_section_facts(raw_obj: dict, body: str, url: str, retrieved_at: str,
                        known: frozenset[str] = frozenset()
                        ) -> tuple[list[StagedFact], list[dict], list[dict]]:
    """Facts for every service block in a sections-mode reply: (facts, dropped, sections)."""
    facts: list[StagedFact] = []
    dropped: list[dict] = []
    sections: list[dict] = []
    taken: set[str] = set()
    blocks = raw_obj.get("services") if isinstance(raw_obj, dict) else None
    if not isinstance(blocks, list):
        raise ValueError("model output has no 'services' list")
    for block in blocks:
        if not isinstance(block, dict):
            continue
        title = str(block.get("title") or "").strip()
        is_service = block.get("is_service") is not False
        sid = _service_id_for(block, taken, known)
        data, malformed = parse_extraction(block)
        got, drop = build_facts(data, body, sid, url, retrieved_at)
        dropped += malformed + drop
        sections.append({"title": title, "service_id": sid, "is_service": is_service,
                         "facts": len(got), "dropped": len(drop) + len(malformed)})
        if is_service and not any(f.predicate in CONTENT_PREDICATES for f in got):
            sections[-1]["note"] = ("no fee, document, prerequisite or time stated for this "
                                    "heading: not staged")
            sections[-1]["facts"] = 0
        elif is_service:
            facts += got
        elif got:
            sections[-1]["note"] = "not a citizen service: facts not staged"
    return facts, dropped, sections


def extract_sections(text: str, *, service_id: str, agency: str, source_url: str,
                     retrieved_at: str, llm: LLM,
                     known_services: tuple[str, ...] = ()) -> ExtractionResult:
    """One model call that reads the whole page and returns each service under its own heading."""
    body = strip_menus(text)
    result = ExtractionResult()
    if len(body) > MAX_PAGE_CHARS:
        body, result.truncated = body[:MAX_PAGE_CHARS], True
    known = ""
    if known_services:
        known = ("Services already in the knowledge graph: " + ", ".join(sorted(known_services)) +
                 ".\nIf a part of the page is about one of these, give it that exact id as its slug "
                 "(keep the same text) so its facts join the existing service. Use a new slug only "
                 "for a service that is genuinely different from all of them.\n")
    user = (f"The page was listed under {service_id} (agency: {agency}), which may be only one of "
            f"the services on it.\n{known}Page: {source_url}\n\n--- PAGE START ---\n{body}\n--- PAGE END ---")
    try:
        reply = llm.complete(SYSTEM_SECTIONS, user)
    except LLMError as e:
        result.error = f"llm: {e}"
        return result
    result.prompt_tokens, result.completion_tokens = reply.prompt_tokens, reply.completion_tokens
    result.model = f"{reply.model} [sections]"
    result.raw_reply = reply.text
    try:
        result.facts, result.dropped, result.sections = build_section_facts(
            json.loads(reply.text), body, source_url, retrieved_at, frozenset(known_services))
    except (json.JSONDecodeError, ValueError) as e:
        result.error = f"model output did not match the schema: {type(e).__name__}: {str(e)[:120]}"
    return result


_HEADING = re.compile(r"^\s*(\*\*[^*\n]{6,110}\*\*|#{2,6}\s+\S.{4,110})\s*$", re.M)


def count_headings(text: str) -> int:
    """How many headed parts a saved page has: a cheap hint that it covers several services."""
    return len(_HEADING.findall(strip_menus(text)))
