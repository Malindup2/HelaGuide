"""Demo-profile operations under the existing DevRuntime transaction lock."""

import hashlib
import json
from datetime import datetime, timezone

from fastapi import HTTPException

from app.errors import StateStoreError
from app.models.demo_profiles import (
    DemoProfile,
    DemoProfileResponse,
    PersonalizationChange,
)
from app.models.user_context import ContextUpdate


def _creation_fingerprint(request):
    document = request.model_dump(mode="json")

    # Familiarity selections are a set of service-specific answers.
    document["initial_context"]["familiarity"].sort(
        key=lambda item: item["service_id"]
    )

    payload = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _known_service_ids(runtime):
    return {
        stage.service_id
        for graph, _, _ in runtime.procedures.values()
        for stage in graph.stages
    }


def get_profile(runtime, profile_id):
    try:
        return runtime.profiles[profile_id]
    except KeyError:
        raise HTTPException(404, "unknown demo profile") from None


def profile_response(runtime, profile):
    return DemoProfileResponse(
        profile=profile,
        session=runtime.session(profile.session_id),
    )


def create_profile(runtime, request):
    """Create profile and context together, or return an exact retry."""

    fingerprint = _creation_fingerprint(request)
    existing = runtime.profiles.get(request.profile_id)

    if existing is not None:
        if existing.creation_fingerprint != fingerprint:
            raise HTTPException(
                409,
                "this profile ID was already used with different creation data",
            )
        return profile_response(runtime, existing)

    known = _known_service_ids(runtime)
    unknown = {
        report.service_id
        for report in request.initial_context.familiarity
        if report.service_id not in known
    }
    if unknown:
        raise HTTPException(
            422,
            "familiarity refers to a service not present in registered procedures",
        )

    session = runtime.contexts.create_session()
    initial = request.initial_context

    session = runtime.contexts.update_context(
        session.session_id,
        ContextUpdate(
            navigation_capability=initial.navigation_capability,
            preferences=initial.preferences,
            locks=initial.locks,
            accessibility=initial.accessibility,
        ),
        expected_revision=session.revision,
    )

    for report in sorted(
        initial.familiarity,
        key=lambda item: item.service_id,
    ):
        session = runtime.contexts.update_context(
            session.session_id,
            ContextUpdate(familiarity=report),
            expected_revision=session.revision,
        )

    now = max(
        datetime.now(timezone.utc),
        session.updated_at,
    )
    profile = DemoProfile(
        profile_id=request.profile_id,
        display_name=request.display_name,
        session_id=session.session_id,
        created_at=now,
        updated_at=now,
        revision=0,
        initial_personalization_enabled=request.personalization_enabled,
        personalization_enabled=request.personalization_enabled,
        creation_fingerprint=fingerprint,
    )
    runtime.profiles[profile.profile_id] = profile
    return profile_response(runtime, profile)


def set_personalization(runtime, profile_id, request):
    """Record an explicit setting operation without selecting or learning."""

    profile = get_profile(runtime, profile_id)

    for previous in profile.personalization_changes:
        if previous.request_id == request.request_id:
            if (
                previous.expected_revision != request.expected_revision
                or previous.enabled != request.enabled
            ):
                raise HTTPException(
                    409,
                    "personalization request ID was reused with different data",
                )

            # Return current state, rather than reapplying an old setting.
            return profile_response(runtime, profile)

    if request.expected_revision != profile.revision:
        raise HTTPException(409, "demo profile revision changed")

    now = max(datetime.now(timezone.utc), profile.updated_at)
    event = PersonalizationChange(
        request_id=request.request_id,
        expected_revision=request.expected_revision,
        enabled=request.enabled,
        occurred_at=now,
    )

    values = {
        name: getattr(profile, name)
        for name in type(profile).model_fields
    }
    values.update(
        updated_at=now,
        revision=profile.revision + 1,
        personalization_enabled=request.enabled,
        personalization_changes=(
            *profile.personalization_changes,
            event,
        ),
    )
    updated = DemoProfile(**values)
    runtime.profiles[profile_id] = updated
    return profile_response(runtime, updated)


def restore_profiles(records, contexts):
    """Validate every association before publishing recovered runtime state."""

    profiles = {}
    session_ids = set()

    for record in records:
        try:
            # Revalidate even if an internal caller supplied model_copy data.
            profile = DemoProfile.model_validate_json(
                record.model_dump_json(round_trip=True)
            )
            session = contexts.get_session(profile.session_id)
        except ValueError as exc:
            raise StateStoreError(
                "saved demo profile or context association is invalid"
            ) from exc

        if (
            profile.profile_id in profiles
            or profile.session_id in session_ids
            or profile.created_at < session.created_at
        ):
            raise StateStoreError(
                "duplicate or inconsistent saved demo profile association"
            )

        profiles[profile.profile_id] = profile
        session_ids.add(profile.session_id)

    return profiles