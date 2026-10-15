"""Independent API tests. No API keys, network calls or learning updates."""

import pytest
from fastapi.testclient import TestClient

from app.dev_main import create_app
from tests.test_explanations import FakeProvider


@pytest.fixture
def api():
    application = create_app(provider=FakeProvider(failure="offline_test"))
    with TestClient(application) as client:
        yield client


def start(client):
    procedures = client.get("/dev/v1/procedures")
    assert procedures.status_code == 200
    procedure_id = procedures.json()[0]["procedure_id"]

    response = client.post("/dev/v1/sessions")
    assert response.status_code == 201
    return procedure_id, response.json()


def select(client, procedure_id, session, **extra):
    return client.post(
        f"/dev/v1/sessions/{session['session_id']}/presentations",
        json={
            "procedure_id": procedure_id,
            "expected_revision": session["revision"],
            **extra,
        },
    )


def ack_body(spec, actions=None):
    return {
        "presentation_id": spec["presentation_id"],
        "configuration_id": spec["configuration"]["configuration_id"],
        "displayed_action_ids": (
            spec["acknowledgment_action_ids"] if actions is None else actions
        ),
    }


def test_complete_offline_api_flow_and_idempotent_acknowledgment(api):
    procedure_id, session = start(api)
    base = f"/dev/v1/sessions/{session['session_id']}"

    response = select(api, procedure_id, session)
    assert response.status_code == 201, response.text
    spec = response.json()["spec"]
    assert spec["explanation"]["origin"] == "fallback"
    assert spec["explanation"]["source_status"] == "synthetic"
    assert not response.json()["stale_for_display"]

    evaluation = api.get(f"{base}/feasibility/{procedure_id}").json()
    assert evaluation["snapshot"]["matching_exposure_count"] == 0

    presentation_url = f"{base}/presentations/{spec['exposure_id']}"
    repeated = api.get(presentation_url)
    assert repeated.status_code == 200
    assert repeated.json()["spec"] == spec
    assert api.get(
        f"{base}/feasibility/{procedure_id}"
    ).json()["snapshot"]["matching_exposure_count"] == 0

    body = ack_body(spec, ["action:request_token"])
    first = api.post(presentation_url + "/ack", json=body)
    second = api.post(presentation_url + "/ack", json=body)
    assert first.status_code == 200, first.text
    assert second.json() == first.json()

    evaluation = api.get(f"{base}/feasibility/{procedure_id}").json()
    assert evaluation["snapshot"]["matching_exposure_count"] == 1
    assert evaluation["snapshot"]["recap_action_ids"] == ["action:request_token"]
    assert sum(
        decision["accepted"]
        for decision in evaluation["feasibility"]["decisions"]
    ) == 16
    assert api.app.state.runtime.policy.posterior_revision == 0

    conflicting = api.post(
        presentation_url + "/ack",
        json=ack_body(spec, ["action:collect_pack"]),
    )
    assert conflicting.status_code == 409


def test_context_updates_are_strict_revision_checked_and_preserve_locks(api):
    procedure_id, session = start(api)
    base = f"/dev/v1/sessions/{session['session_id']}"
    response = api.patch(
        base + "/context",
        json={
            "expected_revision": 0,
            "update": {
                "navigation_capability": 3,
                "locks": {"presentation_mode": "GUIDED"},
            },
        },
    )
    assert response.status_code == 200, response.text
    current = response.json()
    assert current["revision"] == 1
    assert current["settings"]["navigation_capability"] == 3

    stale = api.patch(
        base + "/context",
        json={"expected_revision": 0, "update": {"navigation_capability": 4}},
    )
    assert stale.status_code == 409

    invalid = api.patch(
        base + "/context",
        json={"expected_revision": 1, "update": {"navigation_capability": "3"}},
    )
    assert invalid.status_code == 422

    response = select(
        api, procedure_id, current, focus_action_id="action:collect_pack"
    )
    assert response.status_code == 201, response.text
    spec = response.json()["spec"]
    assert spec["initial_action_id"] == "action:collect_pack"
    assert spec["acknowledgment_action_ids"] == ["action:collect_pack"]

    wrong_scope = api.post(
        base + f"/presentations/{spec['exposure_id']}/ack",
        json=ack_body(spec, ["action:request_token"]),
    )
    assert wrong_scope.status_code == 422


def test_conflicting_preferences_return_explanations_without_relaxing_locks(api):
    procedure_id, session = start(api)
    base = f"/dev/v1/sessions/{session['session_id']}"
    current = api.patch(
        base + "/context",
        json={
            "expected_revision": 0,
            "update": {
                "locks": {"relationship_visual": "DEPENDENCY_MAP"},
                "accessibility": {"allow_relationship_visuals": False},
            },
        },
    ).json()

    response = select(api, procedure_id, current)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "no_feasible_configuration"
    stored = api.get(base).json()
    assert stored["settings"]["locks"]["relationship_visual"] == "DEPENDENCY_MAP"


def test_presentations_are_session_scoped_and_ids_are_checked(api):
    procedure_id, session = start(api)
    spec = select(api, procedure_id, session).json()["spec"]
    other = api.post("/dev/v1/sessions").json()

    foreign = (
        f"/dev/v1/sessions/{other['session_id']}"
        f"/presentations/{spec['exposure_id']}"
    )
    assert api.get(foreign).status_code == 404
    assert api.post(foreign + "/ack", json=ack_body(spec)).status_code == 404

    own = (
        f"/dev/v1/sessions/{session['session_id']}"
        f"/presentations/{spec['exposure_id']}"
    )
    body = ack_body(spec)
    body["presentation_id"] = "wrong"
    assert api.post(own + "/ack", json=body).status_code == 409
    assert api.get(own + "/inspector").status_code == 200


def test_preference_change_marks_existing_document_stale_without_rewriting_it(api):
    procedure_id, session = start(api)
    spec = select(api, procedure_id, session).json()["spec"]
    base = f"/dev/v1/sessions/{session['session_id']}"

    updated = api.patch(
        base + "/context",
        json={
            "expected_revision": 0,
            "update": {"locks": {"presentation_mode": "GUIDED"}},
        },
    )
    assert updated.status_code == 200

    previous = api.get(
        base + f"/presentations/{spec['exposure_id']}"
    ).json()
    assert previous["stale_for_display"]
    assert previous["spec"] == spec

    fresh = select(api, procedure_id, updated.json()).json()
    assert not fresh["stale_for_display"]
    assert fresh["spec"]["configuration"]["presentation_mode"] == "GUIDED"
    assert fresh["spec"]["exposure_id"] != spec["exposure_id"]


def test_mocked_generation_integrates_without_a_real_provider():
    provider = FakeProvider()
    with TestClient(create_app(provider=provider)) as client:
        procedure_id, session = start(client)
        response = select(client, procedure_id, session)
        assert response.status_code == 201, response.text
        assert response.json()["spec"]["explanation"]["origin"] == "generated"
        assert len(provider.calls) == 2
        assert client.app.state.runtime.contexts.event_history(
            session["session_id"]
        ) == ()


def test_default_app_is_offline_even_when_an_api_key_environment_exists(monkeypatch):
    monkeypatch.delenv("C4_DEV_LLM_ENABLED", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "not-a-real-test-key")

    with TestClient(create_app()) as client:
        procedure_id, session = start(client)
        response = select(client, procedure_id, session)
        assert response.status_code == 201, response.text
        explanation = response.json()["spec"]["explanation"]
        assert explanation["origin"] == "fallback"
        assert "provider_disabled" in explanation["diagnostics"]


def test_development_app_does_not_replace_shared_routes(api):
    assert api.get("/health").json()["service"] == "c4-independent-dev"
    assert api.post("/v1/render", json={}).status_code == 404