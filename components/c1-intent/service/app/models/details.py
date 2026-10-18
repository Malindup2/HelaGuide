"""
C1-only models for POST /v1/intent/details. Not part of the team contract: the contract `Intent` is
embedded unchanged, and the extra fields are proposed for a later contract version in
research/docs/c1_contract_proposal.md.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from helaguide_common.contracts import Intent, UtteranceRequest

Route = Literal["orchestration", "trust_verification", "fallback", "none"]


class DetailsRequest(UtteranceRequest):
    """UtteranceRequest plus the bot's last question, which helps the tracker read short answers."""
    bot_text: str | None = Field(default=None, max_length=2000)


class LanguageTag(BaseModel):
    model_config = ConfigDict(extra="forbid")
    word: str
    tag: str = Field(description="SI, EN, MIXED, NE or OTHER (O for words past the model's max length)")


class IntentDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    turn_id: int = Field(ge=0)
    internal_intent: str = Field(description="One of the 12 schema-v1.1 intents, or unknown")
    intent_model_output: str = Field(description="What the classifier predicted before the confidence check")
    confidence: float = Field(ge=0, le=1)
    intent_source: Literal["model", "keyword_fallback", "previous_topic", "unknown"]
    route: Route
    slots: dict[str, str]
    missing_slots: list[str]
    language: Literal["si", "en", "ta", "mixed"]
    language_tags: list[LanguageTag]
    code_switched: bool
    latency_ms: float = Field(ge=0)
    intent: Intent = Field(description="The same projection /v1/intent returns")
