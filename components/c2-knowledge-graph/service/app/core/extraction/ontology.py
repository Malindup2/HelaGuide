"""The service ontology: what the language model may return, and the staged fact it becomes.

Identifiers follow contracts/naming.md. A fact_id is built from where the fact sits
(service, predicate, qualifier), never from its value, so a changed fee keeps its id and
the graph writer can close the old version.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field

PREDICATES = ("fee", "document", "agency", "prerequisite", "processing_time", "eligibility")
SERVICE_ID = re.compile(r"^svc:[a-z0-9_]+$")
FACT_ID = re.compile(r"^svc:[a-z0-9_]+:[a-z0-9_]+(:[a-z0-9_]+)?$")


# ------------------------------------------------------- what the model is asked to return
# A model that thinks less sometimes sends null for a label or a quote. That is a missing
# label, not a broken item: it becomes "" and is handled (a quote of "" is never grounded).
def _as_text(v):
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return "; ".join(str(x) for x in v if x is not None)
    return v


Text = Annotated[str, BeforeValidator(_as_text)]


VARIANT_HELP = ("Which case of the service this applies to, such as ordinary, minor, lost, "
                "replacement, diplomatic. Null when it applies to every case.")


class FeeItem(BaseModel):
    qualifier: Text = Field("", description="Short label for which fee this is, such as normal or urgent")
    variant: str | None = Field(None, description=VARIANT_HELP)
    condition: str | None = Field(None, description="What distinguishes this amount from the same fee "
                                 "in another situation: a validity period ('3 years'), a time window "
                                 "('within one year of issue'). Null when there is none.")
    kind: str = Field("base", description="'base' for the fee itself, 'surcharge' for an amount "
                                          "added to another fee ('in addition to the passport fee')")
    amount_text: str = Field(description="The fee exactly as written on the page, with currency")
    evidence: Text = Field("", description="The sentence or line from the page that states it, copied verbatim")


class DocumentItem(BaseModel):
    name: str = Field(description="The document the citizen must bring, as written")
    variant: str | None = Field(None, description=VARIANT_HELP)
    condition: str | None = Field(None, description="When it is needed, if the page limits it")
    evidence: Text = ""


class PrerequisiteItem(BaseModel):
    description: str = Field(description="A service or step that must be completed FIRST")
    variant: str | None = Field(None, description=VARIANT_HELP)
    provided_by: str | None = Field(None, description="Agency that provides it, if named")
    evidence: Text = ""


class TimeItem(BaseModel):
    qualifier: Text = ""
    variant: str | None = Field(None, description=VARIANT_HELP)
    condition: str | None = Field(None, description="A validity period or time window that distinguishes it")
    text: Text = Field("", description="The processing or delivery time as written")
    evidence: Text = ""


class PageExtraction(BaseModel):
    agency: str | None = None
    agency_evidence: str | None = None
    fees: list[FeeItem] = Field(default_factory=list)
    documents: list[DocumentItem] = Field(default_factory=list)
    prerequisites: list[PrerequisiteItem] = Field(default_factory=list)
    processing_times: list[TimeItem] = Field(default_factory=list)
    eligibility: str | None = None
    eligibility_evidence: str | None = None


# ----------------------------------------------------------------------- staged fact
@dataclass
class StagedFact:
    fact_id: str
    service_id: str
    predicate: str
    qualifier: str | None
    value_text: str
    source_url: str
    retrieved_at: str
    evidence: str
    value_num: float | None = None
    unit: str | None = None
    detail: dict = field(default_factory=dict)
    status: str = "pending"


# ------------------------------------------------------------------------ normalising
def slug(text: str, max_len: int = 40) -> str:
    """Lowercase snake_case, ASCII only, as the contract requires."""
    s = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")
    if len(s) <= max_len:
        return s
    cut = s[:max_len]
    if s[max_len] != "_" and "_" in cut:  # cut on a word boundary, not mid-word
        cut = cut.rsplit("_", 1)[0]
    return cut.rstrip("_")


_CURRENCY = r"(?:lkr|rs|rupees?)"
_AMOUNT = re.compile(rf"(?i)\b({_CURRENCY})\b\.?\s*([\d][\d,]*(?:\.\d+)?)")
_BARE_AMOUNT = re.compile(r"([\d][\d,]*(?:\.\d+)?)")
_FREE = re.compile(r"(?i)\b(free of charge|free|no charge|nil)\b")


def parse_amount(text: str) -> tuple[float | None, str | None]:
    """'LKR. 10,000.00', 'LKR.20,000.00', 'LKR 3500.00' and 'Rs. 20,000' all give a number.

    The page uses four formats for one kind of value; the graph must hold one.
    Returns (value, unit). Unit is only set when a currency was written.
    """
    m = _AMOUNT.search(text or "")
    if m:
        return float(m.group(2).replace(",", "")), "LKR"
    if _FREE.search(text or ""):
        return 0.0, "LKR"
    m = _BARE_AMOUNT.search(text or "")
    if m:
        return float(m.group(1).replace(",", "")), None
    return None, None


def normalise_for_match(text: str) -> str:
    """Letters and digits only, lowercase, single spaces: robust to markdown and punctuation."""
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _sentences(text: str) -> list[str]:
    """Split at a full stop that ends a sentence: after a letter or digit, before a capital.

    "Rs. 20,000" is not split ("Rs." is followed by a digit), so an abbreviation can never
    cut a quote into pieces that each look like a real, shorter sentence.
    """
    parts = re.split(r"(?<=[a-z0-9\)][.!?])\s+(?=[A-Z(\"'])|\n+|\s*;\s*|\s*\|\s*", text or "")
    return [x for x in parts if x.strip()]


def _contains_value(sentence: str, value: str) -> bool:
    """Every number in the value, and most of its longer words, appear in the sentence."""
    s_tokens = set(normalise_for_match(sentence).split())
    v_tokens = normalise_for_match(value).split()
    digits = [t for t in v_tokens if t.isdigit()]
    words = [t for t in v_tokens if not t.isdigit() and len(t) >= 4]
    if not v_tokens:
        return False
    if not digits and not words:  # a short value such as "One day": every word must be there
        return all(t in s_tokens for t in v_tokens)
    if any(d not in s_tokens for d in digits):
        return False
    return not words or sum(w in s_tokens for w in words) / len(words) >= 0.6


def _tokens_in_order_on_page(ev: str, page: str, max_extra: int = 14) -> bool:
    """Every word of the quote is on the page in the quoted order, within a short stretch.

    A table row puts a link or a column between its label and its price, so the quote is
    not one unbroken run. Allowing at most `max_extra` words of gap in total keeps a quote
    from being stitched together out of unrelated parts of a page.
    """
    q = ev.split()
    if len(q) < 4:
        return False
    p = page.split()
    first = q[0]
    for start in (i for i, w in enumerate(p) if w == first):
        at, ok = start, True
        for tok in q[1:]:
            try:
                at = p.index(tok, at + 1, at + 2 + max_extra)
            except ValueError:
                ok = False
                break
        if ok and (at - start + 1) - len(q) <= max_extra:
            return True
    return False


def is_grounded(evidence: str, page_text: str, value: str | None = None) -> bool:
    """The quoted evidence must really be on the page. This is the guard against invention.

    The whole quote, as one run of the page, grounds it (and, when a value is given, the quote
    must hold that value too). Models often run a real sentence on
    into the next line, so otherwise a single sentence of the quote that is on the page grounds
    it, provided that sentence itself contains the value being claimed. A quote with no real
    sentence in it, or whose real sentence does not hold the value, is not grounded.
    """
    page = normalise_for_match(page_text)
    ev = normalise_for_match(evidence)
    if len(ev) >= 6 and ev in page:
        # A real line quoted next to a different value is the dangerous case: the quote must
        # also hold the value being claimed.
        return value is None or _contains_value(evidence, value)
    if value is None:
        return False
    segments = [normalise_for_match(x) for x in _sentences(evidence)]
    segments = [x for x in segments if x]
    for sentence in _sentences(evidence):
        norm = normalise_for_match(sentence)
        if len(norm) >= 25 and norm in page and _contains_value(sentence, value):
            return True
    # A table row: the label and the price sit apart on the page, with a link or a column
    # between them. Every part of the quote must be on the page, in the order quoted, and the
    # quote as a whole must hold the value.
    holds_value = _contains_value(evidence, value)
    # A link's address is not reading text; drop it so it does not count towards the gap.
    page_no_urls = normalise_for_match(re.sub(r"\]\([^)]*\)", "]", page_text or ""))
    if holds_value and _tokens_in_order_on_page(ev, page_no_urls):
        return True
    if len(segments) >= 2 and holds_value:
        at = 0
        for seg in segments:
            found = page.find(seg, at)
            if found < 0:
                return False
            at = found + len(seg)
        return True
    return False
