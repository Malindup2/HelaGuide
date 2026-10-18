"""The whole flow, on SQLite with the stand-in embedder: both paths, confidence, warnings, versions."""
import pytest

from app.core.evaluate import run_grounding
from app.core.pipeline import Pipeline
from tests.helpers import make_settings
from tests.pipeline_fixtures import ds, pipe, run, settings  # noqa: F401

FACT = "svc:passport:fee:normal"
STORY = ["ft-A1", "ft-A2", "ft-A3", "ft-A4", "ft-A5", "ft-A6"]       # six citizens, all in their own words


# --------------------------------------------------------------- both paths ---
def test_both_paths_feed_the_same_fact(pipe, ds):
    a = run(pipe, ds, "ft-A1")           # free text (the main path)
    b = run(pipe, ds, "fb-A2")           # the team's contract message (kept for compatibility)
    assert a.path == "freetext" and b.path == "structured"
    assert a.fact_id == b.fact_id == FACT
    assert pipe.exposure.explain(FACT)["report_count"] == 2


def test_confidence_falls_with_each_credible_dispute_but_by_less_each_time(pipe, ds):
    confs = [0.9]
    for mid in ["ft-A1", "ft-A2", "ft-A6"]:
        confs.append(run(pipe, ds, mid).confidence["new"])
    drops = [confs[i] - confs[i + 1] for i in range(len(confs) - 1)]
    assert confs == sorted(confs, reverse=True)
    assert all(d > 0 for d in drops)


def test_the_percentage_is_always_available_but_the_warning_waits_for_two_drops(pipe, ds):
    r1 = run(pipe, ds, "ft-A1")
    assert r1.exposure["confidence_pct"] == round(100 * r1.confidence["new"])
    assert r1.exposure["warning_code"] == "NONE"
    assert pipe.exposure.contract_trust(FACT).status == "ok"
    r2 = run(pipe, ds, "ft-A2")
    assert r2.exposure["warning_code"] == "LOW_CONFIDENCE"
    assert pipe.exposure.contract_trust(FACT).status == "disputed"


def test_a_strong_story_ends_below_the_flag_level_with_a_strong_warning(pipe, ds):
    for mid in STORY:
        r = run(pipe, ds, mid)
    assert r.confidence["new"] < 0.5 and r.confidence["status"] == "flagged"
    assert r.exposure["warning_code"] == "VERIFY_BEFORE_VISIT"


def test_a_copied_report_is_discounted(pipe, ds):
    run(pipe, ds, "ft-A1")
    copy = run(pipe, ds, "ft-A4")        # nearly the same words, different citizen
    assert copy.independence["dup_count"] == 1
    assert copy.independence["I"] == pytest.approx(0.6)
    other = run(pipe, ds, "ft-A2")
    assert other.independence["I"] == 1.0


def test_a_supporting_report_raises_confidence_again(pipe, ds):
    for mid in ["ft-A1", "ft-A2", "ft-A3", "ft-A4"]:
        before = run(pipe, ds, mid)
    support = run(pipe, ds, "ft-A5")
    assert support.kind == "support"
    assert support.confidence["new"] > before.confidence["new"]


def test_same_message_twice_is_ignored(pipe, ds):
    run(pipe, ds, "ft-A1")
    n = pipe.repo.count_reports()
    again = run(pipe, ds, "ft-A1")
    assert again.state == "duplicate_message" and pipe.repo.count_reports() == n


def test_one_citizen_cannot_add_weight_by_repeating_themselves(pipe, ds):
    run(pipe, ds, "ft-A1")
    base = pipe.exposure.explain(FACT)["confidence"]
    again = dict(ds.freetext["ft-A1"], message_id="ft-A1-again", timestamp="2026-10-20T11:00:00Z")
    pipe.process_freetext(again)
    assert pipe.exposure.explain(FACT)["confidence"] == pytest.approx(base)


def test_citizens_who_disagree_are_recorded_not_resolved(pipe, ds):
    for mid in ["ft-B1", "ft-B2", "ft-B3", "ft-B4"]:
        run(pipe, ds, mid)
    e = pipe.exposure.explain("svc:nic:fee:replacement")
    assert e["claims_disagree"] is True
    assert set(e["claim_groups"]) == {"num:1500", "num:2000"}


def test_reporter_trust_comes_from_reputation_and_age(pipe, ds):
    strong = run(pipe, ds, "ft-A6")      # long-standing, reliable reporter, visited today
    pipe2 = Pipeline.build(make_settings(), reset=True)
    pipe2.load_reporters(); pipe2.sync_facts()
    weak = run(pipe2, ds, "ft-A3")       # five-day-old account, no visit date
    assert strong.trust["T"] > 0.9 > 0.5 > weak.trust["T"]
    assert weak.trust["v_imputed"] and not strong.trust["v_imputed"]


# ------------------------------------------------------------- grounding ---
def test_session_and_questions(ds):
    p = Pipeline.build(make_settings(tau_f=0.30), reset=True)
    p.load_reporters(); p.sync_facts()
    first = run(p, ds, "ft-C11")                   # names the service
    follow = run(p, ds, "ft-C12")                  # does not: the session remembers
    assert first.fact_id == follow.fact_id == "svc:death_certificate:fee:certified_copy"
    assert follow.grounding["service_source"] == "session"


def test_unclear_messages_are_parked_not_scored(pipe, ds):
    r = run(pipe, ds, "ft-D1")
    assert r.state == "clarification_needed" and r.reason == "service_unclear"
    assert pipe.repo.count_reports() == 0
    assert len(pipe.repo.list_unresolved()) == 1
    assert pipe.exposure.explain(FACT)["confidence_pct"] == 90


def test_a_document_that_is_not_in_the_graph_is_reported_as_missing(ds):
    p = Pipeline.build(make_settings(tau_miss_cos=0.25), reset=True)
    p.load_reporters(); p.sync_facts()
    r = run(p, ds, "ft-C10")
    assert r.state == "no_matching_fact" and r.grounding["phrase_similarity"] < 0.25


def test_unknown_fact_id_on_the_structured_path(pipe):
    r = pipe.process_structured({"feedback_id": "fb-x", "session_id": "anon-0001", "fact_id": "svc:passport:fee:ghost",
                                 "text": "fee wrong", "submitted_at": "2026-10-25T10:00:00Z"})
    assert r.state == "no_matching_fact" and r.reason == "unknown_fact_id"


def test_missing_translation_asks_a_question_instead_of_guessing(ds):
    p = Pipeline.build(make_settings(), reset=True)
    p.load_reporters(); p.sync_facts()
    p.normaliser.cache = {}                          # simulate: no cache, no live translation
    r = run(p, ds, "ft-A3")                          # Singlish message with a service hint
    assert r.state == "clarification_needed" and r.reason == "translation_unavailable"


def test_grounding_accuracy_on_all_labelled_messages(pipe, ds):
    rows = run_grounding(pipe, ds)
    assert len(rows) == 43
    assert sum(r["ok"] for r in rows) / len(rows) >= 0.85   # stand-in embedder; the real model is tuned separately


# ---------------------------------------------------------------- versions ---
def test_new_version_resets_confidence_and_judges_old_reports(pipe, ds):
    for mid in STORY:
        run(pipe, ds, mid)
    old_v = pipe.repo.current_version(FACT)
    rep_before = {r.reporter_id: (r.a, r.b) for r in pipe.repo.all_reporters()}

    pipe.source.publish_updates(pipe.s.data_dir / "c2_facts_updates.json")
    res = [r for r in pipe.sync_facts() if r.fact_id == FACT][0]

    assert res.new_version and res.initial_confidence == pytest.approx(0.9)
    new_v = pipe.repo.current_version(FACT)
    assert new_v.valid_from > old_v.valid_from and new_v.value_text == "12000"
    outcome = {v.reporter_id: v.outcome for v in res.verdicts}
    assert outcome["anon-0001"] == "verified_by_source"
    assert outcome["anon-0005"] == "contradicted_by_source"                               # supported the old value
    rep_after = {r.reporter_id: (r.a, r.b) for r in pipe.repo.all_reporters()}
    assert rep_after["anon-0001"][0] == rep_before["anon-0001"][0] + 1
    assert rep_after["anon-0004"][0] == pytest.approx(rep_before["anon-0004"][0] + 0.6)   # a copy earns less
    assert rep_after["anon-0005"][1] == pytest.approx(rep_before["anon-0005"][1] + 0.5)
    e = pipe.exposure.explain(FACT)
    assert e["confidence_pct"] == 90 and e["warning_code"] == "VERIFIED_BY_SOURCE"
    assert pipe.exposure.contract_trust(FACT).status == "verified_correction"


def test_lazy_registration_of_a_fact_c3_has_not_seen_yet(settings):
    p = Pipeline.build(settings, reset=True)                      # no sync: the registry is empty
    r = p.process_structured({"feedback_id": "fb-1", "session_id": "anon-0001", "fact_id": FACT,
                              "text": "The fee is 12,000 now.", "proposed_value": 12000,
                              "submitted_at": "2026-10-20T10:00:00Z"})
    assert r.state == "grounded" and p.repo.current_version(FACT) is not None


def test_the_story_gives_the_same_numbers_through_free_text_only(pipe, ds):
    """76 -> 65 -> 60 -> 55 -> 60 -> 50 percent, with every report typed as free text and no hints."""
    pcts = [run(pipe, ds, mid).confidence["pct"] for mid in STORY]
    assert pcts == [76, 65, 60, 55, 60, 50]


def test_the_contract_message_still_gives_the_same_numbers(pipe, ds):
    """Compatibility: the team's per-fact message (names the fact) reaches the same confidence."""
    pcts = [run(pipe, ds, mid).confidence["pct"] for mid in ["ft-A1", "fb-A2", "ft-A3", "fb-A4", "ft-A5", "ft-A6"]]
    assert pcts == [76, 65, 60, 55, 60, 50]
