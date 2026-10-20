"""
Module B, Algorithm 1: the multi-signal report trust score (MSRT).

    T(r) = R^w1 * S^w2 * C^w3 * V^w4          (weighted geometric mean, weights sum to 1)

    R  reporter reputation   (a+1)/(a+b+2)        STANDARD: posterior mean of a Beta(1,1) prior
                                                  (Beta Reputation System, Josang & Ismail 2002)
    S  report specificity    weighted checklist   CUSTOM: which cues, which weights
    C  account credibility   1 - exp(-age/tau_c)  standard curve, CUSTOM constant
    V  visit recency         exp(-gap/tau_v)      standard curve, CUSTOM constant; optional

A geometric mean is used on purpose: one very weak signal (a brand-new account) pulls the whole
score down, which is the cautious behaviour wanted when the thing being protected is a
government knowledge graph.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from app.core.config import C3Settings
from app.core.lexicon import specificity_features

EPS = 1e-3


@dataclass
class TrustResult:
    T: float
    R: float
    S: float
    C: float
    V: float
    v_imputed: bool
    weights: tuple[float, float, float, float]
    features: dict


def reputation(a: float, b: float) -> float:
    return (a + 1.0) / (a + b + 2.0)


def specificity(settings: C3Settings, feats: dict[str, bool]) -> float:
    return (settings.spec_value * feats["value"] + settings.spec_when * feats["when"] +
            settings.spec_where * feats["where"] + settings.spec_detail * feats["detail"])


def account_credibility(age_days: float, tau_c: float) -> float:
    return 1.0 - math.exp(-max(age_days, 0.0) / tau_c)


def visit_recency(gap_days: float, tau_v: float) -> float:
    return math.exp(-max(gap_days, 0.0) / tau_v)


def msrt(settings: C3Settings, a: float, b: float, age_days: float, gap_days: float | None,
         text_en: str, raw_text: str, claimed_num: float | None, has_visit_date: bool) -> TrustResult:
    feats = specificity_features(text_en, raw_text, claimed_num, has_visit_date)
    R = reputation(a, b)
    S = specificity(settings, feats)
    C = account_credibility(age_days, settings.tau_c)
    w = [settings.w_r, settings.w_s, settings.w_c, settings.w_t]
    if gap_days is None:
        if settings.recency_missing_mode == "drop":
            V, v_imputed = 1.0, True
            w[3] = 0.0
        else:
            V, v_imputed = 0.5, True                 # neutral value, recorded as imputed
    else:
        V, v_imputed = visit_recency(gap_days, settings.tau_v), False
    total = sum(w)
    w = [x / total for x in w]
    vals = [max(x, EPS) for x in (R, S, C, V)]
    if settings.trust_mean == "arithmetic":                  # ablation only: a weak signal can then be outvoted
        T = sum(wi * v for wi, v in zip(w, vals))
    else:                                                    # the real thing: a weighted geometric mean
        T = math.exp(sum(wi * math.log(v) for wi, v in zip(w, vals) if wi > 0))
    return TrustResult(T=T, R=R, S=S, C=C, V=V, v_imputed=v_imputed, weights=tuple(w), features=feats)  # type: ignore[arg-type]
