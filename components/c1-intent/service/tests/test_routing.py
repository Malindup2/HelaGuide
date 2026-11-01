"""Routes on the C1-only /v1/intent/details endpoint, and what /v1/intent sends for the same turns."""
import logging

import jsonschema
import pytest


def details(client, text, session_id="anon-1", bot_text=None):
    r = client.post("/v1/intent/details", json={"session_id": session_id, "text": text, "bot_text": bot_text})
    assert r.status_code == 200, r.text
    return r.json()


def test_feedback_complaint_routes_to_trust_verification(client, real_mode, intent_schema):
    real_mode["oya kiwwa office eka saturday open kiyala"] = ("feedback_complaint", 0.9)
    d = details(client, "oya kiwwa office eka saturday open kiyala")
    assert d["internal_intent"] == "feedback_complaint"
    assert d["route"] == "trust_verification"
    assert d["intent"]["intent"] == "unknown"
    jsonschema.validate(d["intent"], intent_schema)


def test_unsupported_service_is_contract_unknown(client, real_mode, intent_schema):
    real_mode["driving licence ekak ganna one"] = ("unsupported_service", 0.9)
    d = details(client, "driving licence ekak ganna one")
    assert d["route"] == "fallback"
    assert d["slots"]["service_mentioned"] == "driving license"
    r = client.post("/v1/intent", json={"session_id": "anon-2", "text": "driving licence ekak ganna one"})
    assert r.json()["intent"] == "unknown"
    assert r.json()["entities"]["service_id"] is None
    jsonschema.validate(r.json(), intent_schema)


@pytest.mark.parametrize("intent, route", [
    ("nic_replace_lost", "orchestration"),
    ("general_question", "orchestration"),
    ("out_of_scope", "none"),
    ("unknown", "none"),
])
def test_other_routes(client, real_mode, intent, route):
    real_mode["some text"] = (intent, 0.9)
    assert details(client, "some text")["route"] == route


def test_details_shares_sessions_with_intent(client, real_mode):
    client.post("/v1/intent", json={"session_id": "anon-1", "text": "mata ID eka nathi una"})
    d = details(client, "Matara")
    assert d["turn_id"] == 1
    assert d["slots"] == {"district": "Matara"}
    assert d["missing_slots"] == ["urgency"]


def test_bot_text_is_used(client, real_mode):
    details(client, "mata ID eka nathi una")
    d = details(client, "ow", bot_text="District eka Colombo neda?")
    assert d["slots"]["district"] == "Colombo"


def test_language_fields(client, real_mode):
    d = details(client, "mata ID එක nathi una")
    assert d["code_switched"] is True
    assert d["language"] == "mixed"
    assert [t["word"] for t in d["language_tags"]] == ["mata", "ID", "එක", "nathi", "una"]


def test_log_line_has_no_message_text(client, real_mode, caplog):
    with caplog.at_level(logging.INFO, logger="c1-intent"):
        details(client, "mata ID eka nathi una Matara")
    lines = [r.getMessage() for r in caplog.records if r.name == "c1-intent"]
    assert any("route=orchestration" in line and "session=anon-1" in line for line in lines)
    assert not any("nathi" in line or "Matara" in line for line in lines)


def test_details_in_stub_mode(client, monkeypatch, intent_schema):
    monkeypatch.setenv("STUB_MODE", "true")
    d = details(client, "mata passport ekak ganna one", session_id="anon-test")
    assert d["route"] == "orchestration"
    assert d["intent"]["session_id"] == "anon-test"
    assert d["intent"]["entities"]["service_id"] == "svc:passport"
    jsonschema.validate(d["intent"], intent_schema)


def test_details_rejects_unknown_fields(client):
    r = client.post("/v1/intent/details", json={"session_id": "anon-1", "text": "hi", "user_name": "x"})
    assert r.status_code == 422
