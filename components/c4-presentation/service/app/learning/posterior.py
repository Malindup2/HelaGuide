"""Shared Gaussian linear posterior: the numerical kernel of every C4 LinTS policy.

Used by the V3.1 policy and, unchanged, by the historical V1 (app.legacy.v1_policy) and V2
(app.compat.v2_runtime) policies. The Gaussian linear model is a surrogate for binary rewards;
scores are not calibrated probabilities. Reward eligibility, duplicate protection and
persistence are the callers' responsibility.
"""

import math

import numpy as np
from scipy.linalg import solve_triangular


class PolicyError(ValueError):
    """Invalid policy input or operation."""


class GaussianPosterior:
    """Shared Gaussian linear posterior using a Cholesky precision factor.

    `mean` is the prior mean (zeros when omitted). A configured prior must be compiled
    by the policy that owns its feature names and passed in as `mean`.
    """

    def __init__(self, dimension: int, config, mean=None):
        self.dimension = dimension
        self.config = config
        self.revision = 0

        self._precision = (
            np.eye(dimension, dtype=np.float64) * config.prior_precision
        )
        if mean is None:
            if config.prior is not None:
                raise PolicyError("a configured prior must be compiled by its policy")
            mean = np.zeros(dimension, dtype=np.float64)
        self._b = config.prior_precision * mean
        self._factor = (
            np.eye(dimension, dtype=np.float64)
            * math.sqrt(config.prior_precision)
        )
        self._mean = mean

    def _matrix(self, values) -> np.ndarray:
        matrix = np.asarray(values, dtype=np.float64)
        if (
            matrix.ndim != 2
            or matrix.shape[1] != self.dimension
            or not np.isfinite(matrix).all()
        ):
            raise PolicyError("invalid posterior feature matrix")
        return matrix

    def moments(self, values) -> tuple[np.ndarray, np.ndarray]:
        matrix = self._matrix(values)
        projected = solve_triangular(
            self._factor,
            matrix.T,
            lower=True,
            check_finite=False,
        )
        means = 0.5 + matrix @ self._mean
        variances = np.sum(projected * projected, axis=0)
        return means, np.sqrt(variances)

    def sample(self, seed: int) -> np.ndarray:
        # Explicit PCG64; one normal vector per decision.
        rng = np.random.Generator(np.random.PCG64(seed))
        normal = rng.standard_normal(self.dimension)

        # If A = L L^T, L^-T z has covariance A^-1.
        perturbation = solve_triangular(
            self._factor.T,
            normal,
            lower=False,
            check_finite=False,
        )
        sampled = self._mean + self.config.exploration_scale * perturbation
        if not np.isfinite(sampled).all():
            raise PolicyError("non-finite sampled parameters")
        return sampled

    def observe(self, vector, reward: int) -> None:
        if type(reward) is not int or reward not in (0, 1):
            raise PolicyError("reward must be the integer 0 or 1")

        x = np.asarray(vector, dtype=np.float64)
        if x.shape != (self.dimension,) or not np.isfinite(x).all():
            raise PolicyError("invalid update feature vector")

        variance = self.config.observation_noise**2
        precision = self._precision + np.outer(x, x) / variance
        b = self._b + x * (reward - 0.5) / variance

        # Re-factor after feedback, not for each candidate. No explicit inverse.
        # Commit the update only after all numerical operations succeed.
        if not np.isfinite(precision).all() or not np.isfinite(b).all():
            raise PolicyError("posterior update overflowed")

        try:
            factor = np.linalg.cholesky(precision)
            intermediate = solve_triangular(
                factor, b, lower=True, check_finite=False
            )
            mean = solve_triangular(
                factor.T,
                intermediate,
                lower=False,
                check_finite=False,
            )
        except np.linalg.LinAlgError as exc:
            raise PolicyError("posterior precision is not positive definite") from exc

        if not np.isfinite(mean).all():
            raise PolicyError("posterior update produced non-finite parameters")

        self._precision = precision
        self._b = b
        self._factor = factor
        self._mean = mean
        self.revision += 1
