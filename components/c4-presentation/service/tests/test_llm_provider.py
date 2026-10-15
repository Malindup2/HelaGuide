"""OpenAI adapter tests with an injected fake SDK client."""

from types import SimpleNamespace

import pytest

from app.core.llm_provider import (
    OpenAIExplanationProvider,
    ProviderFailure,
)
from app.models.explanations import ExplanationDraft


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