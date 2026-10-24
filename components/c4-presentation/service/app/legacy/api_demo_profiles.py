"""Local demo-profile routes. These endpoints do not authenticate users."""

from fastapi import APIRouter

from app.host.demo_profiles import (
    create_profile,
    get_profile,
    profile_response,
    set_personalization,
)
from app.models.demo_profiles import (
    CreateDemoProfileRequest,
    DemoProfile,
    DemoProfileResponse,
    PersonalizationRequest,
)


def register_demo_profile_routes(application, runtime):
    router = APIRouter(
        prefix="/dev/v1/demo-profiles",
        tags=["demo profiles"],
    )

    @router.get("", response_model=list[DemoProfile])
    def list_profiles():
        current = runtime()
        with current.lock:
            return [
                current.profiles[key]
                for key in sorted(current.profiles)
            ]

    @router.post(
        "",
        response_model=DemoProfileResponse,
        status_code=201,
    )
    def create_demo_profile(request: CreateDemoProfileRequest):
        current = runtime()
        with current.change():
            return create_profile(current, request)

    @router.get(
        "/{profile_id}",
        response_model=DemoProfileResponse,
    )
    def retrieve_demo_profile(profile_id: str):
        current = runtime()
        with current.lock:
            profile = get_profile(current, profile_id)
            return profile_response(current, profile)

    @router.patch(
        "/{profile_id}/personalization",
        response_model=DemoProfileResponse,
    )
    def update_personalization(
        profile_id: str,
        request: PersonalizationRequest,
    ):
        current = runtime()
        with current.change():
            return set_personalization(current, profile_id, request)

    application.include_router(router)