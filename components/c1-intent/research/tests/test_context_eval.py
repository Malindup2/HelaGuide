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


def test_interaction_ci_with_one_session_per_turn():
    full = np.ones(8)
    red = np.array([0, 0, 0, 0, 1, 1, 1, 1], float)
    high = np.array([1, 1, 1, 1, 0, 0, 0, 0], bool)
    bs = Bootstrap(list(range(8)), n_resamples=300, seed=3)
    lo, hi = bs.interaction_ci(full, red, high, ~high)
    assert lo == pytest.approx(1.0) and hi == pytest.approx(1.0)


# ---------------------------------------------------------------- end to end on fake predictions
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
