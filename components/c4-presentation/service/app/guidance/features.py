"""Approved PP1 reference-coded hierarchy. No identity or history inputs."""
import math
import unicodedata
import numpy as np
from app.guidance.catalogue import DIMENSIONS, ACTION_SCHEMA
from app.guidance.sources import digest
from app.models.procedure_features import FEATURE_NAMES, NormalizationScales

SCHEMA = "c4-features-pp1-1.0-525"
RATINGS = (1, 2, 3, 4, None)  # rating 5 is the explicit reference category
ACTIONS = ("guided", "detailed", "disclosure_on", "inline", "map", "recap", "segmentation", "intercept")
PAIRS = (("familiarity", "dependency_depth"), ("confidence", "step_count"),
         ("familiarity", "information_volume"), ("confidence", "dependency_count"),
         ("familiarity", "branch_count"), ("familiarity", "step_count"),
         ("confidence", "parallel_group_count"))
TRIPLES = ((0, 0), (1, 0), (1, 6), (2, 1), (2, 6), (3, 3), (3, 4),
           (4, 3), (4, 4), (5, 5), (5, 6), (6, 3), (6, 4))
SCAFFOLD_PAIRS = ((0, 3), (0, 4), (0, 5), (1, 2), (1, 6), (3, 6), (4, 6), (3, 5), (4, 5))
PREFERENCES = tuple((d, s) for d, states in DIMENSIONS.items() for s in states)
CONTEXT = (tuple(f"observed.{n}" for n in FEATURE_NAMES)
    + tuple(f"complete_value.{n}" for n in FEATURE_NAMES)
    + tuple(f"{s}.{n}" for n in FEATURE_NAMES for s in ("partial", "unknown"))
    + tuple(f"{u}.{r}" for u in ("familiarity", "confidence") for r in RATINGS)
    + tuple(f"preference.{d}.{s}" for d, s in PREFERENCES) + ("intercept",))
NAMES = (tuple(f"{c}*{a}" for c in CONTEXT for a in ACTIONS)
    + tuple(f"{u}.{r}*complete_value.{p}" for u, p in PAIRS for r in RATINGS)
    + tuple(f"{PAIRS[p][0]}.{r}*complete_value.{PAIRS[p][1]}*{ACTIONS[a]}" for p, a in TRIPLES for r in RATINGS)
    + tuple(f"{ACTIONS[a]}*{ACTIONS[b]}" for a, b in SCAFFOLD_PAIRS))
VARIANTS = {"416": 416, "451": 451, "516": 516, "525": 525}
SCALES = (161, 7, 10, 6)
SPEC = {"schema": SCHEMA, "action": ACTION_SCHEMA, "context": CONTEXT, "actions": ACTIONS,
        "pairs": PAIRS, "triples": TRIPLES, "scaffold_pairs": SCAFFOLD_PAIRS,
        "names": NAMES, "preference_states": PREFERENCES, "preference_reference": "unset: all zero within dimension",
        "rating_reference": 5, "rating_indicators": RATINGS, "block_squared_bounds": SCALES,
        "overall_scale": 0.5, "structural_scales": NormalizationScales().model_dump(),
        "normalization": "x_over_x_plus_scale_v1", "unicode": unicodedata.unidata_version,
        "measurement_version": "c4-structural-v2.1"}
FINGERPRINT = digest(SPEC)
assert len(CONTEXT) == 52 and len(PREFERENCES) == 13 and len(set(NAMES)) == len(NAMES) == 525


def action_values(c):
    return np.array([c.navigation == "guided", c.explanation == "detailed", c.disclosure == "on",
        c.relationships == "inline", c.relationships == "map", c.recap == "on", c.segmentation == "on", True], dtype=float)


def encode(m, context, config, variant="525"):
    if variant not in VARIANTS: raise ValueError("unknown PP1 variant")
    if m.measurement_version != SPEC["measurement_version"] or m.unicode_data_version != SPEC["unicode"] or m.normalization_method != SPEC["normalization"]:
        raise ValueError("incompatible structural encoder")
    ordered = m.ordered_measurements()
    if any(v.scale != SPEC["structural_scales"][n] for n, v in zip(FEATURE_NAMES, ordered)):
        raise ValueError("structural scale mismatch")
    prefs = context.get("preferences", {})
    if any(d not in DIMENSIONS or s not in DIMENSIONS[d] for d, s in prefs.items()): raise ValueError("invalid preference")
    ratings = {}
    for u in ("familiarity", "confidence"):
        r = context.get(u)
        if r is not None and (type(r) is not int or r not in range(1, 6)): raise ValueError("invalid rating")
        ratings[u] = [float(r == v) for v in RATINGS]
    observed = [v.normalized_observed for v in ordered]
    complete = [x if v.completeness == "complete" else 0.0 for x, v in zip(observed, ordered)]
    flags = [float(v.completeness == s) for v in ordered for s in ("partial", "unknown")]
    x = observed + complete + flags + ratings["familiarity"] + ratings["confidence"] + [float(prefs.get(d) == s) for d, s in PREFERENCES] + [1.0]
    a = action_values(config)
    lower = [ratings[u][i] * complete[FEATURE_NAMES.index(p)] for u, p in PAIRS for i in range(5)]
    triple = [lower[p * 5 + i] * a[j] for p, j in TRIPLES for i in range(5)]
    blocks = [np.outer(x, a).ravel(), np.array(lower), np.array(triple), np.array([a[i] * a[j] for i, j in SCAFFOLD_PAIRS])]
    vector = np.concatenate([b / math.sqrt(s) for b, s in zip(blocks, SCALES)])[:VARIANTS[variant]] / 2
    if not np.isfinite(vector).all() or np.linalg.norm(vector) > 1 + 1e-10: raise ValueError("feature bound exceeded")
    return vector
