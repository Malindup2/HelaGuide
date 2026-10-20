"""Versioned 515-feature hierarchy, with fixed bounded block scaling.

No history-transfer score adjustment is included. Complete-only demand terms
are zero when coverage is partial/unknown; observed values and flags remain.
"""
import hashlib
import json
import math
import numpy as np
from app.models.procedure_features import FEATURE_NAMES
from app.v2.catalogue import DIMENSIONS, Configuration, Context

SCHEMA = "c4-features-v2.1-515"
ACTION_NAMES = ("guided", "explanation_expanded", "disclosure_expanded", "inline", "map", "recap", "summary")
RATING_STATES = (1, 2, 3, 4, None)
PAIRS = (("familiarity", "dependency_depth"), ("confidence", "step_count"),
         ("familiarity", "information_volume"), ("confidence", "dependency_count"),
         ("familiarity", "branch_count"), ("familiarity", "step_count"),
         ("confidence", "parallel_group_count"))
TRIPLES = ((0, (0,)), (1, (0,)), (2, (1,)), (3, (3, 4)),
           (4, (3, 4)), (5, (5,)), (2, (6,)), (6, (3, 4)))
SCAFFOLD_PAIRS = ((0, 3), (0, 4), (0, 5), (1, 2), (1, 6), (3, 6), (4, 6), (3, 5), (4, 5))
CONTEXT_NAMES = (tuple(f"observed.{n}" for n in FEATURE_NAMES)
    + tuple(f"complete_value.{n}" for n in FEATURE_NAMES)
    + tuple(f"{s}.{n}" for n in FEATURE_NAMES for s in ("partial", "unknown"))
    + tuple(f"{u}.{r}" for u in ("familiarity", "confidence") for r in RATING_STATES)
    + tuple(f"preference.{d}.{s}" for d, states in DIMENSIONS.items() for s in states)
    + ("intercept",))
NAMES = (tuple(f"{c}*{a}" for c in CONTEXT_NAMES for a in (*ACTION_NAMES, "intercept"))
    + tuple(f"{u}.{r}*complete_value.{p}" for u, p in PAIRS for r in RATING_STATES)
    + tuple(f"{PAIRS[p][0]}.{r}*complete_value.{PAIRS[p][1]}*{ACTION_NAMES[a]}"
            for p, actions in TRIPLES for r in RATING_STATES for a in actions)
    + tuple(f"{ACTION_NAMES[a]}*{ACTION_NAMES[b]}" for a, b in SCAFFOLD_PAIRS))
assert len(CONTEXT_NAMES) == 52 and len(NAMES) == len(set(NAMES)) == 515
FINGERPRINT = hashlib.sha256(json.dumps([SCHEMA, NAMES, [161, 7, 8, 6]], separators=(",", ":")).encode()).hexdigest()
VARIANTS = {"full": 515, "pairwise": 416, "threeway": 506}

def encode(measurements, context: Context, config: Configuration, variant="full"):
    if variant not in VARIANTS:
        raise ValueError("unknown encoder ablation")
    observed = [m.normalized_observed for m in measurements.ordered_measurements()]
    complete = [v if m.completeness == "complete" else 0.0
                for v, m in zip(observed, measurements.ordered_measurements())]
    flags = [float(m.completeness == s) for m in measurements.ordered_measurements() for s in ("partial", "unknown")]
    ratings = {u: [float(getattr(context, u) == r) for r in RATING_STATES] for u in ("familiarity", "confidence")}
    prefs = [float(context.preferences.get(d) == s) for d, states in DIMENSIONS.items() for s in states]
    x = np.array(observed + complete + flags + ratings["familiarity"] + ratings["confidence"] + prefs + [1.0])
    a = np.array([config.navigation == "guided", config.explanation == "expanded", config.disclosure == "expanded",
                  config.relationships == "inline", config.relationships == "map", config.recap == "on", config.summary == "on"], dtype=float)
    lower = [ratings[u][i] * complete[FEATURE_NAMES.index(p)] for u, p in PAIRS for i in range(5)]
    triple = [lower[p * 5 + i] * a[j] for p, actions in TRIPLES for i in range(5) for j in actions]
    pairs = [a[i] * a[j] for i, j in SCAFFOLD_PAIRS]
    vector = np.concatenate([np.outer(x, np.append(a, 1.0)).ravel() / math.sqrt(161),
                             np.array(lower) / math.sqrt(7), np.array(triple) / math.sqrt(8),
                             np.array(pairs) / math.sqrt(6)]) / 2
    vector = vector[:VARIANTS[variant]]
    if not np.isfinite(vector).all() or np.linalg.norm(vector) > 1.00000001:
        raise ValueError("invalid feature norm")
    return vector
