"""scripts/replay_log.py and the rigid-log regression file, with the fake engine and FakeLLM (no model, no network)."""
import importlib.util
import json
from pathlib import Path

import pytest

from app.core import pipeline
from app.core.dialogue import DialogueManager
from app.core.llm_client import FakeLLM
from app.core.settings import DialogueSettings
from tests.conftest import FakeEngine

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "replay_log.py"
spec = importlib.util.spec_from_file_location("replay_log", SCRIPT)
replay_log = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay_log)

LOG = json.loads(replay_log.DEFAULT_LOG.read_text(encoding="utf-8"))
TURNS = LOG["turns"]
BIRTH = "birth_cert_copy"
# XLM-R as in the demo log: stuck on birth_cert_copy (the fake engine reads the last message only)
STICKY = {"Hi": ("unknown", 0.0), "I need a birth certifcate": (BIRTH, 0.95), "my mom": (BIRTH, 0.95),
          "kurunegala": (BIRTH, 0.95), "business reg purpose": (BIRTH, 0.61), "school": (BIRTH, 0.52),
          "also i need to get a driving licese": (BIRTH, 0.72), "i need a driving license": (BIRTH, 0.48)}


def engine():
    return FakeEngine(dict(STICKY), 0.35, pipeline.unsupported_service_fallback)


def answer(intent=BIRTH, act="slot_answer", slots=None, tasks=(BIRTH,)):
    return {"reply": "Hari!", "dialogue_act": act, "active_intent": intent, "tasks": list(tasks),
            "slot_updates": slots or {}}


# what a good LLM says for each turn of the log
GOOD = [answer(None, "greet", tasks=()), answer(act="new_request"), answer(slots={"applicant_for": "parent"}),
        answer(slots={"district": "Kurunegala"}), answer(slots={"purpose": "business reg"}), answer(),
        answer(act="correction", slots={"purpose": "school admission"}),
        *[answer("unsupported_service", "new_request", {"service_mentioned": "driving license"})] * 3]


def test_log_file_is_the_demo_log():
    assert [t["text"] for t in TURNS] == [
        "Hi", "I need a birth certifcate", "my mom", "kurunegala", "business reg purpose", "business reg purpose",
        "school", "also i need to get a driving licese", "i need a driving license", "i need a driving license"]
    for t in TURNS:     # every expectation is one the checker knows
        replay_log.check(t["expect_hybrid"], type("R", (), {"slots": {}, "tasks": [], "reply": "x",
                                                             "internal_intent": "", "route": "", "active_intent": None,
                                                             "dialogue_act": None})())


def test_hybrid_with_a_good_llm_meets_every_expectation():
    results = replay_log.replay(TURNS, DialogueManager(FakeLLM(*GOOD), DialogueSettings(mode="hybrid")),
                                engine().new_session)
    s = replay_log.summarise("hybrid", TURNS, results)
    assert (s["expect_met"], s["turns_met"], s["llm_answered"], s["fallbacks"]) == (s["expect_total"], 10, 10, 0)
    assert results[4].raw_slots == {"purpose": "business reg"} and results[4].slots["purpose"] == "other"
    assert results[7].route == "fallback" and results[7].tasks == [BIRTH]


def test_rules_mode_shows_the_rigid_behaviour():
    results = replay_log.replay(TURNS, DialogueManager(None, DialogueSettings(mode="rules")), engine().new_session)
    s = replay_log.summarise("rules", TURNS, results)
    assert s["expect_met"] < s["expect_total"] and s["llm_answered"] == 0
    assert all(r.internal_intent != "unsupported_service" for r in results[7:])     # the sticky intent of the log


def test_checks_name_what_failed():
    r = type("R", (), {"slots": {"purpose": "other"}, "tasks": [BIRTH], "reply": "", "route": "orchestration",
                       "internal_intent": BIRTH, "active_intent": BIRTH, "dialogue_act": None})()
    got = replay_log.check({"slots": {"purpose": "school admission"}, "slots_present": ["district"],
                            "tasks_include": [BIRTH], "route": "fallback", "reply": "nonempty"}, r)
    assert [what for what, ok in got if not ok] == ["purpose=school admission", "district filled", "route=fallback",
                                                    "reply"]
    with pytest.raises(ValueError):
        replay_log.check({"nonsense": 1}, r)


def test_pause_only_between_llm_turns():
    waits = []
    replay_log.replay(TURNS[:3], DialogueManager(FakeLLM(*GOOD[:3]), DialogueSettings(mode="hybrid")),
                      engine().new_session, pause=4, sleep=waits.append)
    assert waits == [4, 4]
    waits.clear()
    replay_log.replay(TURNS[:3], DialogueManager(None, DialogueSettings(mode="rules")), engine().new_session,
                      pause=4, sleep=waits.append)
    assert waits == []


def test_table_has_reply_source_and_checks():
    results = replay_log.replay(TURNS, DialogueManager(FakeLLM(*GOOD), DialogueSettings(mode="hybrid")),
                                engine().new_session)
    text = replay_log.table(TURNS, results)
    head = text.splitlines()[0]
    assert head.split()[:5] == ["#", "Message", "Intent", "XLM-R", "said"]
    assert head.index("Intent") < head.index("XLM-R said") < head.index("Route")
    assert "birth_cert_copy 0.95" in text.splitlines()[4]          # turn 1: XLM-R's own prediction
    assert "reply [llm] Hari!" in text and "expect ok" in text and "FAIL" not in text
