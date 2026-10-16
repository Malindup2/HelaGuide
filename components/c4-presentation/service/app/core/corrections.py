"""Optional corrections and explicitly applied future soft preferences.

Call these functions under DevRuntime's lock or atomic change boundary.
They never invoke policy selection or policy learning updates.
"""

from datetime import datetime, timezone

from fastapi import HTTPException

from app.core.state_store import StateStoreError
from app.models.corrections import (
    CORRECTION_CHOICES,
    CorrectionOption,
    CorrectionOptions,
    CorrectionRecord,
    PreferenceApplication,
    preference_values,
)
from app.models.user_context import (
    ContextUpdate,
    GuestSession,
    PreferenceChange,
    PresentationExposure,
    SoftPreferences,
    UserSettings,
)


def _evaluation(runtime, spec):
    registered = runtime.procedures.get(spec.graph_fingerprint)
    if registered is None:
        raise HTTPException(
            409,
            "procedure version is no longer registered",
        )

    graph, features, safety = registered
    return runtime.contexts.evaluate(
        spec.session_id,
        graph,
        features,
        safety=safety,
    )


def correction_options(runtime, spec):
    """Report current availability without recording an interaction."""
    evaluation = _evaluation(runtime, spec)
    candidates = evaluation.feasibility.feasible_candidates()
    accepted = runtime.feedback.get(spec.exposure_id)

    options = []
    for code, (dimension, value, label) in CORRECTION_CHOICES.items():
        available = any(
            getattr(candidate, dimension) == value
            for candidate in candidates
        )
        options.append(
            CorrectionOption(
                code=code,
                label=label,
                dimension=dimension,
                value=value,
                selected_in_original=(
                    getattr(spec.configuration, dimension) == value
                ),
                available_for_future=available,
                unavailable_reason=(
                    None
                    if available
                    else (
                        "Unavailable under current structure, history, "
                        "content-safety, accessibility or explicit locks. "
                        "See feasibility decisions."
                    )
                ),
            )
        )

    return CorrectionOptions(
        session_revision=evaluation.snapshot.revision,
        feedback_eligible=(
            accepted is not None
            and accepted.receipt.feedback.rating
            in {"need_more", "too_much"}
        ),
        choices=tuple(options),
    )


def record_correction(runtime, spec, request):
    """Record one optional diagnostic against accepted primary feedback."""
    if (
        request.presentation_id != spec.presentation_id
        or request.configuration_id
        != spec.configuration.configuration_id
        or request.decision_id != spec.decision_id
    ):
        raise HTTPException(
            409,
            "correction presentation identity mismatch",
        )

    accepted = runtime.feedback.get(spec.exposure_id)
    if (
        accepted is None
        or accepted.receipt.feedback.rating == "about_right"
    ):
        raise HTTPException(
            409,
            "correction requires accepted need_more or too_much feedback",
        )

    reasons = tuple(sorted(request.reasons))
    previous = runtime.corrections.get(spec.exposure_id)
    if previous is not None:
        if previous.reasons != reasons:
            raise HTTPException(
                409,
                "a different correction was already recorded",
            )
        return previous

    receipt = accepted.receipt
    record = CorrectionRecord(
        session_id=spec.session_id,
        exposure_id=spec.exposure_id,
        presentation_id=spec.presentation_id,
        configuration_id=spec.configuration.configuration_id,
        decision_id=spec.decision_id,
        graph_fingerprint=spec.graph_fingerprint,
        rating=receipt.feedback.rating,
        origin=receipt.feedback.origin,
        acknowledgment_event_id=receipt.acknowledgment_event_id,
        feedback_posterior_revision=(
            receipt.resulting_posterior_revision
        ),
        recorded_at=datetime.now(timezone.utc),
        reasons=reasons,
    )

    if record.recorded_at < accepted.accepted_at:
        raise HTTPException(
            409,
            "clock moved before feedback acceptance",
        )

    runtime.corrections[spec.exposure_id] = record
    return record


def apply_correction(runtime, spec, request):
    """Explicitly apply the recorded choices as future soft preferences.

    A successful retry returns the original application. It does not apply
    preferences again after later user changes.
    """
    record = runtime.corrections.get(spec.exposure_id)
    if record is None:
        raise HTTPException(404, "no recorded correction")

    if record.application is not None:
        if (
            request.expected_revision
            != record.application.expected_revision
        ):
            raise HTTPException(
                409,
                "correction was already applied; use current context "
                "to make another change",
            )
        return record

    before = runtime.session(spec.session_id)
    if before.revision != request.expected_revision:
        raise HTTPException(409, "session revision changed")

    values = preference_values(record.reasons)
    evaluation = _evaluation(runtime, spec)

    jointly_available = any(
        all(
            getattr(candidate, name) == value
            for name, value in values.items()
        )
        for candidate in evaluation.feasibility.feasible_candidates()
    )
    if not jointly_available:
        raise HTTPException(
            409,
            detail={
                "code": "correction_not_currently_feasible",
                "message": (
                    "These preferences cannot currently be satisfied "
                    "together. Hard locks and accessibility settings "
                    "were preserved."
                ),
                "evaluation": evaluation.model_dump(mode="json"),
            },
        )

    after = runtime.contexts.update_context(
        spec.session_id,
        ContextUpdate(preferences=SoftPreferences(**values)),
        expected_revision=request.expected_revision,
    )

    event_id = None
    if after.revision != before.revision:
        event_id = runtime.contexts.event_history(
            spec.session_id
        )[-1].event_id

    application = PreferenceApplication(
        expected_revision=request.expected_revision,
        applied_at=datetime.now(timezone.utc),
        before=before,
        after=after,
        preference_event_id=event_id,
    )

    if application.applied_at < max(
        record.recorded_at,
        after.updated_at,
    ):
        raise HTTPException(
            409,
            "clock moved before correction application",
        )

    updated = CorrectionRecord(
        **{
            name: getattr(record, name)
            for name in type(record).model_fields
            if name != "application"
        },
        application=application,
    )
    runtime.corrections[spec.exposure_id] = updated
    return updated


def _session_at(contexts, session_id, revision):
    """Reconstruct a historical context revision without changing it."""
    current = contexts.get_session(session_id)
    if revision > current.revision:
        raise ValueError("future context revision")

    settings = UserSettings()
    timestamp = current.created_at

    for event in contexts.event_history(session_id):
        if event.sequence > revision:
            break
        if isinstance(event, PreferenceChange):
            settings = event.after

        timestamp = (
            event.acknowledged_at
            if isinstance(event, PresentationExposure)
            else event.occurred_at
        )

    return GuestSession(
        session_id=session_id,
        created_at=current.created_at,
        updated_at=timestamp,
        revision=revision,
        settings=settings,
    )


def restore_corrections(
    records,
    presentations,
    feedback,
    contexts,
):
    """Validate diagnostic and preference attribution before publishing state."""
    restored = {}
    applied_event_ids = set()

    try:
        for record in records:
            spec = presentations.get(record.exposure_id)
            accepted = feedback.get(record.exposure_id)
            if (
                spec is None
                or accepted is None
                or record.exposure_id in restored
            ):
                raise ValueError(
                    "missing or duplicate correction attribution"
                )

            receipt = accepted.receipt
            if (
                record.session_id != spec.session_id
                or record.presentation_id != spec.presentation_id
                or record.configuration_id
                != spec.configuration.configuration_id
                or record.decision_id != spec.decision_id
                or record.graph_fingerprint != spec.graph_fingerprint
                or record.rating != receipt.feedback.rating
                or record.origin != receipt.feedback.origin
                or record.acknowledgment_event_id
                != receipt.acknowledgment_event_id
                or record.feedback_posterior_revision
                != receipt.resulting_posterior_revision
                or record.recorded_at < accepted.accepted_at
            ):
                raise ValueError(
                    "correction differs from original feedback"
                )

            application = record.application
            if application is not None:
                before = application.before
                after = application.after

                if (
                    before.session_id != record.session_id
                    or after.session_id != record.session_id
                    or application.expected_revision != before.revision
                    or before != _session_at(
                        contexts,
                        record.session_id,
                        before.revision,
                    )
                    or after != _session_at(
                        contexts,
                        record.session_id,
                        after.revision,
                    )
                    or application.applied_at < max(
                        record.recorded_at,
                        after.updated_at,
                    )
                ):
                    raise ValueError(
                        "invalid correction application context"
                    )

                preferences = before.settings.preferences.model_dump()
                preferences.update(preference_values(record.reasons))
                expected_settings = before.settings.model_dump()
                expected_settings["preferences"] = preferences

                if after.settings.model_dump() != expected_settings:
                    raise ValueError(
                        "application changed unrelated settings"
                    )

                if before.settings == after.settings:
                    if (
                        after != before
                        or application.preference_event_id is not None
                    ):
                        raise ValueError(
                            "invalid no-op preference application"
                        )
                else:
                    event = next(
                        (
                            item
                            for item in contexts.event_history(
                                record.session_id
                            )
                            if item.event_id
                            == application.preference_event_id
                        ),
                        None,
                    )
                    if (
                        not isinstance(event, PreferenceChange)
                        or after.revision != before.revision + 1
                        or event.sequence != after.revision
                        or event.before != before.settings
                        or event.after != after.settings
                        or event.occurred_at < record.recorded_at
                        or event.event_id in applied_event_ids
                    ):
                        raise ValueError(
                            "missing or duplicated preference attribution"
                        )
                    applied_event_ids.add(event.event_id)

            restored[record.exposure_id] = record

    except (ValueError, KeyError) as exc:
        raise StateStoreError(
            "saved correction attribution differs"
        ) from exc

    return restored