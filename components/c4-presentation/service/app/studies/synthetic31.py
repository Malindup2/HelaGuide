"""Author-defined hypothetical response model v3.1 (separately versioned; the 3.0 model in synthetic.py is untouched).

SYNTHETIC. No citizen observations, no expert validation, no measured comprehension. The selector never imports this module.
It sees only context, structure and the feasible set. This file is the evaluator's hidden world.

Design in one sentence: each scaffold has a need for this citizen and procedure (0 to 1); showing LESS than the need
(under-support) and MORE than the need (over-support) both lower the chance that the citizen says the presentation fits.
The weights of the two directions are an explicit assumption, and several alternative assumptions are provided for sensitivity.
"""
import math
import numpy as np
from app.guidance.catalogue import DIMENSIONS, Constraints
from app.guidance.sources import digest

SCHEMA = "c4-synthetic-response-pp1-1.1"
DIMS = ("navigation", "explanation", "disclosure", "relationships", "recap", "segmentation")

# Alternative reward assumptions. ONE of them is the training world of a run; all are used to evaluate (sensitivity).
ASSUMPTIONS = {
    "balanced": dict(base=1.2, under=1.2, over=1.2, preference=0.6, note="Under- and over-support hurt equally. Primary assumption."),
    "under_heavy": dict(base=1.2, under=2.0, over=0.6, preference=0.6, note="Missing help hurts more than surplus help."),
    "over_heavy": dict(base=1.2, under=0.7, over=2.0, preference=0.6, note="Surplus help (clutter, burden) hurts more than missing help."),
    "preference_led": dict(base=1.2, under=0.6, over=0.6, preference=1.6, note="Stated soft preferences dominate structure and need."),
    "low_need": dict(base=1.2, under=1.2, over=1.2, preference=0.6, shift=-0.6, note="Most citizens need little help (closer to the v3.0 world): need is lowered across the board."),
    "flat": dict(base=0.4, under=0.0, over=0.0, preference=0.0, note="Support has no effect at all (null world)."),
}

# (id, label, kind) kind: "retained" = the v3.0 hypothesis family re-expressed on the wider procedure set; "extension" = new situation.
FAMILIES = {
    "S1": ("Familiar citizen, simple procedure", "retained"), "S2": ("Unfamiliar citizen, same simple procedure", "retained"),
    "S3": ("Unfamiliar citizen, information-heavy procedure", "retained"), "S4": ("Procedural relationships", "retained"),
    "S5": ("Multi-phase orientation", "retained"), "S6": ("Conflicting preferences and accessibility", "retained"),
    "S7": ("Familiar citizen, complex procedure (counterexample)", "retained"), "S8": ("Unfamiliar citizen, simple procedure (counterexample)", "retained"),
    "S9": ("Null support effect", "retained"), "S10": ("High support burden sensitivity", "retained"),
    "N1": ("Familiar citizen, simple procedure, wants to scan requirements quickly", "extension"),
    "N2": ("Unfamiliar citizen, simple procedure, wants short but clear instructions", "extension"),
    "N3": ("Unfamiliar citizen, information-heavy procedure, may benefit from richer explanation", "extension"),
    "N4": ("Low-confidence citizen who dislikes long explanations", "extension"),
    "N5": ("Experienced citizen facing a new, complex procedure", "extension"),
    "N6": ("Citizen who prefers Overview despite limited familiarity", "extension"),
    "N7": ("Branch-heavy procedure where route alternatives matter", "extension"),
    "N8": ("Dependency-heavy procedure where Inline or Map support may help", "extension"),
    "N9": ("Genuine parallel tasks where relationship representation matters", "extension"),
    "N10": ("Multiphase procedure where Segmentation and possibly Recap may help", "extension"),
    "N11": ("Procedure where added scaffolding provides no benefit", "extension"),
    "N12": ("Preferences that conflict with context or hard accessibility requirements", "extension"),
}
SIMPLE = ("study-short-linear", "synthetic-linear-v1", "official-birth_copy-v3")
HEAVY_INFO = ("study-info-heavy", "official-company_pack-v3")
COMPLEX = ("study-multiphase", "study-mixed", "study-multilevel", "synthetic-practice-v2", "study-parallel-join")
BRANCHY = ("study-branching", "study-mixed", "synthetic-conditional-v1", "synthetic-practice-v2", "official-nic_amendment-v3")
DEPENDENT = ("study-multilevel", "study-long-linear", "study-parallel-join", "study-mixed", "synthetic-practice-v2")
PARALLEL = ("study-parallel-join", "synthetic-parallel-v1", "synthetic-practice-v2", "study-multiphase", "study-mixed")
PHASED = ("study-multiphase", "study-mixed", "study-long-linear", "study-multilevel", "synthetic-parallel-v1")
POOLS = {"S1": SIMPLE, "S2": SIMPLE, "S3": HEAVY_INFO + ("synthetic-practice-v2",), "S4": DEPENDENT + BRANCHY, "S5": PHASED, "S7": COMPLEX, "S8": SIMPLE,
         "N1": SIMPLE, "N2": SIMPLE, "N3": HEAVY_INFO, "N5": COMPLEX, "N7": BRANCHY, "N8": DEPENDENT, "N9": PARALLEL, "N10": PHASED}
SPEC = {"schema": SCHEMA, "families": {k: v[0] for k, v in FAMILIES.items()}, "assumptions": ASSUMPTIONS, "origin": "SYNTHETIC",
        "review": "author_defined_external_review_pending", "noise": "Bernoulli draw from the expected reward, clipped to [0.05, 0.95]",
        "need_formulas": "need_k = linear mix of unfamiliarity, low confidence and normalised structure; d_k = sigmoid(4*need_k); see need_vector()",
        "reward": "logit = base - under*sum(max(0,d-s)^2) - over*sum(max(0,s-d)^2) + preference*mean_match - overlap penalties",
        "scope": "Only the registered fictional graphs and clearly fictional study procedures; official procedures only as fallback probes"}


def _rating(value):
    return 0.5 if value is None else (value - 1) / 4


def need_vector(context, m, stages, shift=0.0):
    """Hidden per-scaffold need in [0,1]. Unknown structural measurements contribute 0 (they are not exact demand)."""
    u, c = 1 - _rating(context.get("familiarity")), 1 - _rating(context.get("confidence"))
    def exact(name):
        value = getattr(m, name)
        return value.normalized_observed if value.completeness == "complete" else 0.0
    length, volume, depth = exact("step_count"), exact("information_volume"), exact("dependency_depth")
    relation = (exact("dependency_count") + exact("branch_count") + exact("parallel_group_count")) / 3
    phases = min(1.0, max(0, stages - 1) / 3)
    need = np.array([0.9 * c + 1.1 * length + 0.4 * depth - 0.75, 1.1 * u + 0.9 * volume - 0.9, 0.8 * volume + 0.5 * u - 0.6,
                     1.3 * relation + 0.4 * c + 0.3 * u - 0.55, 0.9 * length + 0.6 * c + 0.2 * phases - 0.7, 1.0 * phases + 0.7 * length + 0.2 * c - 0.55])
    return 1 / (1 + np.exp(-4 * (need + shift)))


def support_vector(config):
    return np.array([config.navigation == "guided", config.explanation == "detailed", config.disclosure == "on",
                     {"none": 0.0, "inline": 0.5, "map": 1.0}[config.relationships], config.recap == "on", config.segmentation == "on"], dtype=float)


def gaps(config, context, m, stages, shift=0.0):
    need, s = need_vector(context, m, stages, shift), support_vector(config)
    return np.maximum(0, need - s), np.maximum(0, s - need)


def probability(config, context, m, stages, assumption="balanced", scenario_regime=None):
    """Counterfactual expected reward. Exposed ONLY to the simulator and evaluator."""
    a = ASSUMPTIONS["flat" if scenario_regime == "flat" else assumption]
    if a["under"] == 0 and a["over"] == 0:
        return 0.6
    under, over = gaps(config, context, m, stages, a.get("shift", 0.0))
    s = support_vector(config)
    prefs = context.get("preferences", {})
    match = sum(1 if getattr(config, d) == v else -0.5 for d, v in prefs.items()) / 6
    logit = a["base"] - a["under"] * float(np.square(under).sum()) - a["over"] * float(np.square(over).sum()) + a["preference"] * match
    logit -= 0.2 * s[0] * s[5] + 0.2 * s[3] * s[4]
    return float(np.clip(1 / (1 + math.exp(-logit)), 0.05, 0.95))


def scenario(rng, index, procedures, *, split="train"):
    """One declared synthetic citizen-procedure case. Families rotate evenly; pools restrict procedures to the structure a family is about."""
    names = list(FAMILIES)
    family = names[index % len(names)]
    allowed = sorted(procedures)
    pool = [p for p in POOLS.get(family, allowed) if p in procedures] or allowed
    pid = pool[int(rng.integers(len(pool)))]
    levels = [1, 3, 5, None] if split == "train" else ([2, 4] if split == "dev" else [1, 2, 3, 4, 5, None])
    f, n = rng.choice(levels), rng.choice(levels)
    low, high = ([1, 2], [4, 5])
    pick = lambda options: int(rng.choice(options))
    if family in ("S1", "S7", "N1"):
        f, n = pick(high if split != "train" else [5]), pick(high if split != "train" else [5])
    if family in ("S2", "S3", "S5", "S8", "N2", "N3"):
        f, n = pick(low if split != "train" else [1]), pick(low if split != "train" else [1])
    if family == "N4":
        n = pick(low if split != "train" else [1])
    if family == "N5":
        f, n = pick(low if split != "train" else [1]), pick(high if split != "train" else [5])
    if family == "N6":
        f = pick(low if split != "train" else [1])
    f = None if f is None else int(f)
    n = None if n is None else int(n)
    preferences = {d: states[int(rng.integers(len(states)))] for d, states in DIMENSIONS.items() if rng.random() < 0.4}
    if family == "N4":
        preferences["explanation"] = "concise"
    if family in ("N1", "N6"):
        preferences["navigation"] = "overview"
    constraints = Constraints(no_map=bool(rng.random() < 0.12), no_guided=bool(rng.random() < 0.08), no_disclosure=bool(rng.random() < 0.12))
    if family in ("S6", "N12"):
        preferences.update({"navigation": "guided", "relationships": "map", "disclosure": "on"} if family == "N12" else {"navigation": "overview" if (n or 3) < 3 else "guided"})
        constraints = Constraints(no_map=True, no_disclosure=True, no_guided=family == "N12")
    regime = "flat" if family in ("S9", "N11") else "primary"
    return {"id": f"{split}-{index:05d}", "family": family, "procedure_id": pid, "context": {"familiarity": f, "confidence": n, "preferences": preferences},
            "constraints": constraints.model_dump(), "latent_regime": regime, "split": split}


FINGERPRINT = digest({"spec": SPEC, "implementation_sha256": __import__("hashlib").sha256(__import__("pathlib").Path(__file__).read_bytes()).hexdigest()})
