"""context_eval.py: CMI, McNemar, Holm, bootstrap, interaction maths and an end-to-end run on fake predictions.
Run from research/:  python -m pytest -q tests
"""
import json
import os

import numpy as np
import pytest

from context_eval import (Bootstrap, cmi, cmi_bucket, holm, interaction_samples, main, masked_mean, mcnemar_exact,
                          stratified,
                          script_bucket)

RESEARCH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------- CMI
def test_cmi_pure_sinhala_is_zero():
    assert cmi(["SI", "SI", "SI"]) == 0


def test_cmi_half_and_half_is_fifty():
    assert cmi(["SI", "EN", "SI", "EN"]) == 50


def test_cmi_named_entities_only_is_zero():
    assert cmi(["NE", "OTHER"]) == 0
    assert cmi(["NE"]) == 0


def test_cmi_ignores_ne_and_other():
    assert cmi(["SI", "EN", "NE", "OTHER"]) == 50       # n - u = 2
    assert cmi(["SI", "SI", "SI", "EN", "NE"]) == 25    # max 3 of 4


def test_buckets():
    assert cmi_bucket(["SI", "SI"], 0, 30) == "pure_si"
    assert cmi_bucket(["EN", "NE"], 0, 30) == "pure_en"
    assert cmi_bucket(["NE"], 0, 30) == "ne_other_only"
    assert cmi_bucket(["SI", "EN"], 50, 30) == "high_cmi"
    assert cmi_bucket(["SI", "SI", "SI", "EN"], 25, 30) == "low_cmi"
    assert cmi_bucket(["SI", "SI", "EN"], 30, 30) == "low_cmi"           # at the median -> low
    assert script_bucket("මගේ NIC එක") == "mixed_script"
    assert script_bucket("මගේ හැඳුනුම්පත") == "sinhala_script"
    assert script_bucket("mata NIC eka one") == "romanised"
    assert script_bucket("0771 123") == "no_letters"


# ---------------------------------------------------------------- tests and corrections
def test_mcnemar_known_tables():
    assert mcnemar_exact(1, 6) == pytest.approx(0.125)          # 2 * (C(7,0) + C(7,1)) / 2^7
    assert mcnemar_exact(0, 5) == pytest.approx(0.0625)         # 2 / 2^5
    assert mcnemar_exact(6, 1) == mcnemar_exact(1, 6)
    assert mcnemar_exact(0, 0) == 1.0
    assert mcnemar_exact(5, 5) == 1.0


def test_holm():
    assert holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
    assert holm([0.5]) == [0.5]


# ---------------------------------------------------------------- bootstrap
def test_bootstrap_is_deterministic():
    sid = [0, 0, 1, 1, 2, 3, 3, 4]
    v = [1, 0, 1, 1, 0, 1, 0, 1]
    a, b = Bootstrap(sid, seed=7), Bootstrap(sid, seed=7)
    assert a.mean_ci(v) == b.mean_ci(v)
    assert np.array_equal(a.w, b.w)
    assert not np.array_equal(a.w, Bootstrap(sid, seed=8).w)


def test_bootstrap_resamples_whole_sessions():
    # each session is all-correct or all-wrong, so every resampled mean is a mix of whole sessions
    sid = [0, 0, 0, 1, 1, 1]
    v = [1, 1, 1, 0, 0, 0]
    bs = Bootstrap(sid, n_resamples=200, seed=1)
    means = bs._ratio(v, None)
    assert set(np.round(means, 6)) <= {0.0, 0.5, 1.0}


# ---------------------------------------------------------------- H3 interaction
def test_interaction_math_tiny_example():
    # turns 0-1 high CMI, turns 2-3 monolingual
    full = np.array([1, 1, 1, 1], float)
    red = np.array([1, 0, 1, 1], float)          # the reduced strategy loses one high-CMI turn
    high = np.array([1, 1, 0, 0], bool)
    mono = ~high
    # drop(high) = 1 - 0.5 = 0.5, drop(mono) = 1 - 1 = 0 -> difference 0.5
    assert interaction_samples(masked_mean, full, red, high, mono) == pytest.approx(0.5)
    # same drop in both buckets -> no interaction
    red2 = np.array([1, 0, 1, 0], float)
    assert interaction_samples(masked_mean, full, red2, high, mono) == pytest.approx(0.0)


def test_stratified_interaction_removes_turn_position_effect():
    # first turns: 2 high, 2 mono, the reduced strategy loses nothing. Follow-up turns: 2 high, 6 mono, it loses half
    # of each bucket. Within each position the drop is the same for high and mono (no interaction), but pooling all
    # turns shows one, because mono turns are mostly follow-ups.
    first = np.array([1] * 4 + [0] * 8, bool)
    follow = ~first
    high = np.array([1, 1, 0, 0] + [1, 1, 0, 0, 0, 0, 0, 0], bool)
    mono = ~high
    full = np.ones(12)
    red = np.array([1, 1, 1, 1] + [1, 0, 1, 0, 1, 0, 1, 0], float)
    pooled = interaction_samples(masked_mean, full, red, high, mono)
    assert pooled == pytest.approx(0.25 - 0.375)                # drop high 1/4, drop mono 3/8
    count = lambda m: float(np.sum(m))
    diff, dh, dm = stratified(masked_mean, count, full, red, high, mono, [first, follow])
    assert float(diff) == pytest.approx(0.0)
    # weights 4 (first) and 8 (follow-up): drop high = (4 * 0 + 8 * 0.5) / 12
    assert float(dh) == pytest.approx(8 * 0.5 / 12) and float(dm) == pytest.approx(8 * 0.5 / 12)
    bs = Bootstrap(list(range(12)), n_resamples=200, seed=5)
    lo, hi = bs.stratified_ci(full, red, high, mono, [first, follow])
    assert lo <= 0 <= hi


def test_permutation_test_detects_an_effect_and_not_a_null():
    from context_eval import Permutations
    labels = ["high_cmi"] * 20 + ["pure_si"] * 20 + ["pure_en"] * 20
    strata = [("s", False)] * 30 + [("s", True)] * 30            # positions mixed into both strata
    pt = Permutations(labels, strata, n=2000, seed=1)
    effect = np.array([1.0] * 20 + [0.0] * 40)                    # the reduced strategy loses only high-CMI turns
    obs, p = pt.test(effect[:, None])
    assert obs[0] == pytest.approx(1.0) and p[0] < 0.001
    null = np.random.default_rng(0).integers(0, 2, 60).astype(float)
    assert np.array_equal(pt.test(null[:, None])[1], Permutations(labels, strata, n=2000, seed=1).test(null[:, None])[1])


def test_permutation_false_positive_rate_on_null_data_is_under_10_percent():
    """30 null fake data sets (no code-mixing effect within a turn position), intent accuracy, the H3 verdict rule:
    the permutation test should say "supported" in about 5% of model x test-set families, and never above 10%."""
    if not os.path.exists(os.path.join(RESEARCH, "data", "seed_all.json")):
        pytest.skip("data/seed_all.json missing (python experiments/prepare_labelstudio.py)")
    import h3_calibration as hc
    cwd = os.getcwd()
    os.chdir(RESEARCH)
    try:
        results = [hc._one(s, scopes=("permutation",), metrics=(("intent_acc", "intent_ok"),)) for s in range(1, 31)]
    finally:
        os.chdir(cwd)
    rates = {r["test_set"]: r for r in hc.summarise(results)}
    for ts in ("synthetic", "heldout"):          # the sets with >= 30 turns in both buckets
        assert rates[ts]["families"] == 60
        assert rates[ts]["says_supported"] < 0.10, rates[ts]


def test_h3_bound_sentence_uses_the_widest_adjusted_ci():
    from context_eval import h3_bound_line
    rows = [{"diff": -0.10, "ci_bonferroni_low": -0.25, "ci_bonferroni_high": 0.05},
            {"diff": 0.02, "ci_bonferroni_low": -0.08, "ci_bonferroni_high": 0.12}]
    text = h3_bound_line(rows, 0.081)
    assert "rule out an interaction larger than 25.0 JGA points" in text
    assert "-10.0 to +2.0" in text and "8.1%" in text
    assert h3_bound_line([{"diff": None, "ci_bonferroni_low": None, "ci_bonferroni_high": None}]) is None


def test_deployed_line_is_xlmr_window_3_only():
    from context_eval import deployed_line
    rows = [{"strategy": "window_3", "diff": -0.010, "ci95_low": -0.091, "ci95_high": 0.077},
            {"strategy": "window_2", "diff": -0.105, "ci95_low": -0.235, "ci95_high": 0.024}]
    text = deployed_line("xlmr", rows)
    assert "XLM-R window_3" in text and "single pre-specified comparison" in text
    assert "[-9.10, +7.70]" in text and "larger than 9.10 JGA points" in text
    assert deployed_line("tfidf", rows) is None


def test_interaction_ci_with_one_session_per_turn():
    full = np.ones(8)
    red = np.array([0, 0, 0, 0, 1, 1, 1, 1], float)
    high = np.array([1, 1, 1, 1, 0, 0, 0, 0], bool)
    bs = Bootstrap(list(range(8)), n_resamples=300, seed=3)
    lo, hi = bs.interaction_ci(full, red, high, ~high)
    assert lo == pytest.approx(1.0) and hi == pytest.approx(1.0)


# ---------------------------------------------------------------- convergence check
def _hist(final_loss, best_dev):
    return [{"epoch": 1, "loss": 1.0, "dev": best_dev - 0.05}, {"epoch": 2, "loss": final_loss, "dev": best_dev}]


def test_convergence_rule_needs_both_conditions():
    from context_eval import convergence_check
    runs_json = {
        "seed1/window_2": {"xlmr": {"history": _hist(0.05, 0.70)}, "tfidf": {"gold": {}}},
        "seed2/window_2": {"xlmr": {"history": _hist(0.06, 0.66)}},
        "seed3/window_2": {"xlmr": {"history": _hist(0.56, 0.46)}},     # 10x loss AND 0.22 dev gap -> flagged
        "seed1/summary": {"xlmr": {"history": _hist(0.05, 0.80)}},
        "seed2/summary": {"xlmr": {"history": _hist(0.07, 0.78)}},
        "seed3/summary": {"xlmr": {"history": _hist(0.50, 0.75)}},      # high loss, dev fine -> not flagged
        "seed1/window_3": {"xlmr": {"history": _hist(0.03, 0.74)}},
        "seed2/window_3": {"xlmr": {"history": _hist(0.03, 0.73)}},
        "seed3/window_3": {"xlmr": {"history": _hist(0.04, 0.60)}},     # dev low, loss fine -> not flagged
    }
    keys = [(m, st, sd) for st in ("window_2", "summary", "window_3") for sd in (1, 2, 3) for m in ("xlmr", "tfidf")]
    rows = {(r["model"], r["strategy"], r["seed"]): r for r in convergence_check(runs_json, keys)}
    assert rows[("xlmr", "window_2", 3)]["flagged"]
    assert rows[("xlmr", "window_2", 3)]["loss_ratio"] == pytest.approx(0.56 / 0.055, abs=0.01)
    assert [k for k, r in rows.items() if r["flagged"]] == [("xlmr", "window_2", 3)]
    assert rows[("tfidf", "window_2", 1)]["note"].startswith("no training history")


# ---------------------------------------------------------------- H2: primary NI CI, secondary McNemar
def test_h2_verdict_and_conflicts():
    from context_eval import h2_verdict
    ni = lambda lo, hi, tok=20: {"ci95_low": lo, "ci95_high": hi, "tokens": tok, "tokens_reference": 50}
    mc = lambda diff, p: {"diff": diff, "p_holm": p}
    assert h2_verdict(ni(-0.03, 0.02), mc(-0.01, 0.6), 0.05)[:3] == ("supported", "not significantly worse", "agree")
    v = h2_verdict(ni(-0.04, -0.01), mc(-0.03, 0.01), 0.05)          # within the margin, but McNemar: worse
    assert v[0] == "supported" and v[2] == "conflicting" and "margin" in v[3]
    v = h2_verdict(ni(-0.15, -0.07), mc(-0.10, 0.20), 0.05)          # CI below the margin, McNemar: no difference
    assert v[0] == "not supported" and v[2] == "conflicting"
    assert h2_verdict(ni(-0.08, 0.02), mc(-0.03, 0.3), 0.05)[:3] == ("inconclusive", "not significantly worse", "agree")
    assert h2_verdict(ni(0.05, 0.16), mc(0.10, 0.0001), 0.05)[:3] == ("supported", "significantly better", "agree")
    assert h2_verdict(ni(-0.01, 0.02, tok=60), mc(0.0, 1.0), 0.05)[0] == "not supported"     # not cheaper


def test_two_level_bootstrap_with_one_seed_equals_session_bootstrap():
    sid = [0, 0, 1, 1, 2, 2, 3, 3]
    a, b = np.array([[1, 0, 1, 1, 0, 1, 1, 1]], float), np.array([[1, 1, 1, 1, 1, 1, 0, 1]], float)
    bs = Bootstrap(sid, n_resamples=300, seed=4)
    assert bs.two_level_diff_ci(a, b) == bs.diff_ci(a[0], b[0])
    # more seeds: deterministic, and seeds may differ in number between the two strategies
    a3 = np.array([[1, 0, 1, 1, 0, 1, 1, 1], [1, 1, 1, 0, 0, 1, 1, 1], [0, 0, 1, 1, 0, 1, 1, 1]], float)
    assert bs.two_level_diff_ci(a3, b) == Bootstrap(sid, n_resamples=300, seed=4).two_level_diff_ci(a3, b)


# ---------------------------------------------------------------- end to end on fake predictions
def test_end_to_end_with_unequal_seeds_and_a_flagged_run(tmp_path):
    from fixtures.fake_context_preds import make_fake_preds
    if not os.path.exists(os.path.join(RESEARCH, "data", "seed_all.json")):
        pytest.skip("data/seed_all.json missing (python experiments/prepare_labelstudio.py)")
    preds = tmp_path / "context_v2" / "preds"
    cwd = os.getcwd()
    os.chdir(RESEARCH)
    try:
        make_fake_preds(str(preds), seeds=(1, 2, 3), max_sessions=3)
        for m in ("xlmr", "tfidf"):                                    # window_3 has seeds 1-2 only
            (preds / f"{m}__window_3__seed3.jsonl").unlink()
        runs_json = {f"seed{sd}/{st}": {"xlmr": {"history": _hist(0.6 if (st, sd) == ("summary", 3) else 0.05,
                                                                  0.4 if (st, sd) == ("summary", 3) else 0.75)}}
                     for st in ("current_only", "window_2", "window_3", "keyword_summary", "structured_state",
                                "summary", "full_history") for sd in (1, 2, 3)}
        (tmp_path / "context_v2" / "runs.json").write_text(json.dumps(runs_json), encoding="utf-8")
        main(["--preds-dir", str(preds), "--out-dir", str(tmp_path / "out"), "--no-plots"])
    finally:
        os.chdir(cwd)
    res = json.loads((tmp_path / "out" / "context_jga_results.json").read_text(encoding="utf-8"))
    assert res["settings"]["seeds_per_run"]["xlmr/window_3"] == [1, 2]
    assert res["metrics"]["xlmr/window_3/fresh"]["seeds"] == 2 and len(res["metrics"]["xlmr/window_3/fresh"]["jga"]) == 3
    assert res["convergence_check"]["flagged"] == [["xlmr", "summary", 3]]
    assert res["sensitivity_excluding_flagged"]["seeds_per_run"]["xlmr/summary"] == [1, 2]
    ni = [r for r in res["h2_noninferiority"] if r["model"] == "xlmr" and r["strategy"] == "window_3"]
    assert ni and all(r["seeds"] == 2 and r["seeds_reference"] == 3 for r in ni)
    assert {r["bucket"] for r in res["token_ratio"]} >= {"all", "pure_si", "pure_en", "mixed"}
    summary = (tmp_path / "out" / "summary.md").read_text(encoding="utf-8")
    for text in ("primary: NI", "secondary: McNemar", "Token tax", "Convergence check",
                 "defined after seeing the failed runs", "flagged runs excluded", "Seeds differ between runs"):
        assert text in summary, text
    assert (tmp_path / "out" / "convergence_check.csv").stat().st_size > 0


def test_end_to_end_on_fake_predictions(tmp_path):
    from fixtures.fake_context_preds import make_fake_preds
    if not os.path.exists(os.path.join(RESEARCH, "data", "seed_all.json")):
        pytest.skip("data/seed_all.json missing (python experiments/prepare_labelstudio.py)")
    cwd = os.getcwd()
    os.chdir(RESEARCH)                       # context_eval reads data/ relative to research/
    try:
        make_fake_preds(str(tmp_path / "preds"), seeds=(1, 2), max_sessions=4)
        main(["--preds-dir", str(tmp_path / "preds"), "--out-dir", str(tmp_path / "out"), "--no-plots"])
        with pytest.raises(SystemExit):      # never overwrites without --overwrite
            main(["--preds-dir", str(tmp_path / "preds"), "--out-dir", str(tmp_path / "out"), "--no-plots"])
    finally:
        os.chdir(cwd)
    out = tmp_path / "out"
    res = json.loads((out / "context_jga_results.json").read_text(encoding="utf-8"))
    assert res["settings"]["fake_predictions"] is True
    assert set(res["settings"]["test_sets"]) == {"gold", "synthetic", "fresh", "heldout"}
    m = res["metrics"]["xlmr/full_history/fresh"]
    assert 0 <= m["jga"][0] <= m["intent_acc"][0] <= 1                # JGA needs the intent right too
    summary = (out / "summary.md").read_text(encoding="utf-8")
    for h in ("H1", "H2", "H3", "H4", "Scale claim", "FAKE PREDICTIONS"):
        assert h in summary
    for f in ("stats_tests.csv", "cmi_breakdown.csv", "interaction_tests.csv"):
        assert (out / f).stat().st_size > 0
