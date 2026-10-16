"""Personalization gates for the independent development application.

These checks are local demonstration controls, not account authentication.
Legacy research sessions may be allowed explicitly by the app factory;
the normal environment-created server disables that compatibility mode.
"""

from fastapi import HTTPException

from app.core.state_store import StateStoreError
from app.models.guidance import GuidanceStatus


def profile_for_session(runtime, session_id):
    profiles = [
        profile
        for profile in runtime.profiles.values()
        if profile.session_id == session_id
    ]
    if len(profiles) > 1:
        raise StateStoreError("multiple profiles refer to one context session")
    return profiles[0] if profiles else None


def guidance_status(runtime, session_id):
    session = runtime.session(session_id)
    profile = profile_for_session(runtime, session_id)
    return GuidanceStatus(
        session_id=session_id,
        session_revision=session.revision,
        profile_id=profile.profile_id if profile else None,
        profile_revision=profile.revision if profile else None,
        personalization_enabled=(
            profile.personalization_enabled if profile else False
        ),
    )


def require_personalization(runtime, session_id, *, allow_legacy=False):
    runtime.session(session_id)
    profile = profile_for_session(runtime, session_id)
    if profile is None and allow_legacy:
        return None
    if profile is None or not profile.personalization_enabled:
        raise HTTPException(
            409,
            detail={
                "code": "personalization_not_enabled",
                "message": (
                    "Use standard guidance, or explicitly enable personalization "
                    "for a demonstration profile."
                ),
            },
        )
    return profile


def episode_is_active(runtime, offer, *, allow_legacy=False):
    profile = profile_for_session(runtime, offer.session_id)
    if profile is None:
        return allow_legacy
    if not profile.personalization_enabled:
        return False
    # Disabling personalization ends the old adaptive episode for new
    # displays, even if personalization is subsequently enabled again.
    return not any(
        not change.enabled and change.occurred_at >= offer.offered_at
        for change in profile.personalization_changes
    )


def require_active_episode(runtime, offer, *, allow_legacy=False):
    if not episode_is_active(runtime, offer, allow_legacy=allow_legacy):
        raise HTTPException(
            409,
            detail={
                "code": "adaptive_episode_inactive",
                "message": (
                    "This adaptive episode is no longer active for new displays. "
                    "Request fresh guidance. Previously acknowledged feedback "
                    "remains attributed to its original decision."
                ),
            },
        )
