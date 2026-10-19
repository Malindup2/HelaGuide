"""Feedback attribution, shared learning and atomic SQLite recovery."""

import json
import sqlite3

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.core.state_store import StateCompatibilityError, StateStoreError
from app.dev_main import create_app
from app.models.policy import PolicyConfig

from tests.test_dev_api import ack_body, select, start
from tests.test_explanations import FakeProvider


def application(path=None, *, mode="simulation"):
    return create_app(
        provider=FakeProvider(failure="offline_test"),
        database_path=path,
        policy_config=PolicyConfig(feedback_mode=mode),
    )


def presentation_url(session, spec):
    return (
        f"/dev/v1/sessions/{session['session_id']}"
        f"/presentations/{spec['exposure_id']}"
    )


def feedback_body(spec, rating="about_right"):
    return {
        "presentation_id": spec["presentation_id"],
        "configuration_id": spec["configuration"]["configuration_id"],
        "decision_id": spec["decision_id"],
        "rating": rating,
    }


def prepare(client, *, acknowledge=True):
    procedure_id, session = start(client)
    response = select(client, procedure_id, session)
    assert response.status_code == 201, response.text
    spec = response.json()["spec"]
    url = presentation_url(session, spec)
    if acknowledge:
        response = client.post(
            url + "/ack",
            json=ack_body(spec, ["action:request_token"]),
        )
        assert response.status_code == 200, response.text
    return procedure_id, session, spec, url


@pytest.mark.parametrize(
    ("rating", "reward"),
    [("about_right", 1), ("need_more", 0), ("too_much", 0)],
)
def test_valid_feedback_updates_shared_posterior(rating, reward):
    with TestClient(application()) as client:
        procedure_id, session, spec, url = prepare(client)
        before = client.get("/dev/v1/policy").json()

        response = client.post(url + "/feedback", json=feedback_body(spec, rating))
        assert response.status_code == 200, response.text
        receipt = response.json()["receipt"]

        assert receipt["reward"] == reward
        assert receipt["feedback"]["rating"] == rating
        assert receipt["feedback"]["origin"] == "simulation"
        assert receipt["procedure_synthetic"] is True
        assert receipt["decision_id"] == spec["decision_id"]
        assert receipt["selection_posterior_revision"] == 0
        assert receipt["resulting_posterior_revision"] == 1

        after = client.get("/dev/v1/policy").json()
        assert after["posterior_revision"] == 1
        assert after["posterior_fingerprint"] != before["posterior_fingerprint"]
        assert after["feature_dimension"] == 656

        current = client.get(
            f"/dev/v1/sessions/{session['session_id']}"
        ).json()
        following = select(client, procedure_id, current)
        assert following.status_code == 201, following.text
        next_spec = following.json()["spec"]
        inspector = client.get(
            presentation_url(session, next_spec) + "/inspector"
        ).json()
        assert inspector["decision"]["posterior_revision"] == 1
        assert inspector["decision"]["selection_mode"] == "thompson"
        # A different configuration is not guaranteed or required.


def test_feedback_requires_acknowledgment_and_valid_request():
    with TestClient(application()) as client:
        _, session, spec, url = prepare(client, acknowledge=False)
        before = client.get("/dev/v1/policy").json()

        assert client.post(
            url + "/feedback", json=feedback_body(spec)
        ).status_code == 409

        invalid = feedback_body(spec)
        invalid["origin"] = "participant_report"
        assert client.post(
            url + "/feedback", json=invalid
        ).status_code == 422

        invalid = feedback_body(spec)
        invalid.pop("rating")
        assert client.post(
            url + "/feedback", json=invalid
        ).status_code == 422

        assert client.get("/dev/v1/policy").json() == before


def test_repeated_feedback_is_idempotent_and_conflicts_are_rejected():
    with TestClient(application()) as client:
        _, session, spec, url = prepare(client)
        body = feedback_body(spec)
        first = client.post(url + "/feedback", json=body)
        second = client.post(url + "/feedback", json=body)
        assert first.status_code == 200
        assert second.json() == first.json()

        conflict = client.post(
            url + "/feedback",
            json=feedback_body(spec, "too_much"),
        )
        assert conflict.status_code == 409
        assert client.get("/dev/v1/policy").json()["posterior_revision"] == 1
        assert client.get(url + "/feedback").json() == first.json()


def test_late_feedback_preserves_original_context_and_vector():
    with TestClient(application()) as client:
        _, session, spec, url = prepare(client)
        original = client.get(url + "/inspector").json()
        current = client.get(
            f"/dev/v1/sessions/{session['session_id']}"
        ).json()

        changed = client.patch(
            f"/dev/v1/sessions/{session['session_id']}/context",
            json={
                "expected_revision": current["revision"],
                "update": {
                    "navigation_capability": 5,
                    "locks": {"presentation_mode": "GUIDED"},
                },
            },
        )
        assert changed.status_code == 200
        response = client.post(url + "/feedback", json=feedback_body(spec))
        assert response.status_code == 200, response.text

        retained = client.get(url + "/inspector").json()
        assert retained == original
        assert retained["decision"]["selected_features"] == (
            original["decision"]["selected_features"]
        )
        assert retained["offer"]["context_snapshot"]["settings"][
            "navigation_capability"
        ] is None
        assert response.json()["receipt"]["decision_id"] == spec["decision_id"]


def test_learning_is_shared_across_guest_sessions():
    with TestClient(application()) as client:
        procedure_id, first_session, spec, url = prepare(client)
        assert client.post(
            url + "/feedback", json=feedback_body(spec)
        ).status_code == 200

        second = client.post("/dev/v1/sessions").json()
        response = select(client, procedure_id, second)
        next_spec = response.json()["spec"]
        inspector = client.get(
            presentation_url(second, next_spec) + "/inspector"
        ).json()
        assert second["session_id"] != first_session["session_id"]
        assert inspector["decision"]["posterior_revision"] == 1
        assert inspector["decision"]["policy_run_id"] == client.get(
            "/dev/v1/policy"
        ).json()["policy_run_id"]

        # Another session cannot rate the original session's presentation.
        assert client.post(
            presentation_url(second, spec) + "/feedback",
            json=feedback_body(spec),
        ).status_code == 404


def test_restart_recovers_state_feedback_sampler_and_pending_offer(tmp_path):
    path = tmp_path / "state.sqlite3"

    with TestClient(application(path)) as client:
        procedure_id, session, spec, url = prepare(client)
        accepted = client.post(
            url + "/feedback", json=feedback_body(spec)
        ).json()

        pending_session = client.post("/dev/v1/sessions").json()
        pending_spec = select(
            client, procedure_id, pending_session
        ).json()["spec"]
        pending_url = presentation_url(pending_session, pending_spec)

        status = client.get("/dev/v1/policy").json()
        saved_session = client.get(
            f"/dev/v1/sessions/{session['session_id']}"
        ).json()
        original_inspector = client.get(url + "/inspector").json()
        state = client.app.state.runtime.policy.export_state()

        generator = np.random.Generator(np.random.PCG64())
        generator.bit_generator.state = json.loads(state.rng_state_json)
        expected_next_seed = int(generator.integers(0, 2**63 - 1))

    with TestClient(application(path)) as client:
        assert client.get("/dev/v1/policy").json() == status
        assert client.get(
            f"/dev/v1/sessions/{session['session_id']}"
        ).json() == saved_session
        assert client.get(url + "/inspector").json() == original_inspector
        assert client.get(url + "/feedback").json() == accepted

        duplicate = client.post(
            url + "/feedback", json=feedback_body(spec)
        )
        assert duplicate.json() == accepted
        assert client.get("/dev/v1/policy").json()["posterior_revision"] == 1

        assert client.get(pending_url).json()["spec"] == pending_spec
        assert client.post(
            pending_url + "/ack",
            json=ack_body(pending_spec, ["action:request_token"]),
        ).status_code == 200

        new_session = client.post("/dev/v1/sessions").json()
        new_spec = select(client, procedure_id, new_session).json()["spec"]
        decision = client.get(
            presentation_url(new_session, new_spec) + "/inspector"
        ).json()["decision"]
        assert decision["posterior_revision"] == 1
        assert decision["draw_seed"] == expected_next_seed

        pending_feedback = client.post(
            pending_url + "/feedback",
            json=feedback_body(pending_spec, "need_more"),
        )
        assert pending_feedback.status_code == 200
        assert pending_feedback.json()["receipt"][
            "resulting_posterior_revision"
        ] == 2


def test_modes_use_separate_state_and_cannot_relabel_existing_database(tmp_path):
    simulation_path = tmp_path / "simulation.sqlite3"
    participant_path = tmp_path / "participant.sqlite3"

    with TestClient(application(simulation_path)) as client:
        prepare(client)

    with pytest.raises(StateCompatibilityError, match="incompatible"):
        with TestClient(application(simulation_path, mode="participant")):
            pass

    with TestClient(application(participant_path, mode="participant")) as client:
        _, session, spec, url = prepare(client)
        response = client.post(url + "/feedback", json=feedback_body(spec))
        assert response.status_code == 200
        receipt = response.json()["receipt"]
        assert receipt["feedback"]["origin"] == "participant_report"
        assert receipt["procedure_synthetic"] is True


def test_changed_feature_manifest_is_rejected(tmp_path):
    path = tmp_path / "state.sqlite3"
    with TestClient(application(path)):
        pass

    with sqlite3.connect(path) as connection:
        manifest = json.loads(
            connection.execute(
                "SELECT manifest FROM c4_snapshot"
            ).fetchone()[0]
        )
        manifest["feature_dimension"] = 655
        connection.execute(
            "UPDATE c4_snapshot SET manifest=?",
            (json.dumps(manifest),),
        )

    with pytest.raises(StateCompatibilityError, match="incompatible"):
        with TestClient(application(path)):
            pass


def test_corrupt_snapshot_is_rejected(tmp_path):
    path = tmp_path / "state.sqlite3"
    with TestClient(application(path)):
        pass

    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE c4_snapshot SET payload='{}'"
        )

    with pytest.raises(StateStoreError, match="checksum"):
        with TestClient(application(path)):
            pass


def test_failed_commit_does_not_report_success_and_restart_recovers(tmp_path, monkeypatch):
    path = tmp_path / "state.sqlite3"

    with TestClient(application(path)) as client:
        _, session, spec, url = prepare(client)
        before = client.get("/dev/v1/policy").json()

        def fail_save(*args, **kwargs):
            raise StateStoreError("injected write failure")

        monkeypatch.setattr(
            client.app.state.runtime.store, "save", fail_save
        )
        response = client.post(url + "/feedback", json=feedback_body(spec))
        assert response.status_code == 503
        assert client.get("/dev/v1/policy").status_code == 503

    with TestClient(application(path)) as client:
        assert client.get("/dev/v1/policy").json() == before
        assert client.get(url + "/feedback").status_code == 404

        response = client.post(url + "/feedback", json=feedback_body(spec))
        assert response.status_code == 200
        assert response.json()["receipt"]["resulting_posterior_revision"] == 1


def test_second_process_cannot_overwrite_newer_state(tmp_path):
    path = tmp_path / "state.sqlite3"
    with TestClient(application(path)) as first:
        with TestClient(application(path)) as second:
            assert first.post("/dev/v1/sessions").status_code == 201
            assert second.post("/dev/v1/sessions").status_code == 503