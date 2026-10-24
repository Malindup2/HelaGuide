"""Author-defined hypothetical response model. Never imported by the policy.

External expert feedback pending; no citizen observations or efficacy claims.
The selector sees context/graph/feasibility, never latent regime or response draws.
"""
import math
import numpy as np
from app.guidance.catalogue import DIMENSIONS, Constraints
from app.guidance.sources import digest

SCHEMA = "c4-synthetic-response-pp1-1.0"
FAMILIES = {
    "S1": "Familiar citizen, simple procedure", "S2": "Unfamiliar citizen, same procedure",
    "S3": "Unfamiliar citizen, information-heavy procedure", "S4": "Procedural relationships",
    "S5": "Multi-phase orientation", "S6": "Conflicting preferences/accessibility",
    "S7": "Familiar citizen, complex procedure counterexample", "S8": "Unfamiliar citizen, simple procedure counterexample",
    "S9": "Null support effect", "S10": "High support burden sensitivity"}
SPEC = {"schema": SCHEMA, "families": FAMILIES, "review": "author_defined_external_review_pending",
    "origin": "SYNTHETIC", "noise": "Bernoulli response with probabilities clipped to [0.08,0.92]",
    "coefficients": {"intercept": 1.4, "mismatch": 1.1, "preference": 0.65, "redundancy": 0.18},
    "regimes": ["primary", "preference_shift", "burden_shift", "null"],
    "scope": "Only actual registered graphs/content; no fabricated structural relationships"}


def scenario(rng, index, procedures, *, evaluation=False):
    family = "S" + str(index % 10 + 1)
    ids = sorted(procedures)
    simple = next(p for p in ids if "linear" in p)
    rich = next(p for p in ids if "practice" in p)
    pid = ids[int(rng.integers(len(ids)))]
    if not evaluation:
        if family in ("S1", "S2", "S8"): pid = simple
        elif family in ("S3", "S5", "S7"): pid = rich
    levels = [2, 4] if evaluation else [1, 3, 5, None]
    f, n = rng.choice(levels), rng.choice(levels)
    if not evaluation:
        if family in ("S1", "S7"): f, n = 5, 5
        if family in ("S2", "S3", "S5", "S8"): f, n = 1, 1
    f = None if f is None else int(f); n = None if n is None else int(n)
    preferences = {d: states[int(rng.integers(len(states)))] for d, states in DIMENSIONS.items() if rng.random() < 0.45}
    constraints = Constraints(no_map=bool(rng.random()<0.15), no_guided=bool(rng.random()<0.1), no_disclosure=bool(rng.random()<0.15))
    if family == "S6":
        preferences["navigation"] = "overview" if (n or 3)<3 else "guided"
        constraints = Constraints(no_map=True, no_disclosure=True)
    context = {"familiarity": f, "confidence": n, "preferences": preferences}
    return {"id": ("heldout" if evaluation else "train") + f"-{index:05d}", "family": family,
            "procedure_id": pid, "context": context, "constraints": constraints.model_dump(),
            "latent_regime": "null" if family=="S9" else "burden_shift" if family=="S10" else "primary"}


def probability(config, context, m, regime="primary"):
    """Counterfactual expected reward is exposed ONLY to simulator/evaluator."""
    if regime == "null": return 0.6
    f = (context.get("familiarity") or 3) / 5
    n = (context.get("confidence") or 3) / 5
    # Source completeness matters here too; unknown observations are not exact demand.
    def exact(name):
        value = getattr(m, name)
        return value.normalized_observed if value.completeness=="complete" else 0.0
    length, volume = exact("step_count"), exact("information_volume")
    relation = (exact("dependency_count") + exact("branch_count") + exact("parallel_group_count")) / 3
    demand = np.array([(1-n)*(0.35+length), (1-f)*(0.35+volume), (1-f)*(0.25+volume),
        (1-n)*(0.3+relation)+(1-f)*0.15, (1-f)*(0.2+length), (1-n)*(0.25+length)])
    support = np.array([config.navigation=="guided",config.explanation=="detailed",config.disclosure=="on",
        {"none":0.0,"inline":0.5,"map":1.0}[config.relationships],config.recap=="on",config.segmentation=="on"],dtype=float)
    preference = sum(1 if getattr(config,d)==s else -0.5 for d,s in context.get("preferences",{}).items()) / 6
    preference_weight = -0.25 if regime=="preference_shift" else 0.65
    burden = 0.35 * support.sum() if regime=="burden_shift" else 0.0
    logit = 1.4 - 1.1*float(np.square(support-demand).sum()) + preference_weight*preference - burden
    logit -= 0.18*support[0]*support[5] + 0.18*support[3]*support[4]
    return float(np.clip(1/(1+math.exp(-logit)),0.08,0.92))

FINGERPRINT = digest({"spec": SPEC, "implementation_sha256": __import__("hashlib").sha256(__import__("pathlib").Path(__file__).read_bytes()).hexdigest()})
