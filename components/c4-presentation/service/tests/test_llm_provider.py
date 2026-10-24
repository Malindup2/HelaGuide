"""OpenAI adapter tests with an injected fake SDK client."""

from types import SimpleNamespace

import pytest
import httpx
from openai import RateLimitError

from app.preparation.llm_provider import (
    OpenAIExplanationProvider,
    ProviderFailure,
)
from app.models.explanations import ExplanationDraft


@pytest.mark.parametrize("details, expected", [
    ({"code": "insufficient_quota"}, "provider_quota_or_billing_limit"),
    ({"code": "credit_balance_exhausted", "type": "insufficient_quota"}, "provider_quota_or_billing_limit"),
    ({"code": "project_spend_limit_exceeded"}, "provider_quota_or_billing_limit"),
    ({"code": "rate_limit_exceeded"}, "provider_rate_limit"),
    ({"type": "rate_limit_error", "code": "slow_down"}, "provider_rate_limit"),
    ({"code": "invalid_api_key"}, "provider_invalid_api_key"),
    ({"code": "model_not_found"}, "provider_model_unavailable_or_inaccessible"),
    ({"code": "unrecognized_value"}, "RateLimitError"),
])
def test_structured_provider_failures_are_safe_and_distinguishable(details, expected, caplog):
    secret = "credential-must-not-appear"
    response = httpx.Response(429, request=httpx.Request("POST", "https://example.invalid"))
    error = RateLimitError(secret, response=response, body={"error": {
        **details, "message": secret,
    }})
    class FailingResponses:
        def parse(self, **kwargs):
            raise error
    provider = OpenAIExplanationProvider(client=SimpleNamespace(responses=FailingResponses()))
    with pytest.raises(ProviderFailure) as caught:
        provider.complete(instructions="test", payload="{}", response_model=ExplanationDraft)
    assert caught.value.code == expected
    assert expected in caplog.text
    assert secret not in caplog.text
    assert secret not in str(caught.value)


class FakeResponses:
    def __init__(self, response):
        self.response = response
        self.arguments = None

    def parse(self, **kwargs):
        self.arguments = kwargs
        return self.response


def response(**changes):
    values = {
        "status": "completed",
        "output": [],
        "output_parsed": object(),
        "output_text": '{"synthetic":true,"items":[]}',
        "id": "response-test",
        "model": "model-returned",
        "usage": SimpleNamespace(input_tokens=20, output_tokens=10),
    }
    values.update(changes)
    return SimpleNamespace(**values)


def test_adapter_uses_structured_output_and_disables_response_storage():
    responses = FakeResponses(response())
    provider = OpenAIExplanationProvider(
        client=SimpleNamespace(responses=responses)
    )

    result = provider.complete(
        instructions="System instructions",
        payload='{"synthetic":true}',
        response_model=ExplanationDraft,
    )

    assert responses.arguments["text_format"] is ExplanationDraft
    assert responses.arguments["store"] is False
    assert responses.arguments["reasoning"] == {"effort": "low"}
    assert "tools" not in responses.arguments
    assert result.call.returned_model == "model-returned"
    assert result.call.input_tokens == 20


@pytest.mark.parametrize(
    "value, expected",
    [
        (response(status="incomplete"), "provider_incomplete"),
        (
            response(output_parsed=None),
            "provider_missing_structured_output",
        ),
        (
            response(
                output=[
                    SimpleNamespace(
                        content=[SimpleNamespace(type="refusal")]
                    )
                ]
            ),
            "provider_refusal",
        ),
    ],
)
def test_adapter_rejects_incomplete_missing_and_refused_outputs(value, expected):
    provider = OpenAIExplanationProvider(
        client=SimpleNamespace(responses=FakeResponses(value))
    )
    with pytest.raises(ProviderFailure, match=expected):
        provider.complete(
            instructions="Instructions",
            payload="{}",
            response_model=ExplanationDraft,
        )


def test_missing_key_and_disabled_provider_need_no_network(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    missing = OpenAIExplanationProvider()
    with pytest.raises(ProviderFailure, match="missing_api_key"):
        missing.complete(
            instructions="Instructions",
            payload="{}",
            response_model=ExplanationDraft,
        )

    disabled = OpenAIExplanationProvider(enabled=False)
    with pytest.raises(ProviderFailure, match="provider_disabled"):
        disabled.complete(
            instructions="Instructions",
            payload="{}",
            response_model=ExplanationDraft,
        )
