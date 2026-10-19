"""User context, preference updates and acknowledged exposure tests."""

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.procedure_features import extract_structural_features
from app.core.procedure_graph import build_procedure_graph
from app.core.procedure_input import parse_procedure_input
from app.core.user_context import (
    ContextConflictError,
    ContextError,
    InMemoryContextService,
    UnknownExposureError,
    UnknownSessionError,
)
from app.models.scaffolds import (
    AccessibilityConstraints,
    PresentationLocks,
)
from app.models.user_context import (
    ContextUpdate,
    FamiliarityReport,
    PreferenceChange,
    PresentationExposure,
    SoftPreferences,
)


FIXTURES = (
    Path(__file__).resolve().parents[2]
    / "research"
    / "data"
    / "fixtures"
    / "linear"
)


class Clock:
    def __init__(self):
        self.value = datetime(2026, 10, 15, tzinfo=timezone.utc)

    def __call__(self):
        value = self.value
        self.value += timedelta(seconds=1)
        return value


@pytest.fixture
def service():
    return InMemoryContextService(clock=Clock())


@pytest.fixture
def documents():
    return tuple(
        json.loads((FIXTURES / name).read_text(encoding="utf-8-sig"))
        for name in ("plan.json", "enrichment.json")
    )


def build(documents):
    graph = build_procedure_graph(
        parse_procedure_input(
            json.dumps(documents[0]),
            json.dumps(documents[1]),
        )
    )
    return graph, extract_structural_features(graph)


@pytest.fixture
def procedure(documents):
    return build(documents)


def make_offer(service, session_id, procedure, actions):
    graph, features = procedure
    evaluation = service.evaluate(session_id, graph, features)
    return service.issue_offer(
        session_id,
        graph,
        features,
        evaluation.feasibility.baseline,
        intended_action_ids=actions,
        expected_revision=evaluation.snapshot.revision,
    )


def acknowledge(service, offer, actions):
    return service.acknowledge_exposure(
        offer.session_id,
        offer.exposure_id,
        configuration_id=offer.configuration.configuration_id,
        displayed_action_ids=actions,
    )


def test_new_guest_has_unknown_context_and_original_feasibility(
    service, procedure
):
    session = service.create_session()
    other = service.create_session()
    assert session.session_id != other.session_id

    result = service.evaluate(session.session_id, *procedure)
    assert len(result.feasibility.feasible_candidates()) == 8
    assert result.snapshot.matching_exposure_count == 0
    assert result.snapshot.recap_action_ids == ()

    encoded = dict(result.snapshot.encoding())
    assert encoded["familiarity.unknown"] == 1.0
    assert encoded["navigation_capability.unknown"] == 1.0
    assert encoded["familiarity.level_1"] == 0.0
    assert service.event_history(session.session_id) == ()


@pytest.mark.parametrize("invalid", [0, 6, True, "3", 2.5])
def test_five_point_ratings_reject_invalid_values(invalid):
    with pytest.raises(ValidationError):
        FamiliarityReport(service_id="svc:demo_pack", score=invalid)
    with pytest.raises(ValidationError):
        ContextUpdate(navigation_capability=invalid)


def test_ratings_are_explicit_and_familiarity_is_service_scoped(
    service, procedure
):
    session = service.create_session()
    session = service.update_context(
        session.session_id,
        ContextUpdate(
            familiarity=FamiliarityReport(
                service_id="svc:demo_pack",
                score=1,
            ),
            navigation_capability=5,
        ),
        expected_revision=0,
    )
    assert session.settings.familiarity_for("svc:demo_pack") == 1
    assert session.settings.familiarity_for("svc:other") is None

    result = service.evaluate(session.session_id, *procedure)
    encoded = dict(result.snapshot.encoding())
    assert encoded["familiarity.level_1"] == 1.0
    assert encoded["familiarity.unknown"] == 0.0
    assert encoded["navigation_capability.level_5"] == 1.0

    session = service.update_context(
        session.session_id,
        ContextUpdate(
            familiarity=FamiliarityReport(
                service_id="svc:demo_pack",
                score=None,
            ),
            navigation_capability=None,
        ),
        expected_revision=session.revision,
    )
    assert session.settings.familiarity_for("svc:demo_pack") is None
    assert session.settings.navigation_capability is None


def test_soft_preferences_do_not_restrict_candidates(service, procedure):
    session = service.create_session()
    before = service.evaluate(session.session_id, *procedure)

    service.update_context(
        session.session_id,
        ContextUpdate(
            preferences=SoftPreferences(
                presentation_mode="GUIDED",
                previous_context_recap=True,
            )
        ),
        expected_revision=0,
    )
    after = service.evaluate(session.session_id, *procedure)

    assert (
        before.feasibility.feasible_candidates()
        == after.feasibility.feasible_candidates()
    )
    assert after.snapshot.settings.preferences.previous_context_recap is True
    assert after.snapshot.settings.locks.previous_context_recap is None


def test_partial_lock_updates_preserve_off_and_support_unlock(
    service, procedure
):
    session = service.create_session()
    session = service.update_context(
        session.session_id,
        ContextUpdate(
            locks=PresentationLocks(
                presentation_mode="GUIDED",
                prerequisite_cue=False,
            )
        ),
        expected_revision=0,
    )
    session = service.update_context(
        session.session_id,
        ContextUpdate(
            locks=PresentationLocks(presentation_mode=None)
        ),
        expected_revision=session.revision,
    )

    assert session.settings.locks.presentation_mode is None
    assert session.settings.locks.prerequisite_cue is False

    result = service.evaluate(session.session_id, *procedure)
    assert {
        item.presentation_mode
        for item in result.feasibility.feasible_candidates()
    } == {"OVERVIEW", "GUIDED"}
    assert all(
        not item.prerequisite_cue
        for item in result.feasibility.feasible_candidates()
    )


def test_accessibility_conflicts_remain_explicit(service, procedure):
    session = service.create_session()
    session = service.update_context(
        session.session_id,
        ContextUpdate(
            locks=PresentationLocks(presentation_mode="GUIDED"),
            accessibility=AccessibilityConstraints(
                allow_guided_navigation=False
            ),
        ),
        expected_revision=0,
    )
    result = service.evaluate(session.session_id, *procedure)
    assert result.feasibility.feasible_candidates() == ()
    assert result.feasibility.baseline is None
    assert session.settings.locks.presentation_mode == "GUIDED"

    session = service.update_context(
        session.session_id,
        ContextUpdate(
            accessibility=AccessibilityConstraints(
                allow_relationship_visuals=False
            )
        ),
        expected_revision=session.revision,
    )
    assert session.settings.accessibility.allow_guided_navigation is False
    assert session.settings.accessibility.allow_relationship_visuals is False


def test_updates_are_revision_checked_and_no_ops_create_no_events(service):
    session = service.create_session()
    same = service.update_context(
        session.session_id,
        ContextUpdate(),
        expected_revision=0,
    )
    assert same == session
    assert service.event_history(session.session_id) == ()

    updated = service.update_context(
        session.session_id,
        ContextUpdate(navigation_capability=3),
        expected_revision=0,
    )
    assert updated.revision == 1

    with pytest.raises(ContextConflictError):
        service.update_context(
            session.session_id,
            ContextUpdate(navigation_capability=4),
            expected_revision=0,
        )
    assert len(service.event_history(session.session_id)) == 1

    with pytest.raises(ValidationError):
        ContextUpdate(locks=None)


def test_offer_is_not_exposure_and_acknowledgment_enables_recap(
    service, procedure
):
    session = service.create_session()
    offer = make_offer(
        service,
        session.session_id,
        procedure,
        ("action:request_token", "action:collect_pack"),
    )

    pending = service.evaluate(session.session_id, *procedure)
    assert pending.snapshot.matching_exposure_count == 0
    assert pending.snapshot.recap_action_ids == ()
    assert service.event_history(session.session_id) == ()

    event = acknowledge(service, offer, ("action:request_token",))
    assert isinstance(event, PresentationExposure)

    displayed = service.evaluate(session.session_id, *procedure)
    assert displayed.snapshot.matching_exposure_count == 1
    assert displayed.snapshot.recap_action_ids == ("action:request_token",)
    assert any(
        item.previous_context_recap
        for item in displayed.feasibility.feasible_candidates()
    )


def test_acknowledgments_are_idempotent_and_conflicts_are_rejected(
    service, procedure
):
    session = service.create_session()
    offer = make_offer(
        service,
        session.session_id,
        procedure,
        ("action:request_token", "action:collect_pack"),
    )
    first = acknowledge(service, offer, ("action:request_token",))
    second = acknowledge(service, offer, ("action:request_token",))

    assert second == first
    assert service.get_session(session.session_id).revision == 1
    assert len(service.event_history(session.session_id)) == 1

    with pytest.raises(ContextConflictError):
        acknowledge(service, offer, ("action:collect_pack",))

    with pytest.raises(ContextConflictError):
        service.acknowledge_exposure(
            session.session_id,
            offer.exposure_id,
            configuration_id="wrong-configuration",
            displayed_action_ids=("action:request_token",),
        )

    assert len(service.event_history(session.session_id)) == 1


def test_unoffered_actions_and_cross_session_acknowledgments_fail(
    service, procedure
):
    first = service.create_session()
    second = service.create_session()
    offer = make_offer(
        service, first.session_id, procedure, ("action:request_token",)
    )

    with pytest.raises(ContextError, match="unoffered"):
        acknowledge(service, offer, ("action:collect_pack",))

    with pytest.raises(UnknownExposureError):
        service.acknowledge_exposure(
            second.session_id,
            offer.exposure_id,
            configuration_id=offer.configuration.configuration_id,
            displayed_action_ids=("action:request_token",),
        )

    assert service.event_history(first.session_id) == ()
    assert service.event_history(second.session_id) == ()


def test_recaps_preserve_chronological_last_occurrences(service, procedure):
    session = service.create_session()
    for action_id in (
        "action:request_token",
        "action:collect_pack",
        "action:request_token",
    ):
        offer = make_offer(
            service, session.session_id, procedure, (action_id,)
        )
        acknowledge(service, offer, (action_id,))

    result = service.evaluate(session.session_id, *procedure)
    expected = ("action:collect_pack", "action:request_token")
    assert result.snapshot.recap_action_ids == expected
    assert result.feasibility.recap_action_ids == expected

    recent = result.snapshot.recent_exposures
    assert [event.sequence for event in recent] == [1, 2, 3]
    assert [event.acknowledged_at for event in recent] == sorted(
        event.acknowledged_at for event in recent
    )


def test_recap_window_is_bounded_but_total_count_is_retained(
    service, procedure
):
    session = service.create_session()
    for _ in range(6):
        offer = make_offer(
            service,
            session.session_id,
            procedure,
            ("action:request_token",),
        )
        acknowledge(service, offer, ("action:request_token",))

    result = service.evaluate(session.session_id, *procedure)
    assert result.snapshot.matching_exposure_count == 6
    assert len(result.snapshot.recent_exposures) == 5
    assert [event.sequence for event in result.snapshot.recent_exposures] == [
        2, 3, 4, 5, 6
    ]


def test_history_is_isolated_by_session_and_graph_version(
    service, procedure, documents
):
    first = service.create_session()
    second = service.create_session()

    offer = make_offer(
        service, first.session_id, procedure, ("action:request_token",)
    )
    acknowledge(service, offer, ("action:request_token",))

    other_session = service.evaluate(second.session_id, *procedure)
    assert other_session.snapshot.matching_exposure_count == 0

    changed = copy.deepcopy(documents)
    changed[1]["content"][0]["text"] += " Updated fictional explanation."
    changed_procedure = build(changed)
    other_version = service.evaluate(first.session_id, *changed_procedure)

    assert other_version.snapshot.matching_exposure_count == 0
    assert other_version.snapshot.recap_action_ids == ()
    assert len(service.event_history(first.session_id)) == 1


def test_late_acknowledgment_preserves_original_context(service, procedure):
    session = service.create_session()
    offer = make_offer(
        service, session.session_id, procedure, ("action:request_token",)
    )
    assert offer.context_snapshot.revision == 0

    service.update_context(
        session.session_id,
        ContextUpdate(navigation_capability=5),
        expected_revision=0,
    )
    event = acknowledge(service, offer, ("action:request_token",))

    assert event.sequence == 2
    assert event.offer.context_snapshot.revision == 0
    assert event.offer.context_snapshot.settings.navigation_capability is None
    assert service.get_session(session.session_id).settings.navigation_capability == 5

    history = service.event_history(session.session_id)
    assert isinstance(history[0], PreferenceChange)
    assert isinstance(history[1], PresentationExposure)


def test_stale_selection_cannot_create_an_offer(service, procedure):
    session = service.create_session()
    evaluation = service.evaluate(session.session_id, *procedure)

    service.update_context(
        session.session_id,
        ContextUpdate(navigation_capability=2),
        expected_revision=0,
    )
    with pytest.raises(ContextConflictError):
        service.issue_offer(
            session.session_id,
            *procedure,
            evaluation.feasibility.baseline,
            intended_action_ids=("action:request_token",),
            expected_revision=evaluation.snapshot.revision,
        )


def test_empty_action_acknowledgment_does_not_invent_recap(
    service, procedure
):
    session = service.create_session()
    offer = make_offer(service, session.session_id, procedure, ())
    acknowledge(service, offer, ())

    result = service.evaluate(session.session_id, *procedure)
    assert result.snapshot.matching_exposure_count == 1
    assert result.snapshot.recap_action_ids == ()
    assert all(
        not item.previous_context_recap
        for item in result.feasibility.feasible_candidates()
    )


def test_encoding_is_deterministic_and_snapshots_are_immutable(
    service, procedure
):
    session = service.create_session()
    before = service.evaluate(session.session_id, *procedure)
    repeated = service.evaluate(session.session_id, *procedure)

    assert before.snapshot.encoding() == repeated.snapshot.encoding()
    names = [name for name, _ in before.snapshot.encoding()]
    assert len(names) == len(set(names))

    with pytest.raises(ValidationError):
        before.snapshot.settings.navigation_capability = 5

    service.update_context(
        session.session_id,
        ContextUpdate(navigation_capability=1),
        expected_revision=0,
    )
    after = service.evaluate(session.session_id, *procedure)
    assert before.snapshot.settings.navigation_capability is None
    assert after.snapshot.settings.navigation_capability == 1
    assert before.snapshot.encoding() != after.snapshot.encoding()


def test_offer_retains_selection_context_for_future_attribution(
    service, procedure
):
    session = service.create_session()
    offer = make_offer(
        service, session.session_id, procedure, ("action:request_token",)
    )

    assert offer.configuration.configuration_id in offer.feasible_configuration_ids
    assert offer.context_snapshot.session_id == session.session_id
    assert offer.graph_fingerprint == offer.context_snapshot.graph_fingerprint
    assert offer.structural_encoding == procedure[1].context_encoding()
    assert offer.feasibility_rules_version == "c4-feasibility-1.0"


def test_restart_loses_sessions_and_naive_clock_is_rejected(service):
    session = service.create_session()
    restarted = InMemoryContextService(clock=Clock())

    with pytest.raises(UnknownSessionError):
        restarted.get_session(session.session_id)

    invalid_clock = InMemoryContextService(
        clock=lambda: datetime(2026, 10, 15)
    )
    with pytest.raises(ContextError, match="timezone-aware"):
        invalid_clock.create_session()