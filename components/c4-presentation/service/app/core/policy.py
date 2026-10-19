"""Shared contextual Linear Thompson Sampling for C4.

One policy instance owns one shared posterior across all scaffold choices
and guest sessions.

The runtime persists exported state and replays attributed feedback on restart.

The Gaussian linear model is a surrogate for binary support-fit rewards.
Scores are not calibrated probabilities.

Public integration boundary:
    SharedLinTSPolicy.select_and_offer(...)
    SharedLinTSPolicy.apply_feedback(...)

No clicks, acknowledgments alone or missing responses create rewards.
"""

import hashlib
import json
import math
import unicodedata
from threading import RLock
from uuid import uuid4

import numpy as np
import scipy
from scipy.linalg import solve_triangular
from app.core.prior import compile_prior

from app.core.user_context import (
    ContextConflictError,
    InMemoryContextService,
)
from app.models.policy import (
    CandidateScore,
    PolicyConfig,
    PolicyDecision,
    PolicyOffer,
    SupportFitFeedback,
    UpdateReceipt,
)
from app.models.procedure_features import (
    FEATURE_NAMES,
    NormalizationScales,
    StructuralFeatures,
)
from app.models.procedure_graph import CanonicalProcedureGraph
from app.models.scaffolds import ContentSafety, ScaffoldConfiguration
from app.models.user_context import ContextSnapshot, PresentationExposure
from app.models.runtime_state import PolicyState


FEATURE_SCHEMA_VERSION = "c4-context-action-1.0"

# Frozen vocabulary for this policy feature-schema version.
CHOICES = (
    ("presentation_mode", ("OVERVIEW", "GUIDED")),
    ("progressive_disclosure", (False, True)),
    ("previous_context_recap", (False, True)),
    (
        "relationship_visual",
        ("NONE", "BRANCH_MAP", "DEPENDENCY_MAP", "PARALLEL_MAP"),
    ),
    ("prerequisite_cue", (False, True)),
)

ACTION_NAMES = (
    "guided",
    "progressive_disclosure",
    "previous_context_recap",
    "branch_map",
    "dependency_map",
    "parallel_map",
    "prerequisite_cue",
)

STRUCTURAL_NAMES = tuple(
    name
    for feature in FEATURE_NAMES
    for name in (
        f"{feature}.normalized_observed",
        f"{feature}.is_complete",
        f"{feature}.is_partial",
        f"{feature}.is_unknown",
    )
)


def _user_names() -> tuple[str, ...]:
    names = []
    for rating in ("familiarity", "navigation_capability"):
        names.extend(f"{rating}.level_{level}" for level in range(1, 6))
        names.append(f"{rating}.unknown")

    for prefix in ("preference", "lock"):
        for dimension, choices in CHOICES:
            for choice in choices:
                if isinstance(choice, bool):
                    label = "on" if choice else "off"
                else:
                    label = choice.lower()
                names.append(f"{prefix}.{dimension}.{label}")
            names.append(f"{prefix}.{dimension}.unset")

    names.extend(
        (
            "accessibility.allow_relationship_visuals",
            "accessibility.allow_collapsed_content",
            "accessibility.allow_guided_navigation",
            "history.recap_available",
            "history.exposures_scaled",
            "history.recap_actions_scaled",
            "history.preference_changes_scaled",
        )
    )
    return tuple(names)


USER_NAMES = _user_names()

CONTEXT_NAMES = (
    tuple(f"structure.{name}" for name in STRUCTURAL_NAMES)
    + tuple(f"user.{name}" for name in USER_NAMES)
)

FEATURE_NAMES_SHARED = tuple(
    f"{context_name} * {action_name}"
    for context_name in ("intercept",) + CONTEXT_NAMES
    for action_name in ("intercept",) + ACTION_NAMES
)

FEATURE_DIMENSION = len(FEATURE_NAMES_SHARED)
FEATURE_SCALE = math.sqrt(FEATURE_DIMENSION)

# A policy run must not silently mix different structural normalizations.
EXPECTED_SCALES = NormalizationScales()

_SCHEMA_DESCRIPTION = {
    "version": FEATURE_SCHEMA_VERSION,
    "names": FEATURE_NAMES_SHARED,
    "scaling": "outer_product_divided_by_sqrt_dimension",
    "structural_measurement": "c4-structural-1.0",
    "user_encoding": "c4-user-context-1.0",
    "normalization": "x_over_x_plus_scale_v1",
    "scales": EXPECTED_SCALES.model_dump(),
    "lexical_rule": "nfc_unicode_lmn_runs_v1",
    "unicode_data_version": unicodedata.unidata_version,
}

FEATURE_SCHEMA_FINGERPRINT = hashlib.sha256(
    json.dumps(
        _SCHEMA_DESCRIPTION,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
).hexdigest()


class PolicyError(ValueError):
    """Invalid policy input or operation."""


class NoFeasibleConfigurationError(PolicyError):
    """No configuration satisfies the current hard constraints."""


class FeedbackConflictError(PolicyError):
    """An exposure already has different accepted feedback."""


def action_encoding(
    configuration: ScaffoldConfiguration,
) -> tuple[float, ...]:
    """Seven stable contrasts; no configuration-specific one-hot arms."""
    if not isinstance(configuration, ScaffoldConfiguration):
        raise TypeError("configuration must be ScaffoldConfiguration")

    return (
        float(configuration.presentation_mode == "GUIDED"),
        float(configuration.progressive_disclosure),
        float(configuration.previous_context_recap),
        float(configuration.relationship_visual == "BRANCH_MAP"),
        float(configuration.relationship_visual == "DEPENDENCY_MAP"),
        float(configuration.relationship_visual == "PARALLEL_MAP"),
        float(configuration.prerequisite_cue),
    )


def encode_context(
    features: StructuralFeatures,
    snapshot: ContextSnapshot,
) -> tuple[float, ...]:
    """Use the existing encodings and reject feature-schema drift.

    Graph/feature consistency is checked by the existing feasibility
    service before policy selection.
    """
    if not isinstance(features, StructuralFeatures):
        raise TypeError("features must be StructuralFeatures")
    if not isinstance(snapshot, ContextSnapshot):
        raise TypeError("snapshot must be ContextSnapshot")

    if features.measurement_version != "c4-structural-1.0":
        raise PolicyError("unsupported structural measurement version")
    if snapshot.encoding_version != "c4-user-context-1.0":
        raise PolicyError("unsupported user encoding version")
    if features.requested_service_id != snapshot.requested_service_id:
        raise PolicyError("structural and user service scopes differ")
    if features.normalization_method != "x_over_x_plus_scale_v1":
        raise PolicyError("unsupported structural normalization")
    if features.lexical_rule != "nfc_unicode_lmn_runs_v1":
        raise PolicyError("unsupported lexical rule")
    if features.unicode_data_version != unicodedata.unidata_version:
        raise PolicyError("Unicode measurement version differs from policy schema")

    for name in FEATURE_NAMES:
        if getattr(features, name).scale != getattr(EXPECTED_SCALES, name):
            raise PolicyError(
                "normalization scales differ from this policy schema; "
                "use a separately versioned policy for different scales"
            )

    structural = features.context_encoding()
    user = snapshot.encoding()

    if tuple(name for name, _ in structural) != STRUCTURAL_NAMES:
        raise PolicyError("structural encoding names or order changed")
    if tuple(name for name, _ in user) != USER_NAMES:
        raise PolicyError("user encoding names or order changed")

    values = tuple(float(value) for _, value in structural + user)
    if not all(math.isfinite(value) and 0.0 <= value <= 1.0 for value in values):
        raise PolicyError("context encodings must be finite values in [0, 1]")
    return values


def feature_vector(
    features: StructuralFeatures,
    snapshot: ContextSnapshot,
    configuration: ScaffoldConfiguration,
) -> np.ndarray:
    """Return a new vector; input models are never mutated."""
    context = np.asarray(
        (1.0,) + encode_context(features, snapshot),
        dtype=np.float64,
    )
    action = np.asarray(
        (1.0,) + action_encoding(configuration),
        dtype=np.float64,
    )
    return np.outer(context, action).reshape(-1) / FEATURE_SCALE


class _GaussianPosterior:
    """Shared Gaussian linear posterior using a Cholesky precision factor.

    This numerical class is internal. Reward eligibility and duplicate
    protection are enforced by SharedLinTSPolicy.apply_feedback().
    """

    def __init__(self, dimension: int, config: PolicyConfig):
        self.dimension = dimension
        self.config = config
        self.revision = 0

        self._precision = (
            np.eye(dimension, dtype=np.float64) * config.prior_precision
        )
        if config.prior is not None and dimension != FEATURE_DIMENSION:
            raise PolicyError("configured prior requires the shared feature dimension")
        mean = (compile_prior(config.prior, FEATURE_NAMES_SHARED, FEATURE_SCALE)
                if config.prior is not None else np.zeros(dimension, dtype=np.float64))
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


class SharedLinTSPolicy:
    """One in-memory shared policy, bound to one context service.

    Use separate instances for simulated and participant-reported feedback.
    The feedback origin is supplied by a trusted experiment/application
    boundary, not accepted as an unauthenticated client assertion.
    """

    def __init__(
        self,
        context_service: InMemoryContextService,
        *,
        config: PolicyConfig | None = None,
    ):
        if not isinstance(context_service, InMemoryContextService):
            raise TypeError("context_service must be InMemoryContextService")

        self.config = config or PolicyConfig()
        self.policy_run_id = f"policy-run:{uuid4().hex}"

        self._contexts = context_service
        self._posterior = _GaussianPosterior(FEATURE_DIMENSION, self.config)
        self._rng = np.random.Generator(np.random.PCG64(self.config.seed))
        self._offers: dict[str, PolicyOffer] = {}
        self._receipts: dict[str, UpdateReceipt] = {}
        self._decision_sequence = 0
        self._lock = RLock()

    @property
    def posterior_revision(self) -> int:
        with self._lock:
            return self._posterior.revision

    def get_offer(self, exposure_id: str) -> PolicyOffer:
        with self._lock:
            try:
                return self._offers[exposure_id]
            except KeyError as exc:
                raise PolicyError("exposure does not belong to this policy run") from exc

    def select_and_offer(
        self,
        session_id: str,
        graph: CanonicalProcedureGraph,
        features: StructuralFeatures,
        *,
        intended_action_ids: tuple[str, ...],
        safety: ContentSafety | None = None,
    ) -> PolicyOffer:
        """Evaluate, select and register an attributed presentation offer.

        A stale context causes issue_offer() to fail. The caller must obtain
        a new selection; a stale decision must not be displayed.

        No exposure or reward is recorded here.
        """
        with self._lock:
            known = {action.action_id for action in graph.actions}
            if (
                not isinstance(intended_action_ids, tuple)
                or not intended_action_ids
                or any(not isinstance(item, str) for item in intended_action_ids)
                or len(intended_action_ids) != len(set(intended_action_ids))
                or not set(intended_action_ids) <= known
            ):
                raise PolicyError(
                    "intended_action_ids must be a nonempty tuple "
                    "of unique actions from this graph"
                )

            evaluation = self._contexts.evaluate(
                session_id, graph, features, safety=safety
            )
            candidates = evaluation.feasibility.feasible_candidates()
            if not candidates:
                raise NoFeasibleConfigurationError(
                    evaluation.feasibility.baseline_reason
                )

            matrix = np.stack(
                [
                    feature_vector(features, evaluation.snapshot, candidate)
                    for candidate in candidates
                ]
            )
            means, standard_deviations = self._posterior.moments(matrix)

            draw_seed = None
            sampled_parameters = None
            sampled_scores = None

            if len(candidates) == 1:
                mode = "forced"
                reason = "Exactly one configuration satisfies the hard constraints."
                selected_index = 0
            elif self._posterior.revision < self.config.cold_start_updates:
                mode = "cold_start_baseline"
                reason = (
                    "The configured number of eligible explicit ratings has "
                    "not been reached; use the existing feasible baseline."
                )
                baseline = evaluation.feasibility.baseline
                if baseline is None or baseline not in candidates:
                    raise PolicyError("feasibility returned no valid baseline")
                selected_index = candidates.index(baseline)
            else:
                mode = "thompson"
                reason = (
                    "Maximum sampled linear score among hard-feasible "
                    "candidates, using one shared parameter draw."
                )
                draw_seed = int(
                    self._rng.integers(0, 2**63 - 1, dtype=np.int64)
                )
                sampled_parameters = self._posterior.sample(draw_seed)
                sampled_scores = 0.5 + matrix @ sampled_parameters
                if not np.isfinite(sampled_scores).all():
                    raise PolicyError("non-finite candidate scores")

                # Stable catalogue order resolves exact numerical ties.
                selected_index = int(np.argmax(sampled_scores))

            selected = candidates[selected_index]

            offer = self._contexts.issue_offer(
                session_id,
                graph,
                features,
                selected,
                intended_action_ids=intended_action_ids,
                expected_revision=evaluation.snapshot.revision,
                safety=safety,
            )

            expected_ids = tuple(
                candidate.configuration_id for candidate in candidates
            )
            if (
                offer.context_snapshot.revision != evaluation.snapshot.revision
                or offer.context_snapshot.settings != evaluation.snapshot.settings
                or offer.context_snapshot.encoding() != evaluation.snapshot.encoding()
                or offer.graph_fingerprint != evaluation.snapshot.graph_fingerprint
                or offer.feasible_configuration_ids != expected_ids
                or offer.structural_encoding != features.context_encoding()
            ):
                raise ContextConflictError(
                    "offer attribution differs from the selection; "
                    "do not display this offer"
                )

            scores = tuple(
                CandidateScore(
                    configuration=candidate,
                    posterior_mean=float(means[index]),
                    posterior_std=float(standard_deviations[index]),
                    sampling_std=float(
                        self.config.exploration_scale
                        * standard_deviations[index]
                    ),
                    sampled_score=(
                        None
                        if sampled_scores is None
                        else float(sampled_scores[index])
                    ),
                )
                for index, candidate in enumerate(candidates)
            )

            sequence = self._decision_sequence + 1
            decision = PolicyDecision(
                decision_id=f"decision:{uuid4().hex}",
                policy_run_id=self.policy_run_id,
                decision_sequence=sequence,
                posterior_revision=self._posterior.revision,
                config=self.config,
                feature_schema_fingerprint=FEATURE_SCHEMA_FINGERPRINT,
                feature_dimension=FEATURE_DIMENSION,
                numerical_versions=(
                    ("numpy", np.__version__),
                    ("scipy", scipy.__version__),
                    ("bit_generator", "PCG64"),
                ),
                selection_mode=mode,
                selection_reason=reason,
                draw_seed=draw_seed,
                evaluation=evaluation,
                structural_features=features,
                configuration=selected,
                selected_features=tuple(
                    float(value) for value in matrix[selected_index]
                ),
                candidate_scores=scores,
                sampled_parameters=(
                    None
                    if sampled_parameters is None
                    else tuple(float(value) for value in sampled_parameters)
                ),
            )
            result = PolicyOffer(decision=decision, offer=offer)
            self._offers[offer.exposure_id] = result
            self._decision_sequence = sequence
            return result

    def apply_feedback(
        self,
        feedback: SupportFitFeedback,
    ) -> UpdateReceipt:
        """Apply one explicit support-fit rating to an acknowledged offer.

        This is an internal learning boundary for later feedback handling.
        It does not authenticate participants or implement a feedback API.

        Missing responses and factual complaints must not be passed here.
        Partial action exposure is allowed: the rating concerns the
        acknowledged presentation, not completion of the entire procedure.
        """
        if not isinstance(feedback, SupportFitFeedback):
            raise TypeError("feedback must be SupportFitFeedback")

        with self._lock:
            expected_origin = (
                "simulation"
                if self.config.feedback_mode == "simulation"
                else "participant_report"
            )
            if feedback.origin != expected_origin:
                raise PolicyError(
                    "feedback origin does not match this policy run"
                )

            previous = self._receipts.get(feedback.exposure_id)
            if previous is not None:
                if previous.feedback == feedback:
                    return previous
                raise FeedbackConflictError(
                    "this exposure already has different accepted feedback"
                )

            selected = self.get_offer(feedback.exposure_id)
            offer = selected.offer

            acknowledgment = next(
                (
                    event
                    for event in self._contexts.event_history(offer.session_id)
                    if isinstance(event, PresentationExposure)
                    and event.offer.exposure_id == offer.exposure_id
                ),
                None,
            )
            if acknowledgment is None:
                raise PolicyError("presentation has not been acknowledged")
            if acknowledgment.offer != offer:
                raise PolicyError("acknowledgment does not match the policy offer")
            if not acknowledgment.displayed_action_ids:
                raise PolicyError(
                    "no procedural action was acknowledged as displayed"
                )

            reward = 1 if feedback.rating == "about_right" else 0

            # Construct the receipt first. Observe commits atomically only
            # after successful numerical checks.
            receipt = UpdateReceipt(
                feedback=feedback,
                policy_run_id=self.policy_run_id,
                decision_id=selected.decision.decision_id,
                acknowledgment_event_id=acknowledgment.event_id,
                reward=reward,
                procedure_synthetic=selected.decision.structural_features.synthetic,
                selection_posterior_revision=selected.decision.posterior_revision,
                resulting_posterior_revision=self._posterior.revision + 1,
            )

            # Use the original selected vector, never current session context.
            self._posterior.observe(
                selected.decision.selected_features,
                reward,
            )
            self._receipts[feedback.exposure_id] = receipt
            return receipt



    def posterior_fingerprint(self) -> str:
        """Fingerprint actual numerical state for recovery verification."""
        with self._lock:
            digest = hashlib.sha256()
            digest.update(str(self._posterior.revision).encode("ascii"))
            digest.update(
                np.asarray(
                    self._posterior._precision, dtype="<f8"
                ).tobytes(order="C")
            )
            digest.update(
                np.asarray(self._posterior._b, dtype="<f8").tobytes(order="C")
            )
            return digest.hexdigest()

    def export_state(self) -> PolicyState:
        with self._lock:
            return PolicyState(
                config=self.config,
                policy_run_id=self.policy_run_id,
                feature_schema_version=FEATURE_SCHEMA_VERSION,
                feature_schema_fingerprint=FEATURE_SCHEMA_FINGERPRINT,
                feature_dimension=FEATURE_DIMENSION,
                decision_sequence=self._decision_sequence,
                posterior_revision=self._posterior.revision,
                posterior_fingerprint=self.posterior_fingerprint(),
                rng_state_json=json.dumps(
                    self._rng.bit_generator.state,
                    sort_keys=True,
                    allow_nan=False,
                ),
                offers=tuple(
                    sorted(
                        self._offers.values(),
                        key=lambda value: value.decision.decision_sequence,
                    )
                ),
                receipts=tuple(
                    sorted(
                        self._receipts.values(),
                        key=lambda value: value.resulting_posterior_revision,
                    )
                ),
            )

    @classmethod
    def from_state(
        cls,
        contexts: InMemoryContextService,
        state: PolicyState,
    ) -> "SharedLinTSPolicy":
        """Recover attribution and replay accepted rewards through apply_feedback."""
        if (
            state.feature_schema_version != FEATURE_SCHEMA_VERSION
            or state.feature_schema_fingerprint != FEATURE_SCHEMA_FINGERPRINT
            or state.feature_dimension != FEATURE_DIMENSION
        ):
            raise PolicyError("persisted policy feature schema is incompatible")

        restored = cls(contexts, config=state.config)
        restored.policy_run_id = state.policy_run_id
        decision_ids = set()
        previous_selection_revision = 0

        for sequence, selected in enumerate(state.offers, start=1):
            decision = selected.decision
            offer = selected.offer
            expected_candidates = tuple(
                candidate.configuration_id
                for candidate in decision.evaluation.feasibility.feasible_candidates()
            )

            if (
                decision.decision_sequence != sequence
                or decision.decision_id in decision_ids
                or offer.exposure_id in restored._offers
                or decision.policy_run_id != state.policy_run_id
                or decision.config != state.config
                or decision.feature_schema_version != FEATURE_SCHEMA_VERSION
                or decision.feature_schema_fingerprint
                != FEATURE_SCHEMA_FINGERPRINT
                or decision.feature_dimension != FEATURE_DIMENSION
                or decision.posterior_revision < previous_selection_revision
                or decision.posterior_revision > state.posterior_revision
                or decision.configuration != offer.configuration
                or (
                    decision.evaluation.snapshot.model_dump(
                        exclude={"captured_at"}
                    )
                    != offer.context_snapshot.model_dump(
                        exclude={"captured_at"}
                    )
                )
                or offer.feasible_configuration_ids != expected_candidates
                or offer.configuration
                not in decision.evaluation.feasibility.feasible_candidates()
                or contexts.registered_offer(
                    offer.session_id, offer.exposure_id
                ) != offer
            ):
                raise PolicyError("invalid persisted policy attribution")

            expected_vector = feature_vector(
                decision.structural_features,
                offer.context_snapshot,
                offer.configuration,
            )
            if not np.array_equal(
                expected_vector,
                np.asarray(decision.selected_features, dtype=np.float64),
            ):
                raise PolicyError("persisted context-action vector differs from schema")

            decision_ids.add(decision.decision_id)
            previous_selection_revision = decision.posterior_revision
            restored._offers[offer.exposure_id] = selected

        if state.decision_sequence != len(state.offers):
            raise PolicyError("persisted decision sequence is inconsistent")
        restored._decision_sequence = state.decision_sequence

        for revision, expected_receipt in enumerate(state.receipts, start=1):
            if (
                expected_receipt.resulting_posterior_revision != revision
                or expected_receipt.selection_posterior_revision
                > restored.posterior_revision
            ):
                raise PolicyError("invalid persisted feedback order")
            actual_receipt = restored.apply_feedback(expected_receipt.feedback)
            if actual_receipt != expected_receipt:
                raise PolicyError("persisted feedback attribution failed recovery")

        if (
            restored.posterior_revision != state.posterior_revision
            or restored.posterior_fingerprint() != state.posterior_fingerprint
        ):
            raise PolicyError("reconstructed posterior differs from saved state")

        try:
            rng_state = json.loads(state.rng_state_json)
            if rng_state.get("bit_generator") != "PCG64":
                raise ValueError("unexpected random generator")
            restored._rng.bit_generator.state = rng_state
        except (ValueError, TypeError, KeyError, AttributeError):
            raise PolicyError("invalid persisted sampler state") from None

        return restored
