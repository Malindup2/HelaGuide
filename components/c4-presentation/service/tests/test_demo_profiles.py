"""Demo-profile creation, isolation and recovery without live LLM calls."""

import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.legacy.navigation_migration import (
    canonical,
    checksum,
    manifest_for,
)
from app.legacy.state_store import StateCompatibilityError, StateStoreError
from app.dev_main import create_app
from app.models.policy import PolicyConfig
from app.models.runtime_state_v1_2 import (
    RuntimeState as CorrectionRuntimeState,
)
from tests.test_explanations import FakeProvider
from tests.test_feedback_persistence import feedback_body
from tests.test_navigation import backend, prepare


def application():
    return create_app(
        provider=FakeProvider(failure="offline_test"),
    )


def creation_body(client, *, enabled=True):
    procedures = client.get("/dev/v1/procedures").json()
    service_ids = list(
        dict.fromkeys(
            procedure["requested_service_id"]
            for procedure in procedures
        )
    )
    return {
        "profile_id": f"profile:{uuid4().hex}",
        "display_name": "Demo citizen A",
        "personalization_enabled": enabled,
        "initial_context": {
            "navigation_capability": 3,
            "preferences": {"presentation_mode": "GUIDED"},
            "familiarity": [
                {"service_id": service_ids[0], "score": 4},
                {"service_id": service_ids[1], "score": None},
            ],
        },
    }


def create(client, body):
    response = client.post("/dev/v1/demo-profiles", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def profile_url(profile):
    return f"/dev/v1/demo-profiles/{profile['profile_id']}"


def test_creation_retrieval_and_retry_do_not_select_or_learn():
    with TestClient(application()) as client:
        body = creation_body(client)
        runtime = client.app.state.runtime
        before_policy = runtime.policy.export_state()

        first = create(client, body)
        second = create(client, body)

        assert first == second
        assert len(runtime.contexts.export_state()) == 1
        assert runtime.policy.export_state() == before_policy
        assert runtime.presentations == {}
        assert runtime.feedback == {}

        profile = first["profile"]
        session = first["session"]

        assert profile["personalization_enabled"] is True
        assert profile["revision"] == 0
        assert profile["session_id"] == session["session_id"]

        settings = session["settings"]
        assert settings["navigation_capability"] == 3
        assert settings["preferences"]["presentation_mode"] == "GUIDED"
        assert settings["locks"]["presentation_mode"] is None

        reports = {
            item["service_id"]: item["score"]
            for item in settings["familiarity"]
        }
        expected_reports = {
            item["service_id"]: item["score"]
            for item in body["initial_context"]["familiarity"]
        }
        assert reports == expected_reports

        retrieved = client.get(profile_url(profile))
        assert retrieved.status_code == 200
        assert retrieved.json() == first

        listed = client.get("/dev/v1/demo-profiles")
        assert listed.status_code == 200
        assert listed.json() == [profile]

        # Reordered familiarity chips remain an equivalent retry.
        body["initial_context"]["familiarity"].reverse()
        assert create(client, body) == first

        body["display_name"] = "Different creation request"
        assert client.post(
            "/dev/v1/demo-profiles", json=body
        ).status_code == 409
        assert len(runtime.contexts.export_state()) == 1


def test_invalid_creation_does_not_leave_an_orphan_session():
    with TestClient(application()) as client:
        runtime = client.app.state.runtime

        body = creation_body(client)
        body["initial_context"]["familiarity"][0]["service_id"] = (
            "svc:not_registered"
        )
        assert client.post(
            "/dev/v1/demo-profiles", json=body
        ).status_code == 422
        assert runtime.contexts.export_state() == ()
        assert runtime.profiles == {}

        body = creation_body(client)
        body["initial_context"]["familiarity"].append(
            body["initial_context"]["familiarity"][0]
        )
        assert client.post(
            "/dev/v1/demo-profiles", json=body
        ).status_code == 422
        assert runtime.contexts.export_state() == ()

        body = creation_body(client)
        body["personalization_enabled"] = "true"
        assert client.post(
            "/dev/v1/demo-profiles", json=body
        ).status_code == 422
        assert runtime.contexts.export_state() == ()


def test_personalization_changes_are_explicit_revisioned_and_retry_safe():
    with TestClient(application()) as client:
        body = {
            "profile_id": f"profile:{uuid4().hex}",
            "display_name": "Demo citizen",
        }
        created = create(client, body)
        profile = created["profile"]
        url = profile_url(profile)
        runtime = client.app.state.runtime

        assert profile["personalization_enabled"] is False
        assert created["session"]["settings"]["navigation_capability"] is None
        assert created["session"]["settings"]["familiarity"] == []

        before_policy = runtime.policy.export_state()
        before_context = runtime.contexts.export_state()

        enable = {
            "request_id": f"event:{uuid4().hex}",
            "expected_revision": 0,
            "enabled": True,
        }
        first = client.patch(url + "/personalization", json=enable)
        assert first.status_code == 200, first.text
        assert first.json()["profile"]["revision"] == 1
        assert first.json()["profile"]["personalization_enabled"] is True

        repeat = client.patch(url + "/personalization", json=enable)
        assert repeat.json() == first.json()

        conflicting_retry = dict(enable, enabled=False)
        assert client.patch(
            url + "/personalization", json=conflicting_retry
        ).status_code == 409

        stale = {
            "request_id": f"event:{uuid4().hex}",
            "expected_revision": 0,
            "enabled": False,
        }
        assert client.patch(
            url + "/personalization", json=stale
        ).status_code == 409

        disable = {
            "request_id": f"event:{uuid4().hex}",
            "expected_revision": 1,
            "enabled": False,
        }
        disabled = client.patch(url + "/personalization", json=disable)
        assert disabled.status_code == 200
        assert disabled.json()["profile"]["revision"] == 2
        assert disabled.json()["profile"]["personalization_enabled"] is False

        # A late retry of the original enable must not enable it again.
        late_retry = client.patch(url + "/personalization", json=enable)
        assert late_retry.status_code == 200
        assert late_retry.json() == disabled.json()

        assert runtime.contexts.export_state() == before_context
        assert runtime.policy.export_state() == before_policy


def test_profiles_keep_context_isolated_and_creation_retry_does_not_reset_it():
    with TestClient(application()) as client:
        first_body = creation_body(client)
        first = create(client, first_body)
        second = create(client, creation_body(client))

        assert first["session"]["session_id"] != second["session"]["session_id"]

        session = first["session"]
        updated = client.patch(
            f"/dev/v1/sessions/{session['session_id']}/context",
            json={
                "expected_revision": session["revision"],
                "update": {"navigation_capability": 5},
            },
        )
        assert updated.status_code == 200

        returned = client.get(profile_url(first["profile"])).json()
        assert returned["session"]["settings"]["navigation_capability"] == 5

        other = client.get(profile_url(second["profile"])).json()
        assert other["session"]["settings"]["navigation_capability"] == 3

        retry = create(client, first_body)
        assert retry["session"] == returned["session"]
        assert len(client.app.state.runtime.contexts.export_state()) == 2


def test_failed_creation_rolls_back_context_and_profile(monkeypatch):
    import app.host.demo_profiles as profile_module

    with TestClient(application()) as client:
        body = creation_body(client)
        runtime = client.app.state.runtime
        before = runtime.export_state()

        def fail_response(*args, **kwargs):
            raise RuntimeError("simulated failure after profile construction")

        monkeypatch.setattr(profile_module, "profile_response", fail_response)

        with pytest.raises(RuntimeError, match="simulated failure"):
            client.post("/dev/v1/demo-profiles", json=body)

        assert runtime.export_state() == before


def test_profile_and_setting_recover_with_original_context(backend):
    with TestClient(backend["application"]()) as client:
        body = creation_body(client)
        created = create(client, body)
        url = profile_url(created["profile"])

        setting = {
            "request_id": f"event:{uuid4().hex}",
            "expected_revision": 0,
            "enabled": False,
        }
        changed = client.patch(url + "/personalization", json=setting)
        assert changed.status_code == 200
        expected = changed.json()

        runtime = client.app.state.runtime
        policy_before = runtime.policy.export_state()
        history_before = client.get(
            f"/dev/v1/sessions/{expected['session']['session_id']}/history"
        ).json()

    with TestClient(backend["application"]()) as client:
        assert client.get(url).json() == expected
        assert create(client, body) == expected
        assert client.patch(
            url + "/personalization", json=setting
        ).json() == expected
        assert client.app.state.runtime.policy.export_state() == policy_before

        history_after = client.get(
            f"/dev/v1/sessions/{expected['session']['session_id']}/history"
        ).json()
        assert history_after == history_before


def test_runtime_1_2_migration_preserves_learning_and_corrections(backend):
    with TestClient(backend["application"]()) as client:
        _, _, spec, url = prepare(client)

        accepted = client.post(
            url + "/feedback",
            json=feedback_body(spec, "need_more"),
        )
        assert accepted.status_code == 200, accepted.text

        correction = client.post(
            url + "/correction",
            json={
                "presentation_id": spec["presentation_id"],
                "configuration_id": spec["configuration"]["configuration_id"],
                "decision_id": spec["decision_id"],
                "reasons": ["prefer_overview"],
            },
        )
        assert correction.status_code == 200, correction.text

        old_policy = client.app.state.runtime.policy.export_state()
        old_inspector = client.get(url + "/inspector").json()
        old_correction = correction.json()

    row = backend["read_row"]()
    document = json.loads(row[2])
    document["format_version"] = "c4-runtime-state-1.2"
    document.pop("profiles")

    payload = canonical(document)
    CorrectionRuntimeState.model_validate_json(payload)
    old_manifest = manifest_for(
        PolicyConfig(),
        backend["kind"],
        corrections=True,
    )
    old_row = (row[0], old_manifest, payload, checksum(payload))
    backend["replace_row"](old_row)

    with pytest.raises(StateCompatibilityError):
        with TestClient(backend["application"]()):
            pass

    result = backend["migrate"](backend["backup"])
    assert result["migrated"] is True
    assert result["runtime_format"] == "c4-runtime-state-1.3"
    assert result["feature_dimension"] == 656
    assert result["posterior_fingerprint"] == old_policy.posterior_fingerprint
    assert result["posterior_revision"] == old_policy.posterior_revision

    backup = json.loads(backend["backup"].read_text(encoding="utf-8"))
    assert backup["payload"] == old_row[2]
    assert backup["manifest"] == old_row[1]

    migrated = json.loads(backend["read_row"]()[2])
    expected = dict(document)
    expected["format_version"] = "c4-runtime-state-1.3"
    expected["profiles"] = []
    assert migrated == expected

    with TestClient(backend["application"]()) as client:
        assert client.app.state.runtime.policy.export_state() == old_policy
        assert client.get(url + "/inspector").json() == old_inspector
        assert client.get(url + "/correction").json() == old_correction
        assert client.get("/dev/v1/demo-profiles").json() == []

    before_repeat = backend["read_row"]()
    assert backend["migrate"](backend["backup"])["migrated"] is False
    assert backend["read_row"]() == before_repeat


def test_recovery_rejects_profile_linked_to_missing_session():
    with TestClient(application()) as client:
        created = create(client, creation_body(client))
        runtime = client.app.state.runtime
        before = runtime.export_state()
        original = before.profiles[0]

        invalid = original.model_copy(
            update={"session_id": f"guest:{uuid4().hex}"}
        )
        invalid_state = before.model_copy(
            update={"profiles": (invalid,)}
        )

        with pytest.raises(StateStoreError, match="profile"):
            runtime._restore(invalid_state)

        assert runtime.export_state() == before
        assert created["profile"]["profile_id"] in runtime.profiles