"""Properties of the algorithms, proved on the formulas themselves (no database, no model)."""
import math

import numpy as np
import pytest

from app.core.confidence import calibrate_lambda, confidence_from_evidence
from app.core.dedup import independence
from app.core.trust import account_credibility, msrt, reputation, visit_recency
from tests.helpers import make_settings

S = make_settings()
C0, THETA, K = S.c_base, S.theta_esc, S.policy_k
LAM = S.lam


# ------------------------------------------------------- calibration by design
def test_lambda_comes_from_the_policy():
    assert LAM == pytest.approx(math.log(0.9 / 0.5) / 3)
    assert LAM == pytest.approx(0.19593, abs=1e-5)
    assert calibrate_lambda(C0, THETA, K) == pytest.approx(LAM)


def test_policy_holds_k_perfect_reports_land_on_the_threshold():
    assert confidence_from_evidence(C0, K * 1.0, LAM) == pytest.approx(THETA)


def test_changing_the_policy_changes_lambda():
    assert calibrate_lambda(0.9, 0.5, 5) == pytest.approx(math.log(1.8) / 5)
    assert calibrate_lambda(0.9, 0.5, 5) < calibrate_lambda(0.9, 0.5, 3)


@pytest.mark.parametrize("bad", [(0.9, 0.95, 3), (0.9, 0.0, 3), (0.9, 0.5, 0)])
def test_calibration_rejects_nonsense(bad):
    with pytest.raises(ValueError):
        calibrate_lambda(*bad)


def test_monotone_and_bounded():
    es = [0, 0.3, 1, 2, 5, 20, 100]
    vals = [confidence_from_evidence(C0, e, LAM) for e in es]
    assert all(a >= b for a, b in zip(vals, vals[1:]))
    assert all(0 < v <= C0 for v in vals)


def test_single_report_cap():
    cap = C0 * (1 - math.exp(-LAM))
    assert C0 - confidence_from_evidence(C0, 1.0, LAM) == pytest.approx(cap)
    assert C0 - confidence_from_evidence(C0, 0.6, LAM) < cap          # a weaker report moves it less


def test_diminishing_returns():
    c = [confidence_from_evidence(C0, e, LAM) for e in range(5)]
    drops = [c[i] - c[i + 1] for i in range(4)]
    assert all(a > b > 0 for a, b in zip(drops, drops[1:]))


# ------------------------------------------------------------------ trust (MSRT)
def test_reputation_is_the_beta_posterior_mean():
    assert reputation(0, 0) == 0.5
    assert reputation(4, 1) == pytest.approx(5 / 7)
    assert reputation(7, 0) > reputation(1, 0) > reputation(0, 0) > reputation(0, 3)


def test_credibility_and_recency_curves():
    assert account_credibility(0, 30) == 0
    assert account_credibility(200, 30) > 0.99
    assert account_credibility(5, 30) < account_credibility(60, 30)
    assert visit_recency(0, 14) == 1
    assert visit_recency(30, 14) < visit_recency(3, 14)


def _t(a, b, age, gap, text="They charged 12000 at the office yesterday, not 11000.", claimed=12000.0, visit=True, mode="neutral"):
    s = make_settings(recency_missing_mode=mode)
    return msrt(s, a, b, age, gap, text, text, claimed, visit)


def test_established_specific_report_beats_new_vague_report():
    strong = _t(7, 0, 260, 0)
    weak = _t(0, 0, 3, None, text="fee was different", claimed=None, visit=False)
    assert strong.T > 0.85 and weak.T < 0.35 and strong.T > weak.T


def test_geometric_mean_is_more_cautious_than_arithmetic_when_one_signal_is_weak():
    r = _t(7, 0, 1, 0)                      # everything strong except a one-day-old account
    arithmetic = sum(w * v for w, v in zip(r.weights, (r.R, r.S, r.C, r.V)))
    assert r.T < arithmetic


def test_recency_is_optional():
    neutral = _t(2, 0, 90, None, visit=False, mode="neutral")
    dropped = _t(2, 0, 90, None, visit=False, mode="drop")
    assert neutral.v_imputed and dropped.v_imputed
    assert neutral.V == 0.5
    assert dropped.weights[3] == 0 and sum(dropped.weights) == pytest.approx(1)
    assert 0 < neutral.T <= 1 and 0 < dropped.T <= 1


def test_trust_always_between_zero_and_one():
    for a, b, age, gap in [(0, 0, 0, None), (50, 0, 900, 0), (0, 50, 1, 400)]:
        assert 0 < _t(a, b, age, gap).T <= 1


# ---------------------------------------------------------------- independence
def _row(reporter, emb, kind="dispute", rid="x"):
    return type("R", (), dict(reporter_id=reporter, report_kind=kind, embedding=np.array(emb, dtype=np.float32),
                              report_id=rid))()


def test_copy_is_discounted_and_a_different_report_is_not():
    earlier = [_row("u1", [1, 0])]
    I_copy, dup, _ = independence(S, np.array([1, 0], dtype=np.float32), "u2", "dispute", earlier)
    I_other, dup2, _ = independence(S, np.array([0, 1], dtype=np.float32), "u2", "dispute", earlier)
    assert I_copy == pytest.approx(S.rho) and dup == 1
    assert I_other == 1.0 and dup2 == 0


def test_two_copies_are_discounted_twice_and_own_reports_are_ignored():
    earlier = [_row("u1", [1, 0], rid="a"), _row("u3", [1, 0], rid="b")]
    I, dup, _ = independence(S, np.array([1, 0], dtype=np.float32), "u2", "dispute", earlier)
    assert I == pytest.approx(S.rho ** 2) and dup == 2
    I_self, _, _ = independence(S, np.array([1, 0], dtype=np.float32), "u1", "dispute", [_row("u1", [1, 0])])
    assert I_self == 1.0


def test_the_arithmetic_alternative_exists_only_for_ablation_and_excuses_a_weak_signal():
    assert make_settings().trust_mean == "geometric"                                   # the real system
    ar = make_settings(trust_mean="arithmetic")
    weak = dict(a=0, b=0, age_days=0.0, gap_days=None, text_en=VAGUE_TEXT, raw_text=VAGUE_TEXT, claimed_num=None, has_visit_date=False)
    assert msrt(ar, **weak).T > 2 * msrt(S, **weak).T                                  # one very weak signal is covered up
    flat = dict(weak, a=3, b=0, age_days=400.0, gap_days=0)                            # all signals strong: the means agree
    assert abs(msrt(ar, **flat).T - msrt(S, **flat).T) < 0.1


VAGUE_TEXT = "I think the passport fee is different from what your guide says."
