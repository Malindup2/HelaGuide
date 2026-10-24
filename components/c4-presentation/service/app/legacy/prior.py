"""Compile a bounded mean, leaving covariance and real feedback counts unchanged."""

import hashlib
import json
from pathlib import Path

import numpy as np

from app.models.prior import PriorSpec


def prior_digest(spec: PriorSpec | None) -> str | None:
    if spec is None:
        return None
    value = json.dumps(spec.model_dump(mode="json"), sort_keys=True,
                       separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def compile_prior(spec: PriorSpec | None, feature_names, feature_scale):
    mean = np.zeros(len(feature_names), dtype=np.float64)
    if spec is None:
        return mean
    # Validate even if an internal caller used model_copy/model_construct.
    spec = PriorSpec.model_validate_json(spec.model_dump_json(round_trip=True))
    for judgment in spec.judgments:
        # Unknown familiarity is its own category, never treated as low/high.
        name = f"{judgment.context} * {judgment.aid}"
        if name not in feature_names:
            raise ValueError(f"unknown prior feature: {name}")
        mean[feature_names.index(name)] = judgment.score_delta * feature_scale
    return mean


def load_prior(path: str | Path) -> PriorSpec:
    path = Path(path)
    if path.stat().st_size > 256_000:
        raise ValueError("prior file exceeds 256 KB")
    prior = PriorSpec.model_validate_json(path.read_text(encoding="utf-8"))
    from app.legacy.v1_policy import FEATURE_NAMES_SHARED, FEATURE_SCALE
    compile_prior(prior, FEATURE_NAMES_SHARED, FEATURE_SCALE)
    return prior
