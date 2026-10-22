"""DialogueManager with the fake engine (real Session and tracker, scripted XLM-R) and FakeLLM: no model, no network."""
import json
from datetime import date

import pytest

from app.core import pipeline
from app.core.dialogue import DialogueManager
from app.core.engine import ASK
from app.core.llm_client import FakeLLM, LLMError
from app.core.settings import DialogueSettings
from app.core.validator import OTHER
from tests.conftest import FakeEngine

BIRTH, PASSPORT = "birth_cert_copy", "passport_new"
TODAY = date(2026, 10, 22)


def llm_reply(intent=BIRTH, act="slot_answer", slots=None, reply="Hari!", tasks=None, asks=None, ready=False):
    return {"reply": reply, "dialogue_act": act, "active_intent": intent, "tasks": tasks or [],
            "slot_updates": slots or {}, "asks_slot": asks, "ready_to_confirm": ready}


@pytest.fixture
def chat():
    """-> make(intents, *llm_replies, mode="hybrid", **settings) -> (chat session, fake llm)"""
    def make(intents, *replies, mode="hybrid", **settings):
        engine = FakeEngine(intents, 0.35, pipeline.unsupported_service_fallback)
        llm = FakeLLM(*replies)
        dm = DialogueManager(llm, DialogueSettings(mode=mode, **settings), today=lambda: TODAY)
        return dm.new_session(engine.new_session()), llm
    return make


def user_content(llm, call=-1):
    return json.loads(llm.calls[call][1][-1]["content"])


# ---------------------------------------------------------------- the six required cases
def test_several_slots_from_one_message(chat):
    text = "my mom's, she's from Kurunegala, for business registration"
    c, llm = chat({text: (BIRTH, 0.9)}, llm_reply(slots={
        "applicant_for": "parent", "district": "Kurunegala", "purpose": "business registration"}, ready=True))
    r = c.step(text)
    assert r.dialogue_source == "llm"
    assert r.slots == {"applicant_for": "parent", "district": "Kurunegala", "purpose": OTHER}
    assert r.raw_slots == {"purpose": "business registration"}
    assert (r.missing_slots, r.ready, r.ready_to_confirm, r.route) == ([], True, True, "orchestration")
    # the rules tracker read "my" as self; applicant_for is not extractive, so the LLM's parent wins
    assert [(x["slot"], x["rules"], x["kept"]) for x in r.conflicts] == [("applicant_for", "self", "llm")]
    assert r.llm_usage["calls"] == 1 and r.llm_usage["prompt_tokens"] > 0


def test_greeting_changes_no_slot(chat):
    c, _ = chat({"Kurunegala": (BIRTH, 0.9)},
                llm_reply(slots={"district": "Kurunegala"}),
                llm_reply(act="greet", reply="Hello again! Who is the certificate for?"))
    c.step("Kurunegala")
    r = c.step("hello")
    assert r.reply == "Hello again! Who is the certificate for?"
    assert r.slots == {"district": "Kurunegala"}
    assert (r.internal_intent, r.route, r.active_intent, r.rejections) == ("unknown", "none", BIRTH, [])


def test_greeting_with_info_still_fills_slots(chat):
    c, _ = chat({"I need a birth certificate": (BIRTH, 0.95), "hi, I'm from Galle": (BIRTH, 0.5)},
                llm_reply(act="new_request"),
                llm_reply(act="greet", reply="Hi! Galle, got it. Who is it for?", slots={"district": "Galle"}))
    c.step("I need a birth certificate")
    r = c.step("hi, I'm from Galle")
    assert r.slots["district"] == "Galle"
    assert (r.internal_intent, r.route) == (BIRTH, "orchestration")
    assert r.rejections == []


def test_first_greeting_with_no_request(chat):
    c, _ = chat({}, llm_reply(intent=None, act="greet", reply="Hi! How can I help?"))
    r = c.step("Hi")
    assert (r.reply, r.internal_intent, r.active_intent, r.route, r.rejections) == \
        ("Hi! How can I help?", "unknown", None, "none", [])


def test_invalid_intent_falls_back_to_xlmr(chat):
    c, _ = chat({"Galle": (BIRTH, 0.9)}, llm_reply(intent="birth_certificate_please", slots={"district": "Galle"}))
    r = c.step("Galle")
    assert (r.internal_intent, r.intent_source, r.active_intent) == (BIRTH, "nlu_fallback", BIRTH)
    assert r.slots["district"] == "Galle"
    assert ("active_intent", "unknown_intent") in {(x["field"], x["reason"]) for x in r.rejections}


def test_invalid_district_is_rejected(chat):
    c, _ = chat({"from Narnia": (BIRTH, 0.9)}, llm_reply(slots={"district": "Narnia"}))
    r = c.step("from Narnia")
    assert "district" not in r.slots
    assert "district" in r.missing_slots
    assert ("district", "not_a_district") in {(x["field"], x["reason"]) for x in r.rejections}


def test_applicant_for_is_protected(chat):
    c, _ = chat({"for my mother": (BIRTH, 0.9), "my son also needs one": (BIRTH, 0.9)},
                llm_reply(slots={"applicant_for": "parent"}),
                llm_reply(slots={"applicant_for": "child"}),
                )
    c.step("for my mother")
    r = c.step("my son also needs one")
    assert r.slots["applicant_for"] == "parent"
    sources = {(x["reason"], x["source"]) for x in r.rejections}
    assert ("protected_without_correction", "llm") in sources


def test_applicant_for_correction_is_allowed(chat):
    c, _ = chat({"for my mother": (BIRTH, 0.9), "sorry, it's for my son": (BIRTH, 0.9)},
                llm_reply(slots={"applicant_for": "parent"}),
                llm_reply(act="correction", slots={"applicant_for": "child"}))
    c.step("for my mother")
    assert c.step("sorry, it's for my son").slots["applicant_for"] == "child"


def test_rules_protection_setting_off_lets_the_tracker_change_it(chat):
    intents = {"for my mother": (BIRTH, 0.9), "my son also needs one": (BIRTH, 0.9)}
    replies = (llm_reply(slots={"applicant_for": "parent"}), llm_reply())
    on, _ = chat(intents, *replies)
    off, _ = chat(intents, *replies, protect_applicant_for=False)
    for c in (on, off):
        c.step("for my mother")
    assert on.step("my son also needs one").slots["applicant_for"] == "parent"
    assert off.step("my son also needs one").slots["applicant_for"] == "child"     # the tracker's own value


def test_llm_error_falls_back_to_rules(chat):
    c, _ = chat({"mata uppenna ekak one, Galle": (BIRTH, 0.9)}, LLMError("connection refused"))
    r = c.step("mata uppenna ekak one, Galle")
    assert (r.dialogue_source, r.error) == ("rules_fallback", "LLMError")
    assert r.slots == {"applicant_for": "self", "district": "Galle"}    # the rules tracker's result
    assert r.reply == r.state["reply"] and r.reply
    assert r.llm_usage is None


def test_bad_llm_json_shape_falls_back_or_is_contained(chat):
    c, _ = chat({"Galle": (BIRTH, 0.9)}, {"reply": 5, "slot_updates": "Galle", "active_intent": BIRTH})
    r = c.step("Galle")
    assert r.dialogue_source == "llm"
    assert r.slots == {"district": "Galle"}         # the rules value; the LLM's bad fields are rejected
    assert {x["reason"] for x in r.rejections} >= {"empty_reply", "not_an_object"}


# ---------------------------------------------------------------- tasks, switches, unsupported services
def test_unsupported_service_keeps_the_open_task(chat):
    c, _ = chat({"I need a birth certificate": (BIRTH, 0.95), "also i need a driving licese": (BIRTH, 0.72)},
                llm_reply(act="new_request", tasks=[BIRTH]),
                llm_reply(intent="unsupported_service", act="new_request", tasks=[BIRTH],
                          slots={"service_mentioned": "driving licence"},
                          reply="Sorry, driving licences aren't covered yet. Shall we finish the birth certificate?"))
    c.step("I need a birth certificate")
    r = c.step("also i need a driving licese")
    assert (r.internal_intent, r.route, r.active_intent, r.tasks) == \
        ("unsupported_service", "fallback", BIRTH, [BIRTH])
    assert r.slots == {"service_mentioned": "driving license"}
    assert "birth certificate" in r.reply


def test_sticky_xlmr_intent_does_not_win_over_a_validated_llm_switch(chat):
    """Turns 7-9 of the rigid log: XLM-R stays on birth_cert_copy for a driving licence request."""
    sticky = {"I need a birth certificate": (BIRTH, 0.95), "my mom": (BIRTH, 0.95),
              "i need a driving license": (BIRTH, 0.48), "ok, back to the certificate. Kurunegala": (BIRTH, 0.9)}
    c, _ = chat(sticky,
                llm_reply(act="new_request", tasks=[BIRTH]),
                llm_reply(slots={"applicant_for": "parent"}, tasks=[BIRTH]),
                llm_reply(intent="unsupported_service", act="new_request", tasks=[BIRTH],
                          slots={"service_mentioned": "driving license"},
                          reply="Sorry, I can't help with driving licences yet. Shall we finish the birth certificate?"),
                llm_reply(slots={"district": "Kurunegala"}, tasks=[BIRTH]))
    c.step("I need a birth certificate")
    c.step("my mom")
    r = c.step("i need a driving license")
    assert (r.internal_intent, r.intent_model_output, r.route) == ("unsupported_service", BIRTH, "fallback")
    assert (r.active_intent, r.tasks) == (BIRTH, [BIRTH])
    assert r.state["active_slots"] == {"applicant_for": "parent"}     # the open task is kept as it was
    back = c.step("ok, back to the certificate. Kurunegala")
    assert (back.internal_intent, back.route, back.active_intent, back.tasks) == \
        (BIRTH, "orchestration", BIRTH, [BIRTH])
    assert back.slots == {"applicant_for": "parent", "district": "Kurunegala"}
    assert back.missing_slots == ["purpose"]


def test_sticky_xlmr_new_core_request_and_switch_back(chat):
    sticky = {"my daughter's birth certificate": (BIRTH, 0.95), "I also need a new passport": (BIRTH, 0.7),
              "back to the birth certificate, Galle": (BIRTH, 0.9)}
    c, _ = chat(sticky,
                llm_reply(act="new_request", slots={"applicant_for": "child"}, tasks=[BIRTH]),
                llm_reply(intent=PASSPORT, act="new_request", tasks=[PASSPORT, BIRTH]),
                llm_reply(act="new_request", slots={"district": "Galle"}, tasks=[BIRTH, PASSPORT]))
    c.step("my daughter's birth certificate")
    r = c.step("I also need a new passport")
    assert (r.active_intent, r.route, r.tasks) == (PASSPORT, "orchestration", [PASSPORT, BIRTH])
    back = c.step("back to the birth certificate, Galle")
    assert (back.active_intent, back.tasks) == (BIRTH, [BIRTH, PASSPORT])
    assert back.slots == {"applicant_for": "child", "district": "Galle"}       # its own slots restored


def test_llm_task_the_engine_does_not_have_is_kept_pending(chat):
    c, _ = chat({"birth certificate for me, and later a passport": (BIRTH, 0.9)},
                llm_reply(act="new_request", slots={"applicant_for": "self"}, tasks=[BIRTH, PASSPORT, "nope"]))
    r = c.step("birth certificate for me, and later a passport")
    assert (r.active_intent, r.tasks) == (BIRTH, [BIRTH, PASSPORT])
    assert r.state["pending_requests"] == [
        {"intent": PASSPORT, "service_id": "svc:passport", "slots": {}, "conditions": {}, "variant_pending": False}]
    assert ("tasks", "unknown_intent") in {(x["field"], x["reason"]) for x in r.rejections}


def test_new_request_switches_and_keeps_the_old_one_pending(chat):
    c, _ = chat({"Galle": (BIRTH, 0.9), "and a passport for my daughter": (BIRTH, 0.6)},
                llm_reply(slots={"district": "Galle"}),
                llm_reply(intent=PASSPORT, act="new_request", slots={"applicant_for": "child"}))
    c.step("Galle")
    r = c.step("and a passport for my daughter")
    assert (r.active_intent, r.tasks) == (PASSPORT, [PASSPORT, BIRTH])
    assert r.slots["applicant_for"] == "child"
    assert r.state["pending_requests"][0]["slots"] == {"district": "Galle"}


def test_llm_value_overrides_non_extractive_rules_and_extractive_rules_win(chat):
    c, _ = chat({"Matale, for school": (BIRTH, 0.9)}, llm_reply(slots={"district": "Kandy", "purpose": "bank"}))
    r = c.step("Matale, for school")
    assert (r.slots["district"], r.slots["purpose"]) == ("Matale", "bank")
    assert sorted((x["slot"], x["kept"]) for x in r.conflicts) == [("district", "rules"), ("purpose", "llm")]


def test_ready_to_confirm_claim_needs_every_slot(chat):
    c, _ = chat({"Galle": (BIRTH, 0.9)}, llm_reply(slots={"district": "Galle"}, ready=True))
    r = c.step("Galle")
    assert (r.ready, r.ready_to_confirm) == (False, False)
    assert ("ready_to_confirm", "slots_missing") in {(x["field"], x["reason"]) for x in r.rejections}


# ---------------------------------------------------------------- prompt contents
def test_hybrid_sends_hints_and_state(chat):
    c, llm = chat({"Galle": (BIRTH, 0.9), "for my daughter": (BIRTH, 0.8)},
                  llm_reply(slots={"district": "Galle"}, asks="applicant_for"), llm_reply())
    c.step("Galle")
    c.step("for my daughter")
    system, messages = llm.calls[1]
    assert "Today is 2026-10-22 (Thursday)" in system and "YYYY-MM-DD" in system
    assert [m["role"] for m in messages] == ["user", "assistant", "user"]
    content = user_content(llm)
    assert content["message"] == "for my daughter"
    assert content["state"]["slots"] == {"district": "Galle"}
    assert content["state"]["missing_slots"] == ["applicant_for", "purpose"]
    hints = content["nlu_hints"]
    assert (hints["xlmr_intent"], hints["tracker_intent"]) == (BIRTH, BIRTH)
    assert hints["tracker_slot_updates"] == {"applicant_for": "child"}


def test_asks_slot_gives_the_tracker_its_own_question(chat):
    c, _ = chat({"Galle": (BIRTH, 0.9)}, llm_reply(slots={"district": "Galle"}, asks="purpose",
                                                    reply="What do you need the certificate for?"))
    c.step("Galle")
    assert c.last_bot_text == ASK["purpose"]["en"]


def test_history_window(chat):
    intents = {t: (BIRTH, 0.9) for t in ("a", "b", "c")}
    c, llm = chat(intents, llm_reply(), llm_reply(), llm_reply(), history_turns=1)
    for t in ("a", "b", "c"):
        c.step(t)
    assert [m["content"] for m in llm.calls[2][1][:-1]] == ["b", "Hari!"]


def test_llm_mode_has_no_hints_and_no_rules_slots(chat):
    c, llm = chat({"Galle": (BIRTH, 0.9)}, llm_reply(), mode="llm")
    r = c.step("Galle")
    assert "nlu_hints" not in user_content(llm)
    assert "district" not in r.slots            # the rules tracker found Galle, but llm mode ignores it
    assert r.dialogue_source == "llm"


def test_rules_mode_never_calls_the_llm(chat):
    c, llm = chat({"mata uppenna ekak one": (BIRTH, 0.9)}, mode="rules")
    r = c.step("mata uppenna ekak one")
    assert llm.calls == []
    assert (r.dialogue_source, r.reply) == ("rules", r.state["reply"])
