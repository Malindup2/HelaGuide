"""dialogue_eval.py end to end with the service's fake engine (real Session and tracker, scripted XLM-R) and a fake
LLM: no model, no network. Fictional dialogues. Run from research/:  python -m pytest -q tests
"""
import importlib.util
import json
from pathlib import Path

import pytest

import dialogue_eval as de
from app.core import pipeline
from app.core.dialogue import DialogueManager
from app.core.llm_client import LLMError, LLMResult, LLMUsage
from app.core.settings import DialogueSettings

_spec = importlib.util.spec_from_file_location("service_conftest", de.SERVICE / "tests" / "conftest.py")
_conftest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_conftest)
FakeEngine = _conftest.FakeEngine

PP, BC = "passport_new", "birth_cert_copy"
DIALOGUES = [
    {"dialogue_id": "t1", "turns": [
        {"speaker": "user", "text": "I want a new passport", "state": {"intent": PP, "slots": {}, "labelled": True}},
        {"speaker": "bot", "text": "Who is it for?"},
        {"speaker": "user", "text": "for my daughter",
         "state": {"intent": PP, "slots": {"applicant_for": "child"}, "labelled": True}},
        {"speaker": "bot", "text": "When are you travelling?"},
        {"speaker": "user", "text": "around the start of next month",
         "state": {"intent": PP, "slots": {"applicant_for": "child", "travel_date": "next month"}, "labelled": True}},
    ]},
    {"dialogue_id": "t2", "turns": [
        {"speaker": "user", "text": "I need a birth certificate copy", "state": {"intent": BC, "slots": {},
                                                                              "labelled": True}},
        {"speaker": "bot", "text": "Who is it for?"},
        {"speaker": "user", "text": "actually a passport first", "state": {"intent": PP, "slots": {},
                                                                         "labelled": True}},
    ]},
]
XLMR = {"I want a new passport": (PP, 0.95), "for my daughter": (PP, 0.9), "around the start of next month": (PP, 0.9),
        "I need a birth certificate copy": (BC, 0.95), "actually a passport first": (BC, 0.6)}


def reply(intent, slots=None, raw=None, act="slot_answer"):
    return {"reply": "Hari!", "dialogue_act": act, "active_intent": intent, "tasks": [intent],
            "slot_updates": slots or {}, **({"slot_raw": raw} if raw else {})}


PERFECT = {"I want a new passport": reply(PP, act="new_request"),
           "for my daughter": reply(PP, {"applicant_for": "child"}),
           "around the start of next month": reply(PP, {"travel_date": "2026-11-01"}, {"travel_date": "next month"}),
           "I need a birth certificate copy": reply(BC, act="new_request"),
           "actually a passport first": reply(PP, act="new_request")}


class ByMessageLLM:
    """Answers by the message text (so any order of runs and turns works); records every call."""

    def __init__(self, answers, errors=None):
        self.answers, self.errors, self.calls = answers, list(errors or []), []

    def complete_json(self, system, messages):
        self.calls.append(messages)
        if self.errors:
            raise self.errors.pop(0)
        msg = json.loads(messages[-1]["content"])["message"]
        return LLMResult(dict(self.answers[msg]), LLMUsage(100, 10, 0, "fake", 5.0, 1, 130))


def engine():
    return FakeEngine(dict(XLMR), 0.35, pipeline.unsupported_service_fallback)


def run(settings, answers=PERFECT, runs=1, errors=None, checkpoint=None, sleeps=None):
    eng, inner = engine(), ByMessageLLM(answers, errors)
    llm = de.EvalLLM(inner, pause=0, sleep=(sleeps.append if sleeps is not None else lambda s: None))

    def make_manager(setting):
        return DialogueManager(llm if setting != "rules" else None, DialogueSettings(mode=setting))

    results, stopped = de.evaluate(DIALOGUES, settings, runs, make_manager, eng.new_session, llm, checkpoint,
                                   log=lambda *a: None)
    return results, stopped, inner, llm


# ---------------------------------------------------------------- scoring through dst_eval's functions
def test_perfect_llm_scores_one_and_dates_use_the_users_words():
    results, stopped, _, _ = run(["llm"])
    r = results["llm"][0]
    assert not stopped
    assert (r["turns"], r["jga"], r["intent_acc"], r["slot_micro"]["f1"]) == (5, 1.0, 1.0, 1.0)
    assert r["dates"] == {"words": 0, "raw": 1, "iso_fallback": 0}
    assert r["intent_switch"] == {"turns": 1, "correct": 1, "accuracy": 1.0, "note": "few turns: anecdotal"}
    assert (r["llm"]["hallucinated_slot_rate"], r["llm"]["failed"], r["llm"]["answered"]) == (0.0, 0, 5)
    assert r["tokens_per_answered_turn"]["provider_total_tokens"] == 130


def test_iso_date_without_words_is_scored_as_iso_and_counted():
    answers = {**PERFECT, "around the start of next month": reply(PP, {"travel_date": "2026-11-01"})}
    r = run(["llm"], answers)[0]["llm"][0]
    assert r["dates"] == {"words": 0, "raw": 1, "iso_fallback": 0}       # the message has date words: kept
    answers = {**PERFECT, "around the start of next month": reply(PP, {"travel_date": "2026-11-01"},
                                                                  {"travel_date": "soonish"})}
    assert run(["llm"], answers)[0]["llm"][0]["dates"]["raw"] == 1


def test_hallucinated_slot_and_slot_rejections():
    answers = {**PERFECT, "I want a new passport": reply(PP, {"applicant_for": "self", "district": "Galle"},
                                                         act="new_request")}
    r = run(["llm"], answers)[0]["llm"][0]
    # turn 1: applicant_for=self is accepted but not in the gold state (a hallucination); district is not a
    # passport slot (rejected). Turn 2: the right "child" is then rejected too, since a known applicant_for only
    # changes on a correction, so the error carries through the dialogue. Turn 3: travel_date, correct.
    assert (r["llm"]["llm_slots_set"], r["llm"]["hallucinated_slots"], r["llm"]["hallucinated_slot_rate"]) == \
        (2, 1, 0.5)
    assert (r["llm"]["slot_updates_proposed"], r["llm"]["slot_updates_rejected"]) == (4, 2)
    assert r["jga"] == 0.4                             # all of t1 wrong, t2 right


def test_rules_runs_once_and_without_llm():
    results, _, inner, _ = run(["rules", "llm"], runs=2)
    assert [len(results["rules"]), len(results["llm"])] == [1, 2]
    assert results["rules"][0]["llm"]["turns"] == 0 and len(inner.calls) == 2 * 5


def test_each_turn_sees_the_gold_history_not_the_systems_replies():
    _, _, inner, _ = run(["llm"])
    third = inner.calls[2]          # "around the start of next month"
    assert [m["content"] for m in third[:-1]] == [
        "I want a new passport", "Who is it for?", "for my daughter", "When are you travelling?"]


# ---------------------------------------------------------------- failures, quota, checkpoint
def test_failed_turn_counts_as_wrong_and_the_sensitivity_number_leaves_its_dialogue_out():
    sleeps = []
    errors = [LLMError("HTTP 503: busy")] * 4         # first turn: 1 try + 3 eval retries, then failed
    r = run(["llm"], errors=errors, sleeps=sleeps)[0]["llm"][0]
    assert sleeps == [30, 60, 60]
    assert (r["llm"]["failed"], r["llm"]["fallback"], r["llm"]["failed_rate"]) == (1, 0, 0.2)
    assert r["jga"] == 0.8                             # the failed turn is wrong
    assert r["jga_without_failed_dialogues"] == 1.0    # dialogue t1 left out


def test_retry_delay_from_the_provider_is_used_when_longer():
    sleeps = []
    msg = 'HTTP 429: {"error": {"message": "slow down", "details": [{"retryDelay": "45s"}]}}'
    run(["llm"], errors=[LLMError(msg)], sleeps=sleeps)
    assert sleeps == [45.0]


def test_client_errors_other_than_429_fail_at_once():
    sleeps = []
    r = run(["llm"], errors=[LLMError("HTTP 400: bad request")], sleeps=sleeps)[0]["llm"][0]
    assert sleeps == [] and r["llm"]["failed"] == 1


def test_quota_stops_the_run_and_the_checkpoint_resumes_it(tmp_path):
    cp = str(tmp_path / "cp.jsonl")
    quota = LLMError("HTTP 429: You exceeded your current quota, please check your plan")
    # dialogue t1 runs (3 calls), then t2's first call hits the quota twice (once retried after 65 s)
    sleeps = []
    eng, inner = engine(), ByMessageLLM(PERFECT)
    llm = de.EvalLLM(inner, pause=0, sleep=sleeps.append)
    real_complete = inner.complete_json

    def complete(system, messages):
        if json.loads(messages[-1]["content"])["message"] == "I need a birth certificate copy":
            raise quota
        return real_complete(system, messages)

    inner.complete_json = complete
    make = lambda s: DialogueManager(llm, DialogueSettings(mode=s))      # noqa: E731
    results, stopped = de.evaluate(DIALOGUES, ["llm"], 1, make, eng.new_session, llm, cp, log=lambda *a: None)
    assert stopped and results == {} and sleeps == [65]
    assert [json.loads(l)["dialogue_id"] for l in Path(cp).read_text(encoding="utf-8").splitlines()] == ["t1"]

    results, stopped, inner2, _ = run(["llm"], checkpoint=cp)               # resume: only t2 is run
    assert not stopped and results["llm"][0]["turns"] == 5
    assert [json.loads(c[-1]["content"])["message"] for c in inner2.calls] == [
        "I need a birth certificate copy", "actually a passport first"]


def test_unreachable_endpoint_stops_the_run():
    results, stopped, _, llm = run(["llm"], errors=[LLMError("ConnectError: refused")])
    assert stopped and results == {} and llm.stop == "endpoint unreachable"


def test_pacing_between_call_starts():
    sleeps, now = [], [0.0]
    llm = de.EvalLLM(ByMessageLLM(PERFECT), pause=4, sleep=sleeps.append, clock=lambda: now[0])
    msg = [{"role": "user", "content": json.dumps({"message": "for my daughter"})}]
    llm.complete_json("s", msg)
    now[0] = 1.5
    llm.complete_json("s", msg)
    assert sleeps == [2.5]


# ---------------------------------------------------------------- helpers
def test_schema_slots_keep_the_intents_schema_and_score_dates_on_words():
    slots, dates = de.schema_slots(PP, {"applicant_for": "child", "district": "Galle", "town": "Moratuwa",
                                        "travel_date": "2026-11-01"}, {"travel_date": "next month"})
    assert slots == {"applicant_for": "child", "travel_date": "next month"}
    assert dates == {"words": 0, "raw": 1, "iso_fallback": 0}
    assert de.schema_slots(PP, {"travel_date": "mid December"}, {})[1]["words"] == 1
    assert de.schema_slots(PP, {"travel_date": "2026-11-01"}, {})[1]["iso_fallback"] == 1


def test_plan_runs_rules_once_then_interleaves():
    assert de.plan(["rules", "llm", "hybrid"], 2) == [(1, "rules"), (1, "llm"), (1, "hybrid"), (2, "llm"),
                                                     (2, "hybrid")]


def test_aggregate_mean_sd_and_range():
    runs = [{"jga": 0.8, "slot_jga": 0.9}, {"jga": 0.6, "slot_jga": 0.9}, {"jga": 0.7, "slot_jga": 0.9}]
    agg = de.aggregate(runs)
    assert agg["jga"] == {"mean": 0.7, "sd": 0.1, "min": 0.6, "max": 0.8, "n_runs": 3}
    assert agg["hallucinated_slot_rate"]["mean"] is None


def test_print_table_runs():
    lines = []
    de.print_table({"llm": de.aggregate([run(["llm"])[0]["llm"][0]])}, log=lines.append)
    assert lines[0].split()[:3] == ["setting", "runs", "JGA"] and lines[1].split()[:3] == ["llm", "1", "1.000"]


@pytest.mark.parametrize("model, slug", [("gemini-3.5-flash-lite", "gemini-3.5-flash-lite"), ("qwen2.5:7b", "qwen2.5-7b")])
def test_model_slug(model, slug):
    assert de.model_slug(model) == slug
