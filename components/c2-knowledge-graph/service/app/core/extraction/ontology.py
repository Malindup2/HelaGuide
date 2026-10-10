"""The service ontology: what the language model may return, and the staged fact it becomes.

Identifiers follow contracts/naming.md. A fact_id is built from where the fact sits
(service, predicate, qualifier), never from its value, so a changed fee keeps its id and
the graph writer can close the old version.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

PREDICATES = ("fee", "document", "agency", "prerequisite", "processing_time", "eligibility")
SERVICE_ID = re.compile(r"^svc:[a-z0-9_]+$")
FACT_ID = re.compile(r"^svc:[a-z0-9_]+:[a-z0-9_]+(:[a-z0-9_]+)?$")


# ------------------------------------------------------- what the model is asked to return
class FeeItem(BaseModel):
    qualifier: str = Field(description="Short label for which fee this is, e.g. normal, urgent, minor_normal")
    amount_text: str = Field(description="The fee exactly as written on the page, with currency")
    evidence: str = Field(description="The sentence or line from the page that states it, copied verbatim")


class DocumentItem(BaseModel):
    name: str = Field(description="The document the citizen must bring, as written")
    condition: str | None = Field(None, description="When it is needed, if the page limits it")
    evidence: str


class PrerequisiteItem(BaseModel):
    description: str = Field(description="A service or step that must be completed FIRST")
    provided_by: str | None = Field(None, description="Agency that provides it, if named")
    evidence: str


class TimeItem(BaseModel):
    qualifier: str
    text: str = Field(description="The processing or delivery time as written")
    evidence: str


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


def is_grounded(evidence: str, page_text: str) -> bool:
    """The quoted evidence must really be on the page. This is the guard against invention."""
    ev = normalise_for_match(evidence)
    return len(ev) >= 6 and ev in normalise_for_match(page_text)
