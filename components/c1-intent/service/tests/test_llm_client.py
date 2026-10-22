import httpx
import pytest

from app.core.llm_client import (BODY_CHARS, REPAIR_MESSAGE, FakeLLM, LLMError, LLMResult, LLMUsage,
                                 OpenAICompatClient, parse_json_object)
from app.core.settings import DialogueSettings

REQ = httpx.Request("POST", "http://llm.test/v1/chat/completions")
KEY = "fake-key-123"


def ok(content, prompt_tokens=10, completion_tokens=4, model="test-model:7b"):
    return httpx.Response(200, request=REQ, json={
        "model": model, "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens}})


def error(status, text):
    return httpx.Response(status, text=text, request=REQ)


class Transport:
    """Stands in for httpx.post: returns (or raises) the scripted items in order, records each request."""

    def __init__(self, *items):
        self.items = list(items)
        self.requests = []

    def __call__(self, url, json, headers, timeout):
        self.requests.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        item = self.items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def client(transport, **kw):
    return OpenAICompatClient("http://llm.test/v1/", "test-model", post=transport, sleep=lambda s: None, **kw)


# ---------------------------------------------------------------- JSON and usage
def test_valid_json_with_usage():
    t = Transport(ok('{"reply": "Hello!", "slot_updates": {}}', 120, 15))
    out = client(t).complete_json("sys", [{"role": "user", "content": "hi"}])
    assert isinstance(out, LLMResult)
    assert out.data == {"reply": "Hello!", "slot_updates": {}}
    u = out.usage
    assert (u.prompt_tokens, u.completion_tokens, u.total_tokens, u.model, u.calls) == \
        (120, 15, 135, "test-model:7b", 1)
    assert u.latency_ms >= 0
    req = t.requests[0]
    assert req["url"] == "http://llm.test/v1/chat/completions"
    assert req["json"]["temperature"] == 0
    assert req["json"]["response_format"] == {"type": "json_object"}
    assert req["json"]["messages"][0] == {"role": "system", "content": "sys"}
    assert req["headers"] == {}             # no key (Ollama): no Authorization header


def test_missing_usage_counts_zero():
    r = httpx.Response(200, request=REQ, json={"choices": [{"message": {"content": "{}"}}]})
    u = client(Transport(r)).complete_json("sys", []).usage
    assert (u.prompt_tokens, u.completion_tokens, u.model, u.calls) == (0, 0, "test-model", 1)


def test_api_key_goes_in_header_only():
    t = Transport(ok("{}"))
    client(t, api_key=KEY).complete_json("sys", [])
    assert t.requests[0]["headers"] == {"Authorization": f"Bearer {KEY}"}
    assert KEY not in str(t.requests[0]["json"])


def test_fenced_json_is_accepted():
    assert parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}


def test_invalid_json_gets_one_repair_retry_and_usage_adds_up():
    t = Transport(ok("Sure! here you go", 100, 5), ok('{"reply": "ok"}', 110, 6))
    out = client(t).complete_json("sys", [{"role": "user", "content": "hi"}])
    assert out.data == {"reply": "ok"}
    assert (out.usage.prompt_tokens, out.usage.completion_tokens, out.usage.calls) == (210, 11, 2)
    repair = t.requests[1]["json"]["messages"]
    assert repair[-2] == {"role": "assistant", "content": "Sure! here you go"}
    assert repair[-1] == {"role": "user", "content": REPAIR_MESSAGE}


def test_invalid_json_twice_raises():
    t = Transport(ok("nope"), ok("[1, 2]"))
    with pytest.raises(LLMError, match="repair"):
        client(t).complete_json("sys", [])
    assert len(t.requests) == 2


# ---------------------------------------------------------------- retries
def test_retries_on_429_and_5xx_then_succeeds():
    t = Transport(error(429, "slow down"), error(503, "busy"), ok('{"x": 1}'))
    assert client(t).complete_json("sys", []).data == {"x": 1}
    assert len(t.requests) == 3


def test_no_retry_on_4xx():
    t = Transport(error(401, "bad key"))
    with pytest.raises(LLMError, match="401"):
        client(t).complete_json("sys", [])
    assert len(t.requests) == 1


def test_gives_up_after_attempts():
    t = Transport(*[error(500, "err")] * 3)
    with pytest.raises(LLMError, match="500"):
        client(t).complete_json("sys", [])
    assert len(t.requests) == 3


def test_timeout_raises_without_retry():
    t = Transport(httpx.ReadTimeout("slow", request=REQ))
    with pytest.raises(LLMError, match="timed out"):
        client(t, timeout=5).complete_json("sys", [])
    assert len(t.requests) == 1


def test_connection_error_is_retried():
    t = Transport(httpx.ConnectError("refused", request=REQ), ok('{"x": 2}'))
    assert client(t).complete_json("sys", []).data == {"x": 2}


# ---------------------------------------------------------------- JSON mode
def test_json_mode_rejected_retries_without_it_and_remembers():
    t = Transport(error(400, '{"error": {"message": "response_format json_object is not supported by this model"}}'),
                  ok('{"x": 1}'), ok('{"x": 2}'))
    c = client(t)
    assert c.complete_json("sys", []).data == {"x": 1}
    assert "response_format" in t.requests[0]["json"]
    assert "response_format" not in t.requests[1]["json"]
    assert c.json_mode is False
    assert c.complete_json("sys", []).data == {"x": 2}        # later calls skip it straight away
    assert "response_format" not in t.requests[2]["json"]
    assert len(t.requests) == 3


def test_other_400_is_not_retried():
    t = Transport(error(400, "model 'nope' not found"))
    c = client(t)
    with pytest.raises(LLMError, match="400"):
        c.complete_json("sys", [])
    assert len(t.requests) == 1
    assert c.json_mode is True


def test_json_mode_400_after_switching_off_is_an_error():
    t = Transport(error(400, "json mode unsupported"), error(400, "json mode unsupported"))
    with pytest.raises(LLMError, match="400"):
        client(t).complete_json("sys", [])
    assert len(t.requests) == 2        # one free retry without response_format, then stop


def test_json_mode_off_by_setting():
    t = Transport(ok("{}"))
    c = OpenAICompatClient.from_settings(DialogueSettings(json_mode=False))
    c._post, c._sleep = t, lambda s: None
    c.complete_json("sys", [])
    assert "response_format" not in t.requests[0]["json"]


# ---------------------------------------------------------------- error messages
def test_error_messages_truncate_body_and_never_show_headers():
    t = Transport(error(401, f"invalid key {KEY} " + "x" * 1000))
    with pytest.raises(LLMError) as e:
        client(t, api_key=KEY).complete_json("sys", [])
    msg = str(e.value)
    assert len(msg) <= len("HTTP 401: ") + BODY_CHARS
    assert "Bearer" not in msg and "Authorization" not in msg


def test_long_transport_errors_are_truncated():
    t = Transport(*[httpx.ConnectError("y" * 1000, request=REQ)] * 3)
    with pytest.raises(LLMError) as e:
        client(t).complete_json("sys", [])
    assert len(str(e.value)) <= len("ConnectError: ") + BODY_CHARS


# ---------------------------------------------------------------- reasoning effort and tokens
def test_reasoning_effort_not_sent_by_default():
    t = Transport(ok("{}"))
    client(t).complete_json("sys", [])
    assert "reasoning_effort" not in t.requests[0]["json"]


def test_reasoning_effort_sent_when_set():
    t = Transport(ok("{}"))
    client(t, reasoning_effort="low").complete_json("sys", [])
    assert t.requests[0]["json"]["reasoning_effort"] == "low"


def test_reasoning_effort_from_settings():
    c = OpenAICompatClient.from_settings(DialogueSettings(reasoning_effort="none"))
    assert c.reasoning_effort == "none"


def test_reasoning_tokens_recorded_separately():
    r = httpx.Response(200, request=REQ, json={"choices": [{"message": {"content": "{}"}}], "usage": {
        "prompt_tokens": 50, "completion_tokens": 300, "completion_tokens_details": {"reasoning_tokens": 260}}})
    u = client(Transport(r)).complete_json("sys", []).usage
    assert (u.prompt_tokens, u.completion_tokens, u.reasoning_tokens, u.total_tokens) == (50, 300, 260, 350)


def test_reasoning_tokens_top_level_and_summed_over_repair():
    first = httpx.Response(200, request=REQ, json={"choices": [{"message": {"content": "oops"}}],
                                                   "usage": {"completion_tokens": 10, "reasoning_tokens": 7}})
    second = httpx.Response(200, request=REQ, json={"choices": [{"message": {"content": "{}"}}], "usage": {
        "completion_tokens": 10, "completion_tokens_details": {"reasoning_tokens": 5}}})
    assert client(Transport(first, second)).complete_json("sys", []).usage.reasoning_tokens == 12


def test_no_reasoning_tokens_is_zero():
    assert client(Transport(ok("{}"))).complete_json("sys", []).usage.reasoning_tokens == 0


# ---------------------------------------------------------------- settings and FakeLLM
def test_from_settings():
    c = OpenAICompatClient.from_settings(DialogueSettings(base_url="http://h/v1", model="m", timeout=7))
    assert (c.base_url, c.model, c.timeout, c.json_mode) == ("http://h/v1", "m", 7, True)


def test_fake_llm_scripts_replies_usage_and_errors():
    scripted = LLMResult({"reply": "b"}, LLMUsage(1, 2, 0, "m", 3.0, 1))
    fake = FakeLLM({"reply": "a"}, scripted, LLMError("down"))
    out = fake.complete_json("one two", [{"role": "user", "content": "three four five"}])
    assert out.data == {"reply": "a"}
    assert (out.usage.prompt_tokens, out.usage.completion_tokens, out.usage.reasoning_tokens, out.usage.model,
            out.usage.calls) == (5, 2, 0, "fake-llm", 1)
    assert fake.complete_json("s", []) is scripted
    with pytest.raises(LLMError):
        fake.complete_json("s", [])
    with pytest.raises(LLMError):
        fake.complete_json("s", [])     # nothing left
    assert len(fake.calls) == 4
