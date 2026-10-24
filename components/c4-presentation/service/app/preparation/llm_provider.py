"""Official OpenAI SDK adapter for structured explanation generation."""

import math
import logging
import os
from importlib.metadata import version
from typing import Protocol
from pathlib import Path
from dotenv import load_dotenv

from openai import OpenAI, OpenAIError
from pydantic import BaseModel, ValidationError

from app.models.explanations import (
    ProviderCall,
    ProviderIdentity,
    ProviderReply,
)


DEFAULT_MODEL = "gpt-5.4-mini-2026-03-17"
log = logging.getLogger("helaguide.c4.llm")


def provider_error_code(exc: OpenAIError) -> str:
    """Classify structured errors without exposing messages, bodies or keys."""
    body = getattr(exc, "body", None)
    body = body if isinstance(body, dict) else {}
    nested = body.get("error")
    details = nested if isinstance(nested, dict) else body
    markers = (
        getattr(exc, "code", None), getattr(exc, "type", None),
        details.get("code"), details.get("type"),
    )
    if any(marker in (
        "insufficient_quota", "credit_balance_exhausted", "billing_not_active",
        "billing_hard_limit_reached", "organization_usage_limit_reached",
        "project_usage_limit_reached", "organization_spend_limit_exceeded",
        "project_spend_limit_exceeded",
    ) for marker in markers):
        return "provider_quota_or_billing_limit"
    if any(marker == "invalid_api_key" for marker in markers):
        return "provider_invalid_api_key"
    if any(marker == "model_not_found" for marker in markers):
        return "provider_model_unavailable_or_inaccessible"
    if any(marker in ("rate_limit_exceeded", "rate_limit_error", "slow_down") for marker in markers):
        return "provider_rate_limit"
    return type(exc).__name__


class ProviderFailure(RuntimeError):
    """A safe diagnostic code, without provider payloads or credentials."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class ExplanationProvider(Protocol):
    @property
    def identity(self) -> ProviderIdentity:
        ...

    def complete(
        self,
        *,
        instructions: str,
        payload: str,
        response_model: type[BaseModel],
    ) -> ProviderReply:
        ...


class OpenAIExplanationProvider:
    """Lazy client creation: construction does not make a network request.

    enabled=False permits offline use of previously loaded cache artifacts.
    API keys are never included in the identity or explanation records.
    """

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        enabled: bool = True,
        timeout_seconds: float = 45.0,
        max_output_tokens: int = 6000,
        client=None,
    ):
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model must be a nonempty identifier")
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be finite and positive")

        self._identity = ProviderIdentity(
            name="openai",
            requested_model=model,
            sdk_version=version("openai"),
            max_output_tokens=max_output_tokens,
        )
        self._enabled = enabled
        self._timeout = timeout_seconds
        self._client = client
        self._owns_client = client is None

    @property
    def identity(self) -> ProviderIdentity:
        return self._identity

    @classmethod
    def from_environment(cls, *, allow_live: bool = True):
        env_path = Path(__file__).resolve().parents[2] / ".env"
        load_dotenv(dotenv_path=env_path, override=False)

        enabled_text = os.getenv("C4_LLM_ENABLED", "true").lower()
        if enabled_text not in {"true", "false"}:
            raise ValueError("C4_LLM_ENABLED must be true or false")

        return cls(
            model=os.getenv("C4_LLM_MODEL", DEFAULT_MODEL),
            enabled=allow_live and enabled_text == "true",
        )

    def _get_client(self):
        if not self._enabled:
            raise ProviderFailure("provider_disabled")

        if self._client is None:
            key = os.getenv("OPENAI_API_KEY")
            if not key or not key.strip():
                raise ProviderFailure("missing_api_key")

            self._client = OpenAI(
                api_key=key,
                timeout=self._timeout,
                max_retries=0,
            )
        return self._client

    def complete(
        self,
        *,
        instructions: str,
        payload: str,
        response_model: type[BaseModel],
    ) -> ProviderReply:
        client = self._get_client()

        try:
            response = client.responses.parse(
                model=self.identity.requested_model,
                instructions=instructions,
                input=[{"role": "user", "content": payload}],
                text_format=response_model,
                reasoning={"effort": self.identity.reasoning_effort},
                max_output_tokens=self.identity.max_output_tokens,
                store=False,
            )
        except OpenAIError as exc:
            code = provider_error_code(exc)
            # Deliberately never log str(exc), request headers or error bodies.
            log.warning("C4 LLM request failed: %s", code)
            raise ProviderFailure(code) from None
        except (ValidationError, ValueError):
            raise ProviderFailure("provider_schema_failure") from None

        if response.status != "completed":
            raise ProviderFailure("provider_incomplete")

        for output in response.output:
            for content in getattr(output, "content", ()):
                if getattr(content, "type", None) == "refusal":
                    raise ProviderFailure("provider_refusal")

        if response.output_parsed is None or not response.output_text:
            raise ProviderFailure("provider_missing_structured_output")

        usage = response.usage
        return ProviderReply(
            text=response.output_text,
            call=ProviderCall(
                response_id=response.id,
                returned_model=response.model,
                input_tokens=(
                    None if usage is None else usage.input_tokens
                ),
                output_tokens=(
                    None if usage is None else usage.output_tokens
                ),
            ),
        )

    def close(self):
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None
