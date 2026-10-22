"""POST /v1/chat: the dialogue layer behind C1_DIALOGUE_MODE, with the fake engine and a scripted LLM (no network)."""
import jsonschema
import pytest

from app.core import pipeline
from app.core.llm_client import FakeLLM, LLMError
from app.main import app

BIRTH = "birth_cert_copy"


def chat(client, text, sid="anon-chat"):
    r = client.post("/v1/chat", json={"session_id": sid, "text": text})
    assert r.status_code == 200, r.text
    return r.json()


def details(client, text, sid, bot_text=None):
    r = client.post("/v1/intent/details", json={"session_id": sid, "text": text, "bot_text": bot_text})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def llm(monkeypatch, real_mode):
    """hybrid mode with a scripted LLM: append replies (dicts or exceptions) to the returned FakeLLM."""
    fake = FakeLLM()
    monkeypatch.setenv("C1_DIALOGUE_MODE", "hybrid")
    monkeypatch.setattr(pipeline.OpenAICompatClient, "from_settings", classmethod(lambda cls, s: fake))
    return fake


def reply(intent=BIRTH, act="slot_answer", slots=None, text="Hari!", **kw):
    return {"reply": text, "dialogue_act": act, "active_intent": intent, "tasks": [BIRTH] if intent else [],
            "slot_updates": slots or {}, **kw}


# ---------------------------------------------------------------- rules mode (default)
def test_rules_mode_is_the_engines_own_conversation(client, real_mode, monkeypatch):
    """Default mode: the reply is the engine's, and C1 feeds its own last reply back as bot_text, like the demo."""
    monkeypatch.delenv("C1_DIALOGUE_MODE", raising=False)
    real_mode.update({"I need a birth certificate": (BIRTH, 0.95), "my mom": (BIRTH, 0.95),
                      "kurunegala": (BIRTH, 0.95), "for school": (BIRTH, 0.9)})
    bot = None
    for text in ("I need a birth certificate", "my mom", "kurunegala", "for school"):
        c = chat(client, text, sid="anon-r1")
        d = details(client, text, sid="anon-r2", bot_text=bot)
        bot = d["reply"]
        assert (c["dialogue_mode"], c["dialogue_source"], c["llm_usage"], c["dialogue_act"]) == \
            ("rules", "rules", None, None)
        for key in ("reply", "internal_intent", "active_intent", "route", "slots", "missing_slots", "ready",
                    "turn_id", "state_version", "assumed_slots", "language", "intent_source"):
            assert c[key] == d[key], key
    assert c["slots"] == {"applicant_for": "parent", "district": "Kurunegala", "purpose": "school admission"}


def test_chat_sessions_are_separate_from_intent_sessions(client, real_mode):
    real_mode["I need a birth certificate"] = (BIRTH, 0.95)
    chat(client, "I need a birth certificate", sid="anon-same")
    assert chat(client, "I need a birth certificate", sid="anon-same")["turn_id"] == 1
    r = client.post("/v1/intent", json={"session_id": "anon-same", "text": "I need a birth certificate"})
    assert r.json()["turn_id"] == 0         # the contract endpoint has not seen this session


def test_contract_projection_validates(client, real_mode, intent_schema):
    real_mode["mata passport ekak ganna one"] = ("passport_new", 0.9)
    c = chat(client, "mata passport ekak ganna one")
    jsonschema.validate(c["intent"], intent_schema)
    assert c["intent"]["entities"]["service_id"] == "svc:passport"
    assert c["intent"]["session_id"] == "anon-chat"


# ---------------------------------------------------------------- hybrid mode
def test_hybrid_turn(client, llm, real_mode, intent_schema):
    real_mode["my mom's, from Kurunegala, for business registration"] = (BIRTH, 0.9)
    llm.replies.append(reply(act="new_request", text="Got it. Shall I confirm?", ready_to_confirm=True, slots={
        "applicant_for": "parent", "district": "Kurunegala", "purpose": "business registration"}))
    c = chat(client, "my mom's, from Kurunegala, for business registration")
    assert (c["dialogue_mode"], c["dialogue_source"], c["dialogue_act"], c["reply"]) == \
        ("hybrid", "llm", "new_request", "Got it. Shall I confirm?")
    assert c["slots"] == {"applicant_for": "parent", "district": "Kurunegala", "purpose": "other"}
    assert c["raw_slots"] == {"purpose": "business registration"}
    assert (c["ready"], c["ready_to_confirm"], c["route"], c["tasks"]) == (True, True, "orchestration", [BIRTH])
    assert c["llm_usage"]["calls"] == 1 and c["llm_usage"]["model"] == "fake-llm"
    assert c["llm_proposed"] == 3 and c["error"] is None
    jsonschema.validate(c["intent"], intent_schema)


def test_hybrid_unsupported_service_keeps_the_task(client, llm, real_mode):
    real_mode.update({"I need a birth certificate": (BIRTH, 0.95), "i need a driving license": (BIRTH, 0.48)})
    llm.replies += [reply(act="new_request"),
                    reply(intent="unsupported_service", act="new_request", slots={"service_mentioned": "driving license"},
                          text="Sorry, driving licences aren't covered. Shall we finish the birth certificate?")]
    chat(client, "I need a birth certificate")
    c = chat(client, "i need a driving license")
    assert (c["internal_intent"], c["route"], c["active_intent"], c["tasks"]) == \
        ("unsupported_service", "fallback", BIRTH, [BIRTH])
    assert c["intent"]["intent"] == "apply_service"     # the contract keeps projecting the open birth certificate


def test_rejections_and_conflicts_are_returned(client, llm, real_mode):
    real_mode["Matale, for school"] = (BIRTH, 0.9)
    llm.replies.append(reply(slots={"district": "Kandy", "purpose": "bank", "travel_date": "2026-12-15"}))
    c = chat(client, "Matale, for school")
    assert sorted((x["slot"], x["kept"]) for x in c["conflicts"]) == [("district", "rules"), ("purpose", "llm")]
    assert {(x["field"], x["reason"], x["source"]) for x in c["rejections"]} == \
        {("travel_date", "slot_not_in_intent", "llm")}


def test_llm_failure_is_a_rules_fallback_not_an_error(client, llm, real_mode):
    real_mode["mata uppenna ekak one, Galle"] = (BIRTH, 0.9)
    llm.replies.append(LLMError("HTTP 503: busy"))
    c = chat(client, "mata uppenna ekak one, Galle")
    assert (c["dialogue_source"], c["error"], c["llm_usage"]) == ("rules_fallback", "LLMError", None)
    assert c["slots"] == {"applicant_for": "self", "district": "Galle"}
    assert c["reply"]


def test_log_has_no_message_text_or_values(client, llm, real_mode, caplog):
    real_mode["for my mother, in Kurunegala"] = (BIRTH, 0.9)
    llm.replies.append(reply(slots={"applicant_for": "parent", "district": "Kurunegala"}))
    with caplog.at_level("INFO", logger="c1-intent"):
        chat(client, "for my mother, in Kurunegala")
    assert "chat session=anon-chat turn=0 mode=hybrid source=llm" in caplog.text
    assert "mother" not in caplog.text and "Kurunegala" not in caplog.text


# ---------------------------------------------------------------- settings, stub mode, schema
def test_manager_is_reused_until_settings_change(client, real_mode, monkeypatch):
    monkeypatch.setenv("C1_DIALOGUE_MODE", "rules")
    first = pipeline.dialogue_manager()
    assert pipeline.dialogue_manager() is first and first.llm is None
    monkeypatch.setenv("C1_DIALOGUE_MODE", "hybrid")
    second = pipeline.dialogue_manager()
    assert second is not first and second.settings.mode == "hybrid" and second.llm is not None


def test_bad_dialogue_settings_answer_503(client, real_mode, monkeypatch):
    monkeypatch.setenv("C1_DIALOGUE_MODE", "chatty")
    r = client.post("/v1/chat", json={"session_id": "anon-chat", "text": "hi"})
    assert r.status_code == 503
    assert "C1_DIALOGUE_MODE" in r.json()["detail"]


def test_stub_mode(client, monkeypatch, intent_schema):
    monkeypatch.setenv("STUB_MODE", "true")
    r = client.post("/v1/chat", json={"session_id": "anon-test", "text": "mata passport ekak ganna one"})
    assert r.status_code == 200
    c = r.json()
    assert (c["dialogue_mode"], c["dialogue_source"], c["active_intent"]) == ("rules", "rules", "passport_new")
    jsonschema.validate(c["intent"], intent_schema)


def test_rejects_bot_text_and_unknown_fields(client):
    for extra in ({"bot_text": "Who is it for?"}, {"user_name": "x"}):
        r = client.post("/v1/chat", json={"session_id": "anon-chat", "text": "hi", **extra})
        assert r.status_code == 422


def test_openapi_lists_chat_as_c1_internal():
    op = app.openapi()["paths"]["/v1/chat"]["post"]
    assert "c1-internal" in op["tags"]         # same tags as /v1/intent/details
    assert op["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("/ChatResponse")
