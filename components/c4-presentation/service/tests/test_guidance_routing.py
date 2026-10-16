"""Standard/opt-in guidance contracts; fake provider only, no paid requests."""

import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.dev_main import create_app
from tests.test_explanations import FakeProvider
from tests.test_feedback_persistence import feedback_body
from tests.test_navigation import backend


def application(provider=None, **options):
    return create_app(
        provider=(
            provider
            if provider is not None
            else FakeProvider(failure="offline_test")
        ),
        allow_legacy_adaptive_sessions=False,
        **options,
    )


def anonymous(client):
    response = client.post("/dev/v1/sessions")
    assert response.status_code == 201
    return response.json()


def profile(client, *, enabled=True, lock_guided=False):
    response = client.post(
        "/dev/v1/demo-profiles",
        json={
            "profile_id": f"profile:{uuid4().hex}",
            "display_name": "Local research profile",
            "personalization_enabled": enabled,
            "initial_context": {
                "navigation_capability": 5,
                "preferences": {"presentation_mode": "GUIDED"},
                "locks": (
                    {"presentation_mode": "GUIDED"}
                    if lock_guided else {}
                ),
            },
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def session_base(session):
    return f"/dev/v1/sessions/{session['session_id']}"


def first_procedure(client):
    return client.get("/dev/v1/procedures").json()[0]["procedure_id"]


def request_guidance(client, session, *, extra=None):
    base = session_base(session)
    status = client.get(base + "/guidance-status")
    assert status.status_code == 200
    status = status.json()
    body = {
        "procedure_id": first_procedure(client),
        "expected_revision": status["session_revision"],
    }
    if status["profile_id"] is not None:
        body["expected_profile_revision"] = status["profile_revision"]
    body.update(extra or {})
    return client.post(base + "/guidance", json=body)


def change_mode(client, profile_record, enabled):
    url = f"/dev/v1/demo-profiles/{profile_record['profile_id']}/personalization"
    response = client.patch(
        url,
        json={
            "request_id": f"event:{uuid4().hex}",
            "expected_revision": profile_record["revision"],
            "enabled": enabled,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["profile"]


def display_body(spec):
    return {
        "presentation_id": spec["presentation_id"],
        "configuration_id": spec["configuration"]["configuration_id"],
        "displayed_action_ids": [spec["acknowledgment_action_ids"][0]],
    }


def presentation_url(session, spec):
    return session_base(session) + f"/presentations/{spec['exposure_id']}"


def test_standard_guidance_never_selects_or_changes_persisted_state(monkeypatch):
    with TestClient(application()) as client:
        session = anonymous(client)
        runtime = client.app.state.runtime
        before = runtime.export_state()

        def unexpected(*args, **kwargs):
            raise AssertionError("standard guidance invoked the adaptive engine")

        monkeypatch.setattr(runtime.policy, "select_and_offer", unexpected)
        monkeypatch.setattr(runtime.contexts, "evaluate", unexpected)

        first = request_guidance(client, session)
        second = request_guidance(client, session)
        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text

        result = first.json()
        document = result["guidance"]
        assert result["mode"] == "standard"
        assert result["personalization_enabled"] is False
        assert document["explanation"]["origin"] == "fallback"
        assert document["explanation"]["source_status"] == "synthetic"
        assert document["learning_eligible"] is False
        assert document["exposure_acknowledgment_required"] is False
        assert document["standard_id"] == second.json()["guidance"]["standard_id"]
        assert "decision_id" not in document
        assert "exposure_id" not in document
        assert runtime.export_state() == before

        protected = {
            (entry["kind"], entry["identifier"])
            for entry in document["explanation"]["source"]["preservation"][
                "always_visible"
            ]
        }
        rendered = {
            (card["source"]["kind"], card["source"]["identifier"])
            for card in document["cards"]
            if not card["collapsed"]
        }
        assert protected <= rendered
        assert all(not card["collapsed"] for card in document["cards"])

        # Standard identifiers cannot be used as adaptive feedback identities.
        response = client.post(
            session_base(session)
            + f"/presentations/{document['standard_id']}/feedback",
            json={
                "presentation_id": document["standard_id"],
                "configuration_id": "not-a-selected-configuration",
                "decision_id": "no-policy-decision",
                "rating": "about_right",
            },
        )
        assert response.status_code == 404
        assert runtime.export_state() == before


def test_standard_generation_reuses_checks_cache_and_excludes_profile_context():
    provider = FakeProvider()
    with TestClient(application(provider)) as client:
        created = profile(client, enabled=False)
        session = created["session"]

        response = request_guidance(client, session)
        assert response.status_code == 200, response.text
        first = response.json()["guidance"]
        repeated = request_guidance(client, session).json()["guidance"]

        assert first["explanation"]["origin"] == "generated"
        assert first["explanation"]["assurance"] == "automated_checks_only"
        assert repeated["explanation"]["cache_hit"] is True
        assert repeated["standard_id"] == first["standard_id"]
        assert len(provider.calls) == 2

        packet_text = provider.calls[0][1]
        packet = json.loads(packet_text)
        assert packet["writing_style"] == "plain"
        assert packet["presentation_kind"] == "standard"
        assert packet["configuration"] is None
        assert session["session_id"] not in packet_text
        assert created["profile"]["profile_id"] not in packet_text
        assert "navigation_capability" not in packet_text
        assert "Local research profile" not in packet_text
        assert all(unit["role"] == "required" for unit in packet["units"])


def test_rejected_standard_generation_falls_back_without_changing_source():
    provider = FakeProvider(reject=True)
    with TestClient(application(provider)) as client:
        session = anonymous(client)
        procedure_id = first_procedure(client)
        graph = client.get(f"/dev/v1/procedures/{procedure_id}/graph").json()
        result = request_guidance(client, session)
        assert result.status_code == 200, result.text
        explanation = result.json()["guidance"]["explanation"]
        assert explanation["origin"] == "fallback"
        assert explanation["assurance"] == "source_preserving_copy"
        assert "semantic_assessment_rejected" in explanation["diagnostics"]
        assert explanation["source"]["graph"] == graph


def test_standard_style_is_explicit_request_only_not_a_profile_update():
    with TestClient(application()) as client:
        session = anonymous(client)
        runtime = client.app.state.runtime
        before = runtime.export_state()

        response = request_guidance(
            client, session, extra={"standard_writing_style": "extra_plain"}
        )
        assert response.status_code == 200
        assert response.json()["guidance"]["writing_style"] == "extra_plain"
        assert runtime.export_state() == before

        assert request_guidance(
            client, session, extra={"standard_writing_style": "unsupported"}
        ).status_code == 422


def test_anonymous_and_disabled_profiles_cannot_bypass_adaptive_gate():
    with TestClient(application()) as client:
        for session in (
            anonymous(client),
            profile(client, enabled=False)["session"],
        ):
            runtime = client.app.state.runtime
            before = runtime.policy.export_state()

            response = client.post(
                session_base(session) + "/presentations",
                json={
                    "procedure_id": first_procedure(client),
                    "expected_revision": session["revision"],
                },
            )
            assert response.status_code == 409
            assert response.json()["detail"]["code"] == (
                "personalization_not_enabled"
            )
            assert request_guidance(client, session).json()["mode"] == "standard"
            assert runtime.policy.export_state() == before


def test_enabled_profile_uses_real_policy_and_feedback_attribution():
    with TestClient(application()) as client:
        created = profile(client, lock_guided=True)
        session = created["session"]
        runtime = client.app.state.runtime
        before = runtime.policy.export_state()

        response = request_guidance(client, session)
        assert response.status_code == 200, response.text
        selected = response.json()
        assert selected["mode"] == "adaptive"
        spec = selected["spec"]
        assert spec["configuration"]["presentation_mode"] == "GUIDED"
        assert runtime.policy.export_state().decision_sequence == (
            before.decision_sequence + 1
        )
        assert runtime.policy.posterior_revision == before.posterior_revision

        url = presentation_url(session, spec)
        acknowledgment = client.post(url + "/ack", json=display_body(spec))
        assert acknowledgment.status_code == 200, acknowledgment.text

        feedback = client.post(
            url + "/feedback", json=feedback_body(spec)
        )
        assert feedback.status_code == 200, feedback.text
        assert feedback.json()["receipt"]["decision_id"] == spec["decision_id"]
        assert runtime.policy.posterior_revision == before.posterior_revision + 1

        again = client.post(url + "/feedback", json=feedback_body(spec))
        assert again.json() == feedback.json()
        following = request_guidance(client, session)
        next_spec = following.json()["spec"]
        inspector = client.get(
            presentation_url(session, next_spec) + "/inspector"
        ).json()
        assert inspector["decision"]["posterior_revision"] == (
            before.posterior_revision + 1
        )


def test_disabling_blocks_new_display_but_preserves_acknowledged_feedback():
    with TestClient(application()) as client:
        created = profile(client, lock_guided=True)
        session = created["session"]
        spec = request_guidance(client, session).json()["spec"]
        url = presentation_url(session, spec)
        ack_request = display_body(spec)
        acknowledgment = client.post(url + "/ack", json=ack_request)
        assert acknowledgment.status_code == 200

        runtime = client.app.state.runtime
        revision = runtime.session(session["session_id"]).revision
        navigation = {
            "event_id": f"event:{uuid4().hex}",
            "expected_revision": revision,
            "presentation_id": spec["presentation_id"],
            "configuration_id": spec["configuration"]["configuration_id"],
            "action_id": spec["pages"][1]["action_id"],
        }
        displayed = client.post(url + "/navigation", json=navigation)
        assert displayed.status_code == 200, displayed.text

        disabled = change_mode(client, created["profile"], False)
        assert client.get(url).json()["stale_for_display"] is True
        assert request_guidance(client, session).json()["mode"] == "standard"
        assert client.post(url + "/ack", json=ack_request).json() == (
            acknowledgment.json()
        )
        assert client.post(url + "/navigation", json=navigation).json() == (
            displayed.json()
        )

        new_navigation = dict(
            navigation,
            event_id=f"event:{uuid4().hex}",
            expected_revision=runtime.session(session["session_id"]).revision,
            action_id=spec["pages"][0]["action_id"],
        )
        before_feedback = runtime.policy.posterior_revision
        assert client.post(
            url + "/navigation", json=new_navigation
        ).status_code == 409

        accepted = client.post(url + "/feedback", json=feedback_body(spec))
        assert accepted.status_code == 200, accepted.text
        assert runtime.policy.posterior_revision == before_feedback + 1

        change_mode(client, disabled, True)
        # Re-enabling does not resurrect the old episode.
        assert client.post(
            url + "/navigation", json=new_navigation
        ).status_code == 409
        assert request_guidance(client, session).json()["mode"] == "adaptive"


def test_unacknowledged_old_offer_cannot_be_acknowledged_after_disabling():
    with TestClient(application()) as client:
        created = profile(client)
        session = created["session"]
        spec = request_guidance(client, session).json()["spec"]
        url = presentation_url(session, spec)
        change_mode(client, created["profile"], False)
        runtime = client.app.state.runtime
        before = runtime.export_state()

        assert client.post(
            url + "/ack", json=display_body(spec)
        ).status_code == 409
        assert client.post(
            url + "/feedback", json=feedback_body(spec)
        ).status_code == 409
        assert runtime.export_state() == before


def test_revisions_and_standard_only_controls_are_checked():
    with TestClient(application()) as client:
        created = profile(client)
        session = created["session"]

        assert request_guidance(
            client, session, extra={"expected_profile_revision": 99}
        ).status_code == 409
        assert request_guidance(
            client, session, extra={"expected_revision": 99}
        ).status_code == 409
        assert request_guidance(
            client, session, extra={"standard_writing_style": "concise"}
        ).status_code == 422
        assert client.post(
            session_base(session) + "/guidance",
            json={
                "procedure_id": first_procedure(client),
                "expected_revision": session["revision"],
            },
        ).status_code == 409

        other = anonymous(client)
        assert request_guidance(
            client, other, extra={"focus_action_id": "action:request_token"}
        ).status_code == 422
        assert request_guidance(
            client, other, extra={"procedure_id": "unknown-procedure"}
        ).status_code == 404


def test_standard_retains_all_three_scenarios_without_optional_scaffolds():
    with TestClient(application()) as client:
        session = anonymous(client)
        runtime = client.app.state.runtime
        before = runtime.export_state()
        for procedure in client.get("/dev/v1/procedures").json():
            response = request_guidance(
                client,
                session,
                extra={"procedure_id": procedure["procedure_id"]},
            )
            assert response.status_code == 200, response.text
            document = response.json()["guidance"]
            assert len(document["pages"]) == len(procedure["action_ids"])
            kinds = {card["source"]["kind"] for card in document["cards"]}
            if procedure["plan_id"] == "synthetic-conditional-v1":
                assert "branch_group" in kinds
                assert "condition" in kinds
            elif procedure["plan_id"] == "synthetic-parallel-v1":
                assert "parallel_group" in kinds
            assert "diagram" not in document
            assert "recap" not in document
        assert runtime.export_state() == before


def test_existing_factory_legacy_research_mode_remains_explicitly_available():
    provider = FakeProvider(failure="offline_test")
    with TestClient(create_app(
        provider=provider,
        allow_legacy_adaptive_sessions=True,
    )) as client:
        session = anonymous(client)
        response = client.post(
            session_base(session) + "/presentations",
            json={
                "procedure_id": first_procedure(client),
                "expected_revision": session["revision"],
            },
        )
        assert response.status_code == 201, response.text
        # The new frontend route never interprets compatibility as opt-in.
        assert request_guidance(client, session).json()["mode"] == "standard"


def test_routing_recovers_existing_runtime_without_a_schema_migration(backend):
    # Reuse the existing isolated SQLite/PostgreSQL persistence fixture.
    with TestClient(backend["application"]()) as client:
        created = profile(client, lock_guided=True)
        session = created["session"]
        spec = request_guidance(client, session).json()["spec"]
        url = presentation_url(session, spec)
        assert client.post(url + "/ack", json=display_body(spec)).status_code == 200
        accepted = client.post(url + "/feedback", json=feedback_body(spec))
        assert accepted.status_code == 200
        change_mode(client, created["profile"], False)
        saved = client.app.state.runtime.export_state()
        assert saved.format_version == "c4-runtime-state-1.3"

    with TestClient(backend["application"]()) as client:
        runtime = client.app.state.runtime
        assert runtime.export_state() == saved
        assert request_guidance(client, session).json()["mode"] == "standard"
        assert runtime.export_state() == saved
        assert client.post(
            url + "/feedback", json=feedback_body(spec)
        ).json() == accepted.json()
        assert runtime.policy.posterior_revision == saved.policy.posterior_revision
