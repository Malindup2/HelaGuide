"""Read-only Inspector API tests using the existing offline provider."""

from fastapi.testclient import TestClient

from app.dev_main import create_app
from tests.test_explanations import FakeProvider


def make_application(database_path=None):
    return create_app(
        provider=FakeProvider(failure="offline_test"),
        database_path=database_path,
    )


def create_session(client):
    response = client.post("/dev/v1/sessions")
    assert response.status_code == 201, response.text
    return response.json()


def test_graph_endpoint_returns_registered_graph_without_changing_state():
    with TestClient(make_application()) as client:
        procedures = client.get("/dev/v1/procedures")
        assert procedures.status_code == 200

        procedure_id = procedures.json()[0]["procedure_id"]
        runtime = client.app.state.runtime
        before = runtime.export_state().model_dump_json()

        response = client.get(
            f"/dev/v1/procedures/{procedure_id}/graph"
        )
        assert response.status_code == 200, response.text

        graph, _, _ = runtime.procedure(procedure_id)
        assert response.json() == graph.model_dump(mode="json")
        assert runtime.export_state().model_dump_json() == before

        missing = client.get("/dev/v1/procedures/not-registered/graph")
        assert missing.status_code == 404
        assert runtime.export_state().model_dump_json() == before


def test_history_returns_ordered_events_and_preserves_session_isolation():
    with TestClient(make_application()) as client:
        first = create_session(client)
        second = create_session(client)
        first_base = f"/dev/v1/sessions/{first['session_id']}"
        second_base = f"/dev/v1/sessions/{second['session_id']}"

        response = client.patch(
            first_base + "/context",
            json={
                "expected_revision": first["revision"],
                "update": {"navigation_capability": 3},
            },
        )
        assert response.status_code == 200, response.text
        updated = response.json()

        procedures = client.get("/dev/v1/procedures").json()
        procedure_id = procedures[0]["procedure_id"]

        response = client.post(
            first_base + "/presentations",
            json={
                "procedure_id": procedure_id,
                "expected_revision": updated["revision"],
            },
        )
        assert response.status_code == 201, response.text
        spec = response.json()["spec"]

        history = client.get(first_base + "/history")
        assert history.status_code == 200, history.text
        assert [
            event["kind"] for event in history.json()["events"]
        ] == ["preference_change"]

        acknowledgment = client.post(
            first_base
            + f"/presentations/{spec['exposure_id']}/ack",
            json={
                "presentation_id": spec["presentation_id"],
                "configuration_id": spec["configuration"][
                    "configuration_id"
                ],
                "displayed_action_ids": [
                    spec["acknowledgment_action_ids"][0]
                ],
            },
        )
        assert acknowledgment.status_code == 200, acknowledgment.text

        runtime = client.app.state.runtime
        before = runtime.export_state().model_dump_json()

        history = client.get(first_base + "/history")
        assert history.status_code == 200, history.text
        document = history.json()

        assert document["schema_version"] == "c4-session-history-1.0"
        assert document["session"]["session_id"] == first["session_id"]
        assert document["session"]["revision"] == 2
        assert [
            event["kind"] for event in document["events"]
        ] == ["preference_change", "presentation_exposure"]
        assert [
            event["sequence"] for event in document["events"]
        ] == [1, 2]
        assert document["events"][1] == acknowledgment.json()

        other_history = client.get(second_base + "/history")
        assert other_history.status_code == 200
        assert other_history.json()["session"]["session_id"] == (
            second["session_id"]
        )
        assert other_history.json()["events"] == []

        assert runtime.export_state().model_dump_json() == before
        assert runtime.policy.posterior_revision == 0


def test_unknown_session_history_returns_404_without_creating_a_session():
    with TestClient(make_application()) as client:
        runtime = client.app.state.runtime
        before = runtime.export_state().model_dump_json()

        response = client.get(
            "/dev/v1/sessions/guest:not-registered/history"
        )
        assert response.status_code == 404
        assert runtime.export_state().model_dump_json() == before


def test_history_survives_sqlite_restart_and_reads_do_not_save(tmp_path):
    database_path = tmp_path / "inspector-state.sqlite3"

    with TestClient(make_application(database_path)) as client:
        session = create_session(client)
        base = f"/dev/v1/sessions/{session['session_id']}"

        response = client.patch(
            base + "/context",
            json={
                "expected_revision": session["revision"],
                "update": {
                    "preferences": {"presentation_mode": "GUIDED"}
                },
            },
        )
        assert response.status_code == 200, response.text

        runtime = client.app.state.runtime
        saved_before = runtime.store.load()
        state_before = runtime.export_state().model_dump_json()
        policy_before = client.get("/dev/v1/policy").json()

        response = client.get(base + "/history")
        assert response.status_code == 200, response.text
        expected_history = response.json()

        assert runtime.store.load() == saved_before
        assert runtime.export_state().model_dump_json() == state_before

    with TestClient(make_application(database_path)) as client:
        runtime = client.app.state.runtime
        saved_before = runtime.store.load()

        response = client.get(base + "/history")
        assert response.status_code == 200, response.text
        assert response.json() == expected_history
        assert client.get("/dev/v1/policy").json() == policy_before
        assert runtime.store.load() == saved_before