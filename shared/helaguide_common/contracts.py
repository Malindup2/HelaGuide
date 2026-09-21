"""
Pydantic mirrors of contracts/schema/v1. The JSON Schemas are the source of truth;
keep these in step with them. CI validates the examples against the schemas.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SERVICE_ID = r"^svc:[a-z0-9_]+$"
FACT_ID = r"^svc:[a-z0-9_]+:[a-z0-9_]+(:[a-z0-9_]+)?$"

Scalar = str | float | int | bool


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ------------------------------------------------------------------- fact
class FactVersion(_Strict):
    value: Scalar
    valid_from: datetime
    valid_to: datetime


class Fact(_Strict):
    fact_id: str = Field(pattern=FACT_ID)
    service_id: str = Field(pattern=SERVICE_ID)
    predicate: Literal["fee", "document", "agency", "prerequisite", "processing_time", "eligibility"]
    value: Scalar
    unit: str | None = None
    source_url: str
    retrieved_at: datetime
    valid_from: datetime
    valid_to: datetime | None
    history: list[FactVersion] = []


# ----------------------------------------------------------------- intent
class IntentEntities(_Strict):
    service_id: str | None = Field(default=None, pattern=SERVICE_ID)
    district: str | None = None


class Intent(_Strict):
    session_id: str
    turn_id: int = Field(ge=0)
    language: Literal["si", "en", "ta", "mixed"]
    intent: Literal["apply_service", "service_info", "check_requirements", "unknown"]
    entities: IntentEntities
    confidence: float = Field(ge=0, le=1)


# ------------------------------------------------------------------- plan
class Fee(_Strict):
    value: float = Field(ge=0)
    currency: str
    fact_id: str = Field(pattern=FACT_ID)


class Document(_Strict):
    name: str
    fact_id: str = Field(pattern=FACT_ID)


class PlanStep(_Strict):
    order: int = Field(ge=1)
    service_id: str = Field(pattern=SERVICE_ID)
    name: str
    agency: str
    fee: Fee
    documents: list[Document]
    depends_on: list[str]


class Provenance(_Strict):
    source_url: str
    retrieved_at: datetime


class Plan(_Strict):
    plan_id: str
    requested_service_id: str = Field(pattern=SERVICE_ID)
    generated_at: datetime
    steps: list[PlanStep] = Field(min_length=1)
    provenance: dict[str, Provenance]


# ---------------------------------------------------------- feedback/trust
class Feedback(_Strict):
    feedback_id: str
    session_id: str
    fact_id: str = Field(pattern=FACT_ID)
    plan_id: str | None = None
    text: str = Field(min_length=1, max_length=2000)
    proposed_value: str | float | int | None = None
    submitted_at: datetime


class TrustScore(_Strict):
    fact_id: str = Field(pattern=FACT_ID)
    confidence: float = Field(ge=0, le=1)
    status: Literal["ok", "disputed", "verified_correction"]
    report_count: int = Field(ge=0)
    updated_at: datetime


class Correction(_Strict):
    correction_id: str
    fact_id: str = Field(pattern=FACT_ID)
    proposed_value: Scalar
    confidence: float = Field(ge=0, le=1)
    report_count: int = Field(ge=1)
    verified_at: datetime


# ----------------------------------------------------------------- render
class RenderStep(_Strict):
    order: int = Field(ge=1)
    title: str
    body: str
    fee_display: str
    documents: list[str]
    warning: str | None = None


class Render(_Strict):
    session_id: str
    plan_id: str
    mode: Literal["standard", "simplified", "voice"]
    detail_level: Literal["low", "medium", "high"]
    steps: list[RenderStep]


# ------------------------------------------------------- request bodies
class UtteranceRequest(_Strict):
    """What the frontend sends to the gateway, and the gateway to C1."""
    session_id: str
    text: str = Field(min_length=1, max_length=2000)


class RenderRequest(_Strict):
    """What the gateway sends to C4."""
    session_id: str
    plan: Plan
    trust: list[TrustScore] = []
