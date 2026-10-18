"""
Component-internal models for C3. Cross-component messages stay in helaguide_common.contracts.

FreeTextFeedback is a C3-PRIVATE proposal for the message C1 would forward to C3 for
free-text feedback. It is NOT part of contracts/ and has not been agreed with the team.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FreeTextEntities(BaseModel):
    model_config = ConfigDict(extra="forbid")
    service_id: str | None = Field(default=None, pattern=r"^svc:[a-z0-9_]+$")
    predicate_hint: Literal["fee", "document", "agency", "prerequisite", "processing_time", "eligibility"] | None = None
    mentioned_value: str | float | int | None = None
    visit_date: date | None = None
    reporter_token: str | None = Field(default=None, pattern=r"^anon-[a-z0-9]+$")
    # The services on the citizen's screen just before the feedback (a workflow they were looking at).
    # A SOFT hint: used only when the words of the message cannot decide the service by themselves.
    context_services: list[str] | None = None

    @field_validator("context_services")
    @classmethod
    def _service_ids(cls, v):
        import re
        for x in v or []:
            if not re.match(r"^svc:[a-z0-9_]+$", x):
                raise ValueError(f"not a service id: {x}")
        return v


class FreeTextFeedback(BaseModel):
    """C1 -> C3 (proposed, private). One feedback message in the citizen's own words."""
    model_config = ConfigDict(extra="forbid")
    message_id: str
    session_id: str
    timestamp: datetime
    language: Literal["en", "si", "mixed"] | None = None     # "mixed" = Singlish
    raw_text: str = Field(min_length=1, max_length=2000)
    text_en: str | None = None                                # English text if C1 already produced it
    intent: Literal["feedback_discrepancy"] = "feedback_discrepancy"
    entities: FreeTextEntities = FreeTextEntities()


class StructuredExtras(BaseModel):
    """Optional C3-private extras for the contract `feedback` message (demo scaffolding)."""
    model_config = ConfigDict(extra="forbid")
    visit_date: date | None = None
    reporter_token: str | None = Field(default=None, pattern=r"^anon-[a-z0-9]+$")


@dataclass
class Incoming:
    """Both input paths are converted into this one shape before any algorithm runs."""
    message_id: str
    path: Literal["structured", "freetext"]
    reporter_id: str
    submitted_at: datetime
    raw_text: str
    fact_id: str | None = None
    language: str | None = None
    text_en: str | None = None
    service_hint: str | None = None
    predicate_hint: str | None = None
    claimed_hint: Any = None
    visit_date: date | None = None
    context_services: list[str] | None = None


@dataclass
class FactVersion:
    fact_id: str
    service_id: str
    predicate: str
    qualifier: str | None
    value_text: str
    value_num: float | None
    unit: str | None
    description: str
    source_url: str | None
    retrieved_at: datetime | None
    valid_from: datetime
    valid_to: datetime | None
    connection_unverified: bool = False
    embedding: Any = None        # numpy array or None


@dataclass
class ConfidenceRecord:
    fact_id: str
    valid_from: datetime
    base_confidence: float
    confidence: float
    status: str = "active"
    drop_events: int = 0
    verified_by_source: bool = False
    last_updated: datetime | None = None
    last_reason: str | None = None


@dataclass
class Reporter:
    reporter_id: str
    created_at: datetime
    a: float = 0.0
    b: float = 0.0
    rep_day: date | None = None
    rep_delta_today: float = 0.0


@dataclass
class ReportRow:
    report_id: str
    message_id: str
    path: str
    reporter_id: str
    raw_text: str
    text_en: str | None
    language: str | None
    fact_id: str
    fact_valid_from: datetime
    discrepancy_type: str
    report_kind: str
    claimed_value_raw: str | None
    claimed_num: float | None
    claimed_key: str
    visit_date: date | None
    submitted_at: datetime
    trust_t: float
    sig_r: float
    sig_s: float
    sig_c: float
    sig_v: float
    v_imputed: bool
    dup_count: int
    indep_i: float
    state: str = "active"
    embedding: Any = None
    trace: dict = field(default_factory=dict)


class DemoFeedbackRequest(BaseModel):
    """What the citizen console sends when a pre-written sample message is submitted."""
    model_config = ConfigDict(extra="forbid")
    sample_id: str
    persona_id: str
    visit_date: date | None = None
