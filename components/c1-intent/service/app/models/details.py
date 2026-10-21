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


Conditions = dict[str, int | bool]


class RequestSummary(BaseModel):
    """A service request in the conversation other than the active one."""
    model_config = ConfigDict(extra="forbid")
    intent: str
    service_id: str | None
    slots: dict[str, str]
    conditions: Conditions = Field(default_factory=dict)
    variant_pending: bool = False


class IntentDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    turn_id: int = Field(ge=0)
    state_version: int = Field(ge=0, description="Goes up when the active request's intent, slots, conditions or "
                               "pending variant change; ask C2 again when it differs from the last one sent")
    internal_intent: str = Field(description="One of the 12 schema-v1.1 intents, or unknown")
    intent_model_output: str = Field(description="What the classifier predicted before the confidence check")
    confidence: float = Field(ge=0, le=1)
    intent_source: Literal["model", "keyword_fallback", "previous_topic", "active_intent", "current_message_switch",
                           "pending_resume", "variant_answer", "service_keyword", "greeting", "unknown"]
    active_intent: str | None = Field(description="The core intent the conversation is about; kept across turns "
                                      "unless the user clearly switches service. None until one is confident")
    intent_locked: bool = Field(description="True when this turn kept active_intent over the model's prediction")
    ready: bool = Field(description="All slots of active_intent are filled and confirmed; the request can go to "
                        "orchestration")
    assumed_slots: list[str] = Field(description="Slots carried over from an earlier request that the citizen "
                                     "has not confirmed yet (only district); the bot asks before using them")
    variant_pending: bool = Field(default=False, description="The citizen named the service but not which kind "
                                  "(\"i need a NIC\"); internal_intent is provisional and the reply asks")
    reply: str = Field(min_length=1, description="What the bot says next: the next slot question, a confirmation, "
                       "a clarifying question or a fallback")
    completed_requests: list[RequestSummary] = Field(description="Requests finished earlier in the conversation "
                                                     "(all slots filled when the citizen moved on)")
    pending_requests: list[RequestSummary] = Field(description="Requests left unfinished by a switch; the bot "
                                                   "offers to finish them once the active one is ready")
    route: Route
    slots: dict[str, str]
    conditions: Conditions = Field(default_factory=dict, description="Facts about the applicant that are not "
                                   "slots, kept only when said and never asked for: applicant_age (int), "
                                   "applicant_minor (bool). C1 does not decide what they imply; C2 does")
    missing_slots: list[str]
    language: Literal["si", "en", "ta", "mixed"]
    language_tags: list[LanguageTag]
    code_switched: bool
    latency_ms: float = Field(ge=0)
    context_strategy: str = Field(description="How the intent model's input is built: window_3 = the last 3 user "
                                  "messages (the deployed setting, Observation 8)")
    context_tokens: int = Field(ge=0, description="Tokens the intent model read this turn: the whole context window "
                                "including the current message, XLM-R tokenizer with <s> and </s>, before "
                                "truncation; 0 when the model did not run (a greeting)")
    intent: Intent = Field(description="The same projection /v1/intent returns")
