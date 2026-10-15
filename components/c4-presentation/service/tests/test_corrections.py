"""Optional corrections, explicit preferences and state compatibility."""

import json

import pytest
from fastapi.testclient import TestClient

from app.core.navigation_migration import (
    canonical,
    checksum,
    manifest_for,
)
from app.core.state_store import (
    StateCompatibilityError,
    StateStoreError,
)
from app.models.policy import PolicyConfig
from app.models.runtime_state_v1_1 import (
    RuntimeState as NavigationRuntimeState,
)
from tests.test_dev_api import ack_body
from tests.test_feedback_persistence import (
    application,
    feedback_body,
    prepare,
)
from tests.test_navigation import backend


def correction_body(spec, *reasons):
    return {
        "presentation_id": spec["presentation_id"],
        "configuration_id": spec["configuration"]["configuration_id"],
        "decision_id": spec["decision_id"],
        "reasons": list(reasons),
    }


def accept_negative_feedback(client, spec, url):
    response = client.post(
        url + "/feedback",
        json=feedback_body(spec, "need_more"),
    )
    assert response.status_code == 200, response.text
    return response.json()


def session_url(session):
    return f"/dev/v1/sessions/{session['session_id']}"


def test_correction_and_application_recover_without_extra_learning(backend):
    with TestClient(backend["application"]()) as client:
        procedure_id, session, spec, url = prepare(client)
        base = session_url(session)
        original_inspector = client.get(url + "/inspector").json()
        accepted = accept_negative_feedback(client, spec, url)
        policy_after_feedback = client.get("/dev/v1/policy").json()
        context_before = client.get(base).json()

        body = correction_body(
            spec,
            "prefer_guided",
            "show_prerequisite_cues",
        )
        recorded = client.post(url + "/correction", json=body)
        assert recorded.status_code == 200, recorded.text
        record = recorded.json()

        assert record["application"] is None
        assert record["rating"] == "need_more"
        assert record["origin"] == "simulation"
        assert record["decision_id"] == spec["decision_id"]
        assert record["acknowledgment_event_id"] == (
            accepted["receipt"]["acknowledgment_event_id"]
        )
        assert client.get(base).json() == context_before
        assert client.get("/dev/v1/policy").json() == policy_after_feedback

        reversed_body = dict(body, reasons=list(reversed(body["reasons"])))
        repeated = client.post(url + "/correction", json=reversed_body)
        assert repeated.status_code == 200
        assert repeated.json() == record

        apply_body = {"expected_revision": context_before["revision"]}
        applied = client.post(
            url + "/correction/apply",
            json=apply_body,
        )
        assert applied.status_code == 200, applied.text
        applied_record = applied.json()

        context_after = client.get(base).json()
        assert context_after["settings"]["preferences"]["presentation_mode"] == (
            "GUIDED"
        )
        assert context_after["settings"]["preferences"]["prerequisite_cue"] is True
        assert context_after["settings"]["locks"] == (
            context_before["settings"]["locks"]
        )
        assert context_after["settings"]["accessibility"] == (
            context_before["settings"]["accessibility"]
        )
        assert context_after["revision"] == context_before["revision"] + 1
        assert applied_record["application"]["preference_event_id"]

        assert client.get("/dev/v1/policy").json() == policy_after_feedback
        assert client.get(url + "/inspector").json() == original_inspector
        assert client.get(url).json()["spec"] == spec

        assert client.post(
            url + "/correction/apply",
            json=apply_body,
        ).json() == applied_record
        assert client.get(base).json() == context_after

    with TestClient(backend["application"]()) as client:
        assert client.get(url + "/correction").json() == applied_record
        assert client.get(base).json() == context_after
        assert client.get("/dev/v1/policy").json() == policy_after_feedback
        assert client.get(url + "/inspector").json() == original_inspector

        assert client.post(
            url + "/correction/apply",
            json=apply_body,
        ).json() == applied_record

        following = client.post(
            base + "/presentations",
            json={
                "procedure_id": procedure_id,
                "expected_revision": context_after["revision"],
            },
        )
        assert following.status_code == 201, following.text
        next_spec = following.json()["spec"]
        inspector = client.get(
            base + f"/presentations/{next_spec['exposure_id']}/inspector"
        ).json()

        assert inspector["decision"]["posterior_revision"] == (
            policy_after_feedback["posterior_revision"]
        )
        assert inspector["decision"]["feature_dimension"] == 656
        assert inspector["decision"]["evaluation"]["snapshot"]["settings"][
            "preferences"
        ]["presentation_mode"] == "GUIDED"

        # Soft preferences do not guarantee a different selected configuration.


def test_correction_requires_negative_acknowledged_feedback_and_identity():
    with TestClient(application()) as client:
        _, session, spec, url = prepare(client, acknowledge=False)
        body = correction_body(spec, "prefer_guided")

        assert client.post(
            url + "/correction", json=body
        ).status_code == 409

        assert client.post(
            url + "/feedback",
            json=feedback_body(spec, "need_more"),
        ).status_code == 409

        assert client.post(
            url + "/ack",
            json=ack_body(spec, ["action:request_token"]),
        ).status_code == 200

        assert client.post(
            url + "/correction", json=body
        ).status_code == 409

        accept_negative_feedback(client, spec, url)

        wrong_identity = dict(body, decision_id="wrong-decision")
        assert client.post(
            url + "/correction", json=wrong_identity
        ).status_code == 409

        invalid = correction_body(
            spec,
            "prefer_guided",
            "prefer_overview",
        )
        assert client.post(
            url + "/correction", json=invalid
        ).status_code == 422

        assert client.post(
            url + "/correction", json=body
        ).status_code == 200
        assert client.post(
            url + "/correction",
            json=correction_body(spec, "prefer_overview"),
        ).status_code == 409

        other = client.post("/dev/v1/sessions").json()
        other_url = (
            session_url(other)
            + f"/presentations/{spec['exposure_id']}/correction"
        )
        assert client.get(other_url).status_code == 404
        assert client.post(other_url, json=body).status_code == 404

        _, _, second_spec, second_url = prepare(client)
        response = client.post(
            second_url + "/feedback",
            json=feedback_body(second_spec, "about_right"),
        )
        assert response.status_code == 200
        assert client.post(
            second_url + "/correction",
            json=correction_body(second_spec, "prefer_guided"),
        ).status_code == 409


def test_unavailable_aid_remains_diagnostic_and_cannot_be_applied():
    with TestClient(application()) as client:
        _, session, spec, url = prepare(client)
        base = session_url(session)
        accept_negative_feedback(client, spec, url)
        before = client.get(base).json()
        policy = client.get("/dev/v1/policy").json()

        options = client.get(url + "/correction-options")
        assert options.status_code == 200
        parallel = next(
            item
            for item in options.json()["choices"]
            if item["code"] == "show_parallel_map"
        )
        assert not parallel["available_for_future"]
        assert parallel["unavailable_reason"]

        recorded = client.post(
            url + "/correction",
            json=correction_body(spec, "show_parallel_map"),
        )
        assert recorded.status_code == 200

        rejected = client.post(
            url + "/correction/apply",
            json={"expected_revision": before["revision"]},
        )
        assert rejected.status_code == 409
        assert rejected.json()["detail"]["code"] == (
            "correction_not_currently_feasible"
        )
        assert client.get(base).json() == before
        assert client.get("/dev/v1/policy").json() == policy
        assert client.get(url + "/correction").json()["application"] is None


def test_application_preserves_locks_and_retries_do_not_reapply():
    with TestClient(application()) as client:
        _, session, spec, url = prepare(client)
        base = session_url(session)
        accept_negative_feedback(client, spec, url)
        assert client.post(
            url + "/correction",
            json=correction_body(spec, "prefer_guided"),
        ).status_code == 200

        original_revision = client.get(base).json()["revision"]
        locked = client.patch(
            base + "/context",
            json={
                "expected_revision": original_revision,
                "update": {"locks": {"presentation_mode": "OVERVIEW"}},
            },
        )
        assert locked.status_code == 200

        assert client.post(
            url + "/correction/apply",
            json={"expected_revision": original_revision},
        ).status_code == 409
        assert client.post(
            url + "/correction/apply",
            json={"expected_revision": locked.json()["revision"]},
        ).status_code == 409
        assert client.get(base).json() == locked.json()

        unlocked = client.patch(
            base + "/context",
            json={
                "expected_revision": locked.json()["revision"],
                "update": {"locks": {"presentation_mode": None}},
            },
        )
        assert unlocked.status_code == 200

        apply_body = {"expected_revision": unlocked.json()["revision"]}
        applied = client.post(url + "/correction/apply", json=apply_body)
        assert applied.status_code == 200, applied.text

        current = client.get(base).json()
        later = client.patch(
            base + "/context",
            json={
                "expected_revision": current["revision"],
                "update": {"preferences": {"presentation_mode": "OVERVIEW"}},
            },
        )
        assert later.status_code == 200

        repeated = client.post(url + "/correction/apply", json=apply_body)
        assert repeated.status_code == 200
        assert repeated.json() == applied.json()
        assert client.get(base).json() == later.json()


def test_failed_preference_application_rolls_back(monkeypatch):
    with TestClient(application()) as client:
        _, session, spec, url = prepare(client)
        accept_negative_feedback(client, spec, url)
        assert client.post(
            url + "/correction",
            json=correction_body(spec, "prefer_guided"),
        ).status_code == 200

        runtime = client.app.state.runtime
        before = runtime.export_state()
        revision = client.get(session_url(session)).json()["revision"]
        original_update = runtime.contexts.update_context

        def fail_after_update(*args, **kwargs):
            original_update(*args, **kwargs)
            raise RuntimeError("injected failure after context update")

        monkeypatch.setattr(
            runtime.contexts,
            "update_context",
            fail_after_update,
        )

        with pytest.raises(RuntimeError, match="injected failure"):
            client.post(
                url + "/correction/apply",
                json={"expected_revision": revision},
            )

        assert runtime.export_state() == before


def test_runtime_1_1_migration_preserves_policy_and_history(backend):
    with TestClient(backend["application"]()) as client:
        _, session, spec, url = prepare(client)
        accept_negative_feedback(client, spec, url)
        old_policy = client.app.state.runtime.policy.export_state()
        old_inspector = client.get(url + "/inspector").json()

    row = backend["read_row"]()
    document = json.loads(row[2])
    document["format_version"] = "c4-runtime-state-1.1"
    document.pop("corrections")
    payload = canonical(document)
    NavigationRuntimeState.model_validate_json(payload)

    old_manifest = manifest_for(
        PolicyConfig(),
        backend["kind"],
        navigation=True,
    )
    old_row = (
        row[0],
        old_manifest,
        payload,
        checksum(payload),
    )
    backend["replace_row"](old_row)

    with pytest.raises(StateCompatibilityError):
        with TestClient(backend["application"]()):
            pass

    result = backend["migrate"](backend["backup"])
    assert result["migrated"] is True
    assert result["runtime_format"] == "c4-runtime-state-1.2"
    assert result["feature_dimension"] == 656

    backup = json.loads(backend["backup"].read_text(encoding="utf-8"))
    assert backup["payload"] == old_row[2]
    assert backup["manifest"] == old_row[1]

    migrated_document = json.loads(backend["read_row"]()[2])
    expected = dict(document)
    expected["format_version"] = "c4-runtime-state-1.2"
    expected["corrections"] = []
    assert migrated_document == expected

    with TestClient(backend["application"]()) as client:
        assert client.app.state.runtime.policy.export_state() == old_policy
        assert client.get(url + "/inspector").json() == old_inspector

    before_repeat = backend["read_row"]()
    assert backend["migrate"](backend["backup"])["migrated"] is False
    assert backend["read_row"]() == before_repeat


def test_recovery_rejects_corrupted_correction_attribution():
    with TestClient(application()) as client:
        _, _, spec, url = prepare(client)
        accept_negative_feedback(client, spec, url)
        assert client.post(
            url + "/correction",
            json=correction_body(spec, "prefer_guided"),
        ).status_code == 200

        runtime = client.app.state.runtime
        before = runtime.export_state()
        invalid_record = before.corrections[0].model_copy(
            update={"decision_id": "wrong-decision"}
        )
        invalid_state = before.model_copy(
            update={"corrections": (invalid_record,)}
        )

        with pytest.raises(StateStoreError, match="correction attribution"):
            runtime._restore(invalid_state)

        assert runtime.export_state() == before