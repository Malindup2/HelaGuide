"""
/v1/intent and /v1/intent/details are byte-for-byte what the base branch (c1/context-v2) returns, in every
C1_DIALOGUE_MODE and with /v1/chat traffic on the same session IDs. Golden responses: fixtures/compat_context_v2.json,
recorded from c1/context-v2 with compat_record.py (only latency_ms is normalised; see compat_cases.normalise).
"""
import json
from pathlib import Path

import pytest

from app.core import pipeline
from app.core.llm_client import LLMResult, LLMUsage
from app.core.sessions import SessionStore
from app.main import app
from tests import compat_cases
from tests.conftest import FakeEngine

GOLDEN = json.loads((Path(__file__).parent / "fixtures" / "compat_context_v2.json").read_text(encoding="utf-8"))


class GreetingLLM:
    """Answers every chat turn with a greeting and no slot changes."""

    def complete_json(self, system, messages):
        return LLMResult({"reply": "Hello!", "dialogue_act": "greet", "active_intent": None, "slot_updates": {}},
                         LLMUsage(10, 5, 0, "fake", 1.0, 1))


@pytest.fixture
def fake_engine(monkeypatch, tmp_path):
    compat_cases.install_fake_engine(pipeline, SessionStore, FakeEngine, tmp_path, monkeypatch.setattr,
                                     monkeypatch.setenv, lambda name: monkeypatch.delenv(name, raising=False))
    monkeypatch.setattr(pipeline, "_chat_store", SessionStore())
    monkeypatch.setattr(pipeline, "_dialogue", None)
    monkeypatch.setattr(pipeline.OpenAICompatClient, "from_settings", classmethod(lambda cls, s: GreetingLLM()))
    monkeypatch.setenv("C1_LLM_BASE_URL", "http://127.0.0.1:9/v1")     # never called: from_settings is patched


def _compare(actual, expected):
    assert len(actual) == len(expected)
    for a, e in zip(actual, expected):
        assert (a["path"], a.get("request")) == (e["path"], e.get("request"))
        assert a["status"] == e["status"], a["request"] if "request" in a else a["path"]
        assert a["body"] == e["body"], f"{a['path']} {a.get('request')}"


def test_golden_file_is_from_the_base_branch():
    assert GOLDEN["base"] == "c1/context-v2"
    assert [(r["path"], r["request"]) for r in GOLDEN["responses"]] == \
        [(p, b) for p, b in compat_cases.REQUESTS]


@pytest.mark.parametrize("mode", ["rules", "llm", "hybrid"])
def test_responses_are_byte_for_byte_the_base_branch(client, fake_engine, monkeypatch, mode):
    monkeypatch.setenv("C1_DIALOGUE_MODE", mode)
    _compare(compat_cases.run(client), GOLDEN["responses"])


@pytest.mark.parametrize("mode", ["rules", "hybrid"])
def test_chat_traffic_on_the_same_sessions_changes_nothing(client, fake_engine, monkeypatch, mode):
    monkeypatch.setenv("C1_DIALOGUE_MODE", mode)
    seen = set()
    original_post = client.post

    def post_with_chat(path, json):
        sid = json.get("session_id")
        if sid and json.get("text"):
            for text in (["hello"] if sid in seen else ["hello", json["text"]]):
                assert original_post("/v1/chat", json={"session_id": sid, "text": text}).status_code == 200
            seen.add(sid)
        return original_post(path, json=json)

    monkeypatch.setattr(client, "post", post_with_chat)
    _compare(compat_cases.run(client), GOLDEN["responses"])
    assert len(pipeline._chat_store) > 0        # the chat turns really ran


def test_stub_responses_are_byte_for_byte_the_base_branch(client, monkeypatch):
    monkeypatch.setenv("STUB_MODE", "true")
    for mode in ("rules", "llm", "hybrid"):
        monkeypatch.setenv("C1_DIALOGUE_MODE", mode)
        _compare(compat_cases.run_stub(client), GOLDEN["stub"])


def test_openapi_of_both_endpoints_is_unchanged():
    assert compat_cases.contract_openapi(app) == GOLDEN["openapi"]
