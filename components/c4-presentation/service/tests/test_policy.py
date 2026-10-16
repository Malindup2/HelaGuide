"""Shared LinTS mathematics, feasibility and attribution tests."""

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from app.core.policy import (
    ACTION_NAMES,
    FEATURE_DIMENSION,
    FEATURE_NAMES_SHARED,
    FEATURE_SCHEMA_FINGERPRINT,
    FeedbackConflictError,
    NoFeasibleConfigurationError,
    PolicyError,
    SharedLinTSPolicy,
    _GaussianPosterior,
    action_encoding,
    encode_context,
    feature_vector,
)
from app.core.procedure_features import extract_structural_features
from app.core.procedure_graph import build_procedure_graph
from app.core.procedure_input import load_procedure_input
from app.core.scaffolds import enumerate_scaffolds
from app.core.user_context import (
    ContextConflictError,
    InMemoryContextService,
)
from app.models.policy import PolicyConfig, SupportFitFeedback
from app.models.procedure_features import NormalizationScales
from app.models.scaffolds import (
    AccessibilityConstraints,
    PresentationLocks,
)
from app.models.user_context import ContextUpdate, FamiliarityReport


FIXTURES = (
    Path(__file__).resolve().parents[2]
    / "research"
    / "data"
    / "fixtures"
    / "linear"
)

ACTION_IDS = ("action:request_token", "action:collect_pack")


@pytest.fixture
def procedure():
    procedure = load_procedure_input(
        FIXTURES / "plan.json",
        FIXTURES / "enrichment.json",
    )
    graph = build_procedure_graph(procedure)
    return graph, extract_structural_features(graph)


@pytest.fixture
def service():
    return InMemoryContextService(
        clock=lambda: datetime(2026, 10, 15, tzinfo=timezone.utc)
    )


def select(policy, session_id, procedure):
    return policy.select_and_offer(
        session_id,
        *procedure,
        intended_action_ids=ACTION_IDS,
    )


def acknowledge(service, selected):
    offer = selected.offer
    return service.acknowledge_exposure(
        offer.session_id,
        offer.exposure_id,
        configuration_id=offer.configuration.configuration_id,
        displayed_action_ids=("action:request_token",),
    )


def feedback(selected, rating="about_right", origin="simulation"):
    return SupportFitFeedback(
        exposure_id=selected.offer.exposure_id,
        rating=rating,
        origin=origin,
    )


def test_feature_schema_and_all_actions_are_stable(service, procedure):
    graph, features = procedure
    session = service.create_session()
    snapshot = service.evaluate(session.session_id, graph, features).snapshot
    configurations = enumerate_scaffolds()

    assert len(ACTION_NAMES) == 7
    assert len({action_encoding(item) for item in configurations}) == 64
    assert FEATURE_DIMENSION == 656
    assert len(set(FEATURE_NAMES_SHARED)) == FEATURE_DIMENSION
    assert len(FEATURE_SCHEMA_FINGERPRINT) == 64

    context = encode_context(features, snapshot)
    assert len(context) == 81

    vectors = [
        feature_vector(features, snapshot, item)
        for item in configurations
    ]
    assert len({tuple(vector) for vector in vectors}) == 64
    assert all(vector.shape == (656,) for vector in vectors)
    assert all(np.linalg.norm(vector) <= 1.0 + 1e-12 for vector in vectors)

    user = dict(snapshot.encoding())
    assert user["familiarity.unknown"] == 1.0
    assert user["navigation_capability.unknown"] == 1.0


def test_context_action_interactions_change_with_explicit_context(
    service, procedure
):
    graph, features = procedure
    session = service.create_session()
    before = service.evaluate(session.session_id, graph, features).snapshot

    service.update_context(
        session.session_id,
        ContextUpdate(
            familiarity=FamiliarityReport(
                service_id=graph.requested_service_id,
                score=1,
            ),
            navigation_capability=5,
        ),
        expected_revision=0,
    )
    after = service.evaluate(session.session_id, graph, features).snapshot

    overview = enumerate_scaffolds()[0]
    guided = next(
        item
        for item in enumerate_scaffolds()
        if item.presentation_mode == "GUIDED"
        and item.relationship_visual == "NONE"
        and not item.progressive_disclosure
        and not item.previous_context_recap
        and not item.prerequisite_cue
    )

    before_difference = (
        feature_vector(features, before, guided)
        - feature_vector(features, before, overview)
    )
    after_difference = (
        feature_vector(features, after, guided)
        - feature_vector(features, after, overview)
    )
    assert not np.array_equal(before_difference, after_difference)


def test_policy_rejects_mixed_normalization_scales(service, procedure):
    graph, _ = procedure
    changed = extract_structural_features(
        graph,
        scales=NormalizationScales(step_count=20.0),
    )
    session = service.create_session()
    policy = SharedLinTSPolicy(service)

    with pytest.raises(PolicyError, match="normalization scales"):
        select(policy, session.session_id, (graph, changed))

    assert service.event_history(session.session_id) == ()
    assert policy.posterior_revision == 0


def test_posterior_matches_closed_form_and_sampling_orientation():
    config = PolicyConfig(
        prior_precision=2.0,
        observation_noise=0.5,
        exploration_scale=0.7,
    )
    posterior = _GaussianPosterior(3, config)

    first = np.array([1.0, 0.5, -0.2])
    second = np.array([0.3, -0.4, 0.7])
    posterior.observe(first, 1)
    posterior.observe(second, 0)

    variance = config.observation_noise**2
    precision = (
        2.0 * np.eye(3)
        + np.outer(first, first) / variance
        + np.outer(second, second) / variance
    )
    b = (0.5 * first - 0.5 * second) / variance
    expected_mean = np.linalg.solve(precision, b)

    queries = np.array([[0.2, 0.1, 0.8], [1.0, -0.5, 0.0]])
    means, std = posterior.moments(queries)

    expected_variance = np.einsum(
        "ij,ji->i",
        queries,
        np.linalg.solve(precision, queries.T),
    )
    np.testing.assert_allclose(means, 0.5 + queries @ expected_mean)
    np.testing.assert_allclose(std**2, expected_variance)

    seed = 123
    normal = np.random.Generator(np.random.PCG64(seed)).standard_normal(3)
    expected_draw = expected_mean + 0.7 * np.linalg.solve(
        np.linalg.cholesky(precision).T,
        normal,
    )
    np.testing.assert_allclose(posterior.sample(seed), expected_draw)
    assert posterior.revision == 2


def test_posterior_remains_stable_for_collinear_observations():
    posterior = _GaussianPosterior(3, PolicyConfig())
    x = np.array([1.0, 0.5, 0.5])

    before = posterior.moments(x[None, :])[1][0]
    for index in range(30):
        posterior.observe(x, index % 2)

    mean, std = posterior.moments(x[None, :])
    assert np.isfinite(mean).all()
    assert 0.0 < std[0] < before

    revision = posterior.revision
    with pytest.raises(PolicyError):
        posterior.observe(np.array([np.nan, 0.0, 0.0]), 1)
    assert posterior.revision == revision


def test_default_cold_start_uses_baseline_without_inventing_learning(
    service, procedure
):
    session = service.create_session()
    policy = SharedLinTSPolicy(service)
    expected = service.evaluate(session.session_id, *procedure)

    selected = select(policy, session.session_id, procedure)
    assert selected.decision.selection_mode == "cold_start_baseline"
    assert selected.offer.configuration == expected.feasibility.baseline
    assert selected.decision.sampled_parameters is None
    assert selected.decision.draw_seed is None
    assert policy.posterior_revision == 0
    assert service.event_history(session.session_id) == ()

    acknowledge(service, selected)
    assert policy.posterior_revision == 0

    another = select(policy, session.session_id, procedure)
    assert another.decision.selection_mode == "cold_start_baseline"


def test_seeded_sampling_is_reproducible_and_uses_one_shared_draw(
    service, procedure
):
    session = service.create_session()
    config = PolicyConfig(cold_start_updates=0, seed=27)
    first_policy = SharedLinTSPolicy(service, config=config)
    second_policy = SharedLinTSPolicy(service, config=config)

    first = select(first_policy, session.session_id, procedure)
    second = select(second_policy, session.session_id, procedure)

    assert first.decision.selection_mode == "thompson"
    assert first.decision.draw_seed == second.decision.draw_seed
    assert first.offer.configuration == second.offer.configuration
    np.testing.assert_array_equal(
        first.decision.sampled_parameters,
        second.decision.sampled_parameters,
    )

    graph, features = procedure
    decision = first.decision
    theta = np.array(decision.sampled_parameters)
    recomputed = []

    for score in decision.candidate_scores:
        vector = feature_vector(
            features,
            decision.evaluation.snapshot,
            score.configuration,
        )
        value = float(0.5 + vector @ theta)
        assert score.sampled_score == pytest.approx(value)
        recomputed.append(value)

    winner = decision.candidate_scores[int(np.argmax(recomputed))]
    assert decision.configuration == winner.configuration
    assert len(decision.candidate_scores) == 8


def test_hard_constraints_are_respected_and_conflicts_are_not_relaxed(
    service, procedure
):
    session = service.create_session()
    session = service.update_context(
        session.session_id,
        ContextUpdate(
            locks=PresentationLocks(
                presentation_mode="GUIDED",
                progressive_disclosure=False,
                previous_context_recap=False,
                relationship_visual="NONE",
                prerequisite_cue=False,
            )
        ),
        expected_revision=0,
    )
    policy = SharedLinTSPolicy(
        service, config=PolicyConfig(cold_start_updates=0)
    )
    selected = select(policy, session.session_id, procedure)
    assert selected.decision.selection_mode == "forced"
    assert selected.offer.configuration.presentation_mode == "GUIDED"

    service.update_context(
        session.session_id,
        ContextUpdate(
            accessibility=AccessibilityConstraints(
                allow_guided_navigation=False
            )
        ),
        expected_revision=session.revision,
    )

    with pytest.raises(NoFeasibleConfigurationError):
        select(policy, session.session_id, procedure)
    assert policy.posterior_revision == 0


def test_stale_context_cannot_register_a_policy_offer(
    service, procedure, monkeypatch
):
    session = service.create_session()
    original_issue = service.issue_offer

    def changed_before_issue(*args, **kwargs):
        current = service.get_session(session.session_id)
        service.update_context(
            session.session_id,
            ContextUpdate(navigation_capability=2),
            expected_revision=current.revision,
        )
        return original_issue(*args, **kwargs)

    monkeypatch.setattr(service, "issue_offer", changed_before_issue)
    policy = SharedLinTSPolicy(service)

    with pytest.raises(ContextConflictError):
        select(policy, session.session_id, procedure)
    assert policy.posterior_revision == 0


def test_feedback_requires_acknowledgment_and_is_idempotent(
    service, procedure
):
    session = service.create_session()
    policy = SharedLinTSPolicy(service)
    selected = select(policy, session.session_id, procedure)

    with pytest.raises(PolicyError, match="not been acknowledged"):
        policy.apply_feedback(feedback(selected))
    assert policy.posterior_revision == 0

    acknowledge(service, selected)
    receipt = policy.apply_feedback(feedback(selected))
    repeated = policy.apply_feedback(feedback(selected))

    assert repeated == receipt
    assert receipt.reward == 1
    assert receipt.procedure_synthetic is True
    assert policy.posterior_revision == 1

    with pytest.raises(FeedbackConflictError):
        policy.apply_feedback(feedback(selected, "too_much"))
    assert policy.posterior_revision == 1

    next_offer = select(policy, session.session_id, procedure)
    assert next_offer.decision.selection_mode == "thompson"
    assert next_offer.decision.posterior_revision == 1


def test_late_feedback_uses_original_vector_and_posterior_revision(
    service, procedure, monkeypatch
):
    session = service.create_session()
    policy = SharedLinTSPolicy(service)
    selected = select(policy, session.session_id, procedure)
    original_vector = selected.decision.selected_features

    service.update_context(
        session.session_id,
        ContextUpdate(navigation_capability=5),
        expected_revision=0,
    )
    acknowledge(service, selected)

    observed = []
    original_observe = policy._posterior.observe

    def capture(vector, reward):
        observed.append((tuple(vector), reward))
        return original_observe(vector, reward)

    monkeypatch.setattr(policy._posterior, "observe", capture)

    receipt = policy.apply_feedback(feedback(selected, "need_more"))
    assert observed == [(original_vector, 0)]
    assert receipt.selection_posterior_revision == 0
    assert receipt.resulting_posterior_revision == 1
    assert selected.decision.evaluation.snapshot.settings.navigation_capability is None
    assert receipt.feedback.rating == "need_more"


def test_feedback_modes_are_separate_and_rewards_keep_direction(
    service, procedure
):
    session = service.create_session()
    policy = SharedLinTSPolicy(
        service,
        config=PolicyConfig(feedback_mode="participant"),
    )
    selected = select(policy, session.session_id, procedure)
    acknowledge(service, selected)

    with pytest.raises(PolicyError, match="origin"):
        policy.apply_feedback(feedback(selected))

    receipt = policy.apply_feedback(
        feedback(selected, "too_much", "participant_report")
    )
    assert receipt.reward == 0
    assert receipt.feedback.rating == "too_much"
    assert receipt.feedback.origin == "participant_report"
    assert receipt.procedure_synthetic is True

    with pytest.raises(ValidationError):
        SupportFitFeedback(
            exposure_id=selected.offer.exposure_id,
            rating=None,
            origin="participant_report",
        )


def test_shared_model_learns_across_sessions_but_not_policy_instances(
    service, procedure
):
    first_session = service.create_session()
    second_session = service.create_session()
    policy = SharedLinTSPolicy(service)

    first = select(policy, first_session.session_id, procedure)
    acknowledge(service, first)
    policy.apply_feedback(feedback(first))

    second = select(policy, second_session.session_id, procedure)
    assert second.decision.posterior_revision == 1
    assert second.decision.selection_mode == "thompson"

    restarted = SharedLinTSPolicy(service)
    assert restarted.posterior_revision == 0
    with pytest.raises(PolicyError, match="policy run"):
        restarted.apply_feedback(feedback(first))


def test_empty_exposure_cannot_train(service, procedure):
    session = service.create_session()
    policy = SharedLinTSPolicy(service)
    selected = select(policy, session.session_id, procedure)
    offer = selected.offer

    service.acknowledge_exposure(
        session.session_id,
        offer.exposure_id,
        configuration_id=offer.configuration.configuration_id,
        displayed_action_ids=(),
    )
    with pytest.raises(PolicyError, match="no procedural action"):
        policy.apply_feedback(feedback(selected))
    assert policy.posterior_revision == 0
    