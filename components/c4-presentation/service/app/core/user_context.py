"""In-memory guest context and acknowledged exposure for C4.

Use one service instance per backend process. Restarting loses all state.
This service is intended for the independent research prototype, not a
distributed session system.

Session event order is server acknowledgment/acceptance order. Client
timestamps are not used to infer physical viewing order or task completion.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4

from app.core.scaffolds import filter_scaffolds, graph_fingerprint
from app.models.procedure_features import StructuralFeatures
from app.models.procedure_graph import CanonicalProcedureGraph
from app.models.scaffolds import (
    ContentSafety,
    FeasibilityResult,
    ScaffoldConfiguration,
)
from app.models.user_context import (
    RECAP_WINDOW,
    ContextEvaluation,
    ContextEvent,
    ContextSnapshot,
    ContextUpdate,
    ExposureSummary,
    GuestSession,
    PreferenceChange,
    PresentationExposure,
    PresentationOffer,
    UserSettings,
)

from app.models.runtime_state import SessionState

class ContextError(ValueError):
    """Invalid context operation."""


class ContextConflictError(ContextError):
    """Stale revision or conflicting acknowledgment."""


class UnknownSessionError(ContextError):
    """The session does not exist in this service instance."""


class UnknownExposureError(ContextError):
    """The exposure offer does not belong to this session."""


@dataclass
class _SessionState:
    session: GuestSession
    events: list[ContextEvent] = field(default_factory=list)
    offers: dict[str, PresentationOffer] = field(default_factory=dict)
    acknowledgments: dict[str, PresentationExposure] = field(
        default_factory=dict
    )


def _copy_with(model, **changes):
    """Reconstruct a frozen model from declared fields, excluding exports."""
    values = {
        name: getattr(model, name)
        for name in type(model).model_fields
    }
    values.update(changes)
    return type(model)(**values)


def _merge_explicit(current, patch):
    return _copy_with(
        current,
        **{
            name: getattr(patch, name)
            for name in patch.model_fields_set
        },
    )


def _validate_action_ids(action_ids, known):
    if not isinstance(action_ids, tuple):
        raise ContextError("action IDs must be a tuple")
    if any(not isinstance(identifier, str) for identifier in action_ids):
        raise ContextError("action IDs must be strings")
    if len(action_ids) != len(set(action_ids)):
        raise ContextError("action IDs must be unique")
    missing = set(action_ids) - known
    if missing:
        raise ContextError(f"unknown or unoffered action IDs: {sorted(missing)}")


class InMemoryContextService:
    def __init__(
        self,
        *,
        clock: Callable[[], datetime] | None = None,
    ):
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._sessions: dict[str, _SessionState] = {}
        self._lock = RLock()

    def _now(self, earliest: datetime | None = None) -> datetime:
        value = self._clock()
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ContextError("clock must return a timezone-aware datetime")
        value = value.astimezone(timezone.utc)
        if earliest is not None and value < earliest:
            raise ContextError("clock moved before the preceding session operation")
        return value

    def _state(self, session_id: str) -> _SessionState:
        try:
            return self._sessions[session_id]
        except KeyError as exc:
            raise UnknownSessionError("unknown guest session") from exc

    @staticmethod
    def _check_revision(state, expected_revision):
        if (
            type(expected_revision) is not int
            or expected_revision != state.session.revision
        ):
            raise ContextConflictError(
                "session revision changed; obtain current context and retry"
            )

    def create_session(self) -> GuestSession:
        with self._lock:
            now = self._now()
            session = GuestSession(
                session_id=f"guest:{uuid4().hex}",
                created_at=now,
                updated_at=now,
                revision=0,
                settings=UserSettings(),
            )
            self._sessions[session.session_id] = _SessionState(session=session)
            return session

    def get_session(self, session_id: str) -> GuestSession:
        with self._lock:
            return self._state(session_id).session

    def event_history(self, session_id: str) -> tuple[ContextEvent, ...]:
        with self._lock:
            return tuple(self._state(session_id).events)

    def update_context(
        self,
        session_id: str,
        update: ContextUpdate,
        *,
        expected_revision: int,
    ) -> GuestSession:
        """Apply only explicitly supplied fields.

        Conflicting locks are retained. Their consequences are reported by
        feasibility evaluation rather than silently changing user choices.
        """
        if not isinstance(update, ContextUpdate):
            raise TypeError("update must be ContextUpdate")

        with self._lock:
            state = self._state(session_id)
            self._check_revision(state, expected_revision)
            before = state.session.settings
            changes = {}

            if "familiarity" in update.model_fields_set:
                reports = {
                    report.service_id: report
                    for report in before.familiarity
                }
                report = update.familiarity
                reports[report.service_id] = report
                changes["familiarity"] = tuple(
                    reports[key] for key in sorted(reports)
                )

            if "navigation_capability" in update.model_fields_set:
                changes["navigation_capability"] = update.navigation_capability

            for name in ("preferences", "locks", "accessibility"):
                if name in update.model_fields_set:
                    changes[name] = _merge_explicit(
                        getattr(before, name),
                        getattr(update, name),
                    )

            after = _copy_with(before, **changes)
            if after == before:
                return state.session

            changed_fields = tuple(
                name
                for name in type(before).model_fields
                if getattr(before, name) != getattr(after, name)
            )
            now = self._now(state.session.updated_at)
            sequence = state.session.revision + 1

            event = PreferenceChange(
                event_id=f"event:{uuid4().hex}",
                session_id=session_id,
                sequence=sequence,
                occurred_at=now,
                changed_fields=changed_fields,
                before=before,
                after=after,
            )
            session = _copy_with(
                state.session,
                settings=after,
                revision=sequence,
                updated_at=now,
            )

            state.events.append(event)
            state.session = session
            return session

    def _snapshot(self, state, graph) -> ContextSnapshot:
        fingerprint = graph_fingerprint(graph)
        matching = [
            event
            for event in state.events
            if isinstance(event, PresentationExposure)
            and event.offer.graph_fingerprint == fingerprint
        ]

        recent = tuple(
            ExposureSummary(
                exposure_id=event.offer.exposure_id,
                sequence=event.sequence,
                acknowledged_at=event.acknowledged_at,
                configuration_id=event.offer.configuration.configuration_id,
                displayed_action_ids=event.displayed_action_ids,
            )
            for event in matching[-RECAP_WINDOW:]
        )

        # Keep each action at its most recent position in the recap window.
        # Ordering within one acknowledgment is its supplied display order.
        last_occurrence = {}
        for event in recent:
            for action_id in event.displayed_action_ids:
                last_occurrence.pop(action_id, None)
                last_occurrence[action_id] = None

        return ContextSnapshot(
            session_id=state.session.session_id,
            revision=state.session.revision,
            captured_at=self._now(state.session.updated_at),
            graph_fingerprint=fingerprint,
            requested_service_id=graph.requested_service_id,
            settings=state.session.settings,
            matching_exposure_count=len(matching),
            preference_change_count=sum(
                isinstance(event, PreferenceChange)
                for event in state.events
            ),
            recent_exposures=recent,
            recap_action_ids=tuple(last_occurrence),
        )

    def evaluate(
        self,
        session_id: str,
        graph: CanonicalProcedureGraph,
        features: StructuralFeatures,
        *,
        safety: ContentSafety | None = None,
    ) -> ContextEvaluation:
        """Build current context and reuse the existing feasibility engine."""
        with self._lock:
            state = self._state(session_id)
            snapshot = self._snapshot(state, graph)
            result = filter_scaffolds(
                graph,
                features,
                context=snapshot.feasibility_context(),
                safety=safety,
            )

            if set(result.recap_action_ids) != set(snapshot.recap_action_ids):
                raise ContextError("recap membership differs across context boundaries")

            # Existing 1D returns lexical ordering. Preserve its membership
            # and decisions while supplying chronological ordering here.
            ordered_result = _copy_with(
                result,
                recap_action_ids=snapshot.recap_action_ids,
            )
            return ContextEvaluation(
                snapshot=snapshot,
                feasibility=ordered_result,
            )

    def issue_offer(
        self,
        session_id: str,
        graph: CanonicalProcedureGraph,
        features: StructuralFeatures,
        configuration: ScaffoldConfiguration,
        *,
        intended_action_ids: tuple[str, ...],
        expected_revision: int,
        safety: ContentSafety | None = None,
    ) -> PresentationOffer:
        """Register a feasible intended presentation without recording exposure.

        Call after selection. The current context revision is checked again
        so a selection made before a context change is not silently offered.
        """
        with self._lock:
            state = self._state(session_id)
            self._check_revision(state, expected_revision)
            evaluation = self.evaluate(
                session_id, graph, features, safety=safety
            )
            candidates = evaluation.feasibility.feasible_candidates()
            if configuration not in candidates:
                raise ContextConflictError(
                    "configuration is not feasible in the current context"
                )

            known = {action.action_id for action in graph.actions}
            _validate_action_ids(intended_action_ids, known)

            canonical_configuration = next(
                item for item in candidates if item == configuration
            )
            offer = PresentationOffer(
                exposure_id=f"exposure:{uuid4().hex}",
                session_id=session_id,
                offered_at=evaluation.snapshot.captured_at,
                graph_fingerprint=evaluation.snapshot.graph_fingerprint,
                configuration=canonical_configuration,
                intended_action_ids=intended_action_ids,
                context_snapshot=evaluation.snapshot,
                feasible_configuration_ids=tuple(
                    item.configuration_id for item in candidates
                ),
                feasibility_rules_version=evaluation.feasibility.rules_version,
                structural_measurement_version=features.measurement_version,
                structural_encoding=features.context_encoding(),
            )
            state.offers[offer.exposure_id] = offer
            return offer

    def acknowledge_exposure(
        self,
        session_id: str,
        exposure_id: str,
        *,
        configuration_id: str,
        displayed_action_ids: tuple[str, ...],
    ) -> PresentationExposure:
        """Record the first matching client acknowledgment exactly once.

        Acknowledgment order is authoritative for the session history.
        A late acknowledgment retains the offer's original context even
        when the user's preferences have subsequently changed.

        An empty action tuple records presentation exposure without
        claiming that any detailed action was displayed.
        """
        with self._lock:
            state = self._state(session_id)
            offer = state.offers.get(exposure_id)
            if offer is None:
                raise UnknownExposureError(
                    "exposure offer does not belong to this guest session"
                )

            if configuration_id != offer.configuration.configuration_id:
                raise ContextConflictError(
                    "acknowledged configuration differs from the offered configuration"
                )
            _validate_action_ids(
                displayed_action_ids,
                set(offer.intended_action_ids),
            )

            previous = state.acknowledgments.get(exposure_id)
            if previous is not None:
                if previous.displayed_action_ids != displayed_action_ids:
                    raise ContextConflictError(
                        "exposure already acknowledged with different displayed actions"
                    )
                return previous

            now = self._now(max(state.session.updated_at, offer.offered_at))
            sequence = state.session.revision + 1
            event = PresentationExposure(
                event_id=f"event:{uuid4().hex}",
                session_id=session_id,
                sequence=sequence,
                acknowledged_at=now,
                displayed_action_ids=displayed_action_ids,
                offer=offer,
            )
            session = _copy_with(
                state.session,
                revision=sequence,
                updated_at=now,
            )

            state.events.append(event)
            state.acknowledgments[exposure_id] = event
            state.session = session
            return event


    def registered_offer(
        self,
        session_id: str,
        exposure_id: str,
    ) -> PresentationOffer:
        """Read an existing offer without acknowledging it."""
        with self._lock:
            state = self._state(session_id)
            try:
                return state.offers[exposure_id]
            except KeyError:
                raise UnknownExposureError("unknown registered offer") from None

    def export_state(self) -> tuple[SessionState, ...]:
        """Export immutable records without clocks, locks or credentials."""
        with self._lock:
            return tuple(
                SessionState(
                    session=state.session,
                    events=tuple(state.events),
                    offers=tuple(
                        state.offers[key] for key in sorted(state.offers)
                    ),
                )
                for _, state in sorted(self._sessions.items())
            )

    @classmethod
    def from_state(
        cls,
        records: tuple[SessionState, ...],
    ) -> "InMemoryContextService":
        """Restore a trusted local snapshot and verify its event chains."""
        service = cls()
        all_event_ids = set()
        all_exposure_ids = set()

        for record in records:
            session = record.session
            session_id = session.session_id
            if session_id in service._sessions:
                raise ContextError("duplicate persisted session")

            offers = {}
            for offer in record.offers:
                if (
                    offer.session_id != session_id
                    or offer.context_snapshot.session_id != session_id
                    or offer.exposure_id in all_exposure_ids
                    or offer.context_snapshot.revision > session.revision
                    or offer.offered_at < session.created_at
                    or offer.graph_fingerprint
                    != offer.context_snapshot.graph_fingerprint
                ):
                    raise ContextError("invalid persisted presentation offer")
                all_exposure_ids.add(offer.exposure_id)
                offers[offer.exposure_id] = offer

            settings = UserSettings()
            settings_at_revision = {0: settings}
            previous_time = session.created_at
            acknowledgments = {}

            for sequence, event in enumerate(record.events, start=1):
                if (
                    event.session_id != session_id
                    or event.sequence != sequence
                    or event.event_id in all_event_ids
                ):
                    raise ContextError("invalid persisted event identity or sequence")
                all_event_ids.add(event.event_id)

                if isinstance(event, PreferenceChange):
                    occurred_at = event.occurred_at
                    expected_changed = tuple(
                        name
                        for name in type(settings).model_fields
                        if getattr(event.before, name) != getattr(event.after, name)
                    )
                    if (
                        event.before != settings
                        or event.before == event.after
                        or event.changed_fields != expected_changed
                    ):
                        raise ContextError("broken persisted preference history")
                    settings = event.after
                else:
                    occurred_at = event.acknowledged_at
                    offer = offers.get(event.offer.exposure_id)
                    if (
                        offer != event.offer
                        or event.offer.exposure_id in acknowledgments
                        or occurred_at < event.offer.offered_at
                    ):
                        raise ContextError("invalid persisted acknowledgment")
                    _validate_action_ids(
                        event.displayed_action_ids,
                        set(event.offer.intended_action_ids),
                    )
                    acknowledgments[event.offer.exposure_id] = event

                if occurred_at < previous_time:
                    raise ContextError("persisted event chronology is invalid")
                previous_time = occurred_at
                settings_at_revision[sequence] = settings

            if (
                session.revision != len(record.events)
                or session.settings != settings
                or session.updated_at != previous_time
            ):
                raise ContextError("session differs from its persisted history")

            for offer in offers.values():
                snapshot = offer.context_snapshot
                if snapshot.settings != settings_at_revision[snapshot.revision]:
                    raise ContextError("offer context differs from historical settings")

            service._sessions[session_id] = _SessionState(
                session=session,
                events=list(record.events),
                offers=offers,
                acknowledgments=acknowledgments,
            )

        return service