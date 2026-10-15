"""Stable navigation and explicit runtime migration.

PostgreSQL cases use only c4_pp1_test and clear its C4 snapshot rows.
All explanation requests use the existing offline FakeProvider.
"""

import json
import os
import sqlite3
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.navigation_migration import (
    canonical,
    checksum,
    manifest_for,
    migrate_postgres,
    migrate_sqlite,
)
from app.core.state_store import StateCompatibilityError
from app.dev_main import create_app
from app.models.policy import PolicyConfig
from app.models.runtime_state_v1 import RuntimeState as LegacyRuntimeState
from tests.test_explanations import FakeProvider
from tests.test_feedback_persistence import feedback_body


@pytest.fixture(params=("sqlite", "postgresql"))
def backend(request, tmp_path):
    kind = request.param
    path = tmp_path / "navigation.sqlite3"
    dsn = None

    if kind == "postgresql":
        dsn = os.getenv("C4_TEST_POSTGRES_DSN")
        if not dsn:
            pytest.skip("C4_TEST_POSTGRES_DSN is not configured")

        import psycopg
        from psycopg.conninfo import conninfo_to_dict

        if conninfo_to_dict(dsn).get("dbname") != "c4_pp1_test":
            pytest.fail("navigation tests require c4_pp1_test")

        def clear():
            with psycopg.connect(dsn, autocommit=True) as connection:
                exists = connection.execute(
                    "SELECT to_regclass('c4.research_runtime_state')"
                ).fetchone()[0]
                if exists is not None:
                    connection.execute(
                        "DELETE FROM c4.research_runtime_state "
                        "WHERE state_key IN ('simulation', 'participant')"
                    )

        clear()

    def application():
        return create_app(
            provider=FakeProvider(failure="offline_test"),
            database_path=path if kind == "sqlite" else None,
            postgres_dsn=dsn,
        )

    def read_row():
        if kind == "sqlite":
            with sqlite3.connect(path) as connection:
                return connection.execute(
                    "SELECT revision, manifest, payload, checksum "
                    "FROM c4_snapshot WHERE singleton=1"
                ).fetchone()

        with psycopg.connect(dsn, autocommit=True) as connection:
            return connection.execute(
                "SELECT revision, manifest, payload, checksum "
                "FROM c4.research_runtime_state "
                "WHERE state_key='simulation'"
            ).fetchone()

    def replace_row(row):
        if kind == "sqlite":
            with sqlite3.connect(path) as connection:
                connection.execute(
                    "UPDATE c4_snapshot "
                    "SET revision=?, manifest=?, payload=?, checksum=? "
                    "WHERE singleton=1",
                    row,
                )
        else:
            with psycopg.connect(dsn, autocommit=True) as connection:
                connection.execute(
                    "UPDATE c4.research_runtime_state "
                    "SET revision=%s, manifest=%s, payload=%s, checksum=%s "
                    "WHERE state_key='simulation'",
                    row,
                )

    def migrate(backup):
        if kind == "sqlite":
            return migrate_sqlite(path, backup)
        return migrate_postgres(dsn, backup)

    yield {
        "kind": kind,
        "application": application,
        "read_row": read_row,
        "replace_row": replace_row,
        "migrate": migrate,
        "backup": tmp_path / "before-navigation.json",
    }

    if kind == "postgresql":
        clear()


def prepare(client, *, acknowledge=True):
    procedure_id = client.get("/dev/v1/procedures").json()[0][
        "procedure_id"
    ]
    session = client.post("/dev/v1/sessions").json()
    base = f"/dev/v1/sessions/{session['session_id']}"

    updated = client.patch(
        base + "/context",
        json={
            "expected_revision": session["revision"],
            "update": {"locks": {"presentation_mode": "GUIDED"}},
        },
    )
    assert updated.status_code == 200, updated.text

    response = client.post(
        base + "/presentations",
        json={
            "procedure_id": procedure_id,
            "expected_revision": updated.json()["revision"],
        },
    )
    assert response.status_code == 201, response.text
    spec = response.json()["spec"]
    url = base + f"/presentations/{spec['exposure_id']}"

    if acknowledge:
        response = client.post(
            url + "/ack",
            json={
                "presentation_id": spec["presentation_id"],
                "configuration_id": spec["configuration"][
                    "configuration_id"
                ],
                "displayed_action_ids": [spec["initial_action_id"]],
            },
        )
        assert response.status_code == 200, response.text

    return procedure_id, base, spec, url


def display_body(client, base, spec, action_id):
    return {
        "event_id": f"event:{uuid4().hex}",
        "expected_revision": client.get(base).json()["revision"],
        "presentation_id": spec["presentation_id"],
        "configuration_id": spec["configuration"]["configuration_id"],
        "action_id": action_id,
    }


def test_navigation_is_stable_retry_safe_and_updates_actual_recap(backend):
    with TestClient(backend["application"]()) as client:
        procedure_id, base, spec, url = prepare(client)
        original_offer = client.get(url + "/inspector").json()
        original_policy = (
            client.app.state.runtime.policy.export_state().model_dump_json()
        )

        initial = client.get(url + "/navigation").json()
        assert initial["current_action_id"] == "action:request_token"

        body = display_body(client, base, spec, "action:collect_pack")
        first = client.post(url + "/navigation", json=body)
        assert first.status_code == 200, first.text
        assert first.json()["is_revisit"] is False

        repeated = client.post(url + "/navigation", json=body)
        assert repeated.status_code == 200
        assert repeated.json() == first.json()

        conflicting = dict(body, action_id="action:request_token")
        assert client.post(
            url + "/navigation", json=conflicting
        ).status_code == 409

        back = display_body(client, base, spec, "action:request_token")
        revisited = client.post(url + "/navigation", json=back)
        assert revisited.status_code == 200, revisited.text
        assert revisited.json()["is_revisit"] is True

        navigation = client.get(url + "/navigation").json()
        assert navigation["current_action_id"] == "action:request_token"
        assert len(navigation["events"]) == 2

        evaluation = client.get(
            base + f"/feasibility/{procedure_id}"
        ).json()
        assert evaluation["snapshot"]["matching_exposure_count"] == 1
        assert evaluation["snapshot"]["recap_action_ids"] == [
            "action:collect_pack",
            "action:request_token",
        ]
        assert client.get(url).json()["spec"] == spec
        assert client.get(url + "/inspector").json() == original_offer
        assert (
            client.app.state.runtime.policy.export_state().model_dump_json()
            == original_policy
        )


def test_navigation_requires_acknowledgment_and_correct_identity(backend):
    with TestClient(backend["application"]()) as client:
        _, base, spec, url = prepare(client, acknowledge=False)
        body = display_body(client, base, spec, "action:collect_pack")
        assert client.post(
            url + "/navigation", json=body
        ).status_code == 409

        response = client.post(
            url + "/ack",
            json={
                "presentation_id": spec["presentation_id"],
                "configuration_id": spec["configuration"]["configuration_id"],
                "displayed_action_ids": [spec["initial_action_id"]],
            },
        )
        assert response.status_code == 200
        body = display_body(client, base, spec, "action:collect_pack")

        assert client.post(
            url + "/navigation",
            json=dict(body, action_id="action:not_in_this_procedure"),
        ).status_code == 422

        assert client.post(
            url + "/navigation",
            json=dict(body, presentation_id="another-presentation"),
        ).status_code == 409

        assert client.post(
            url + "/navigation",
            json=dict(body, configuration_id="another-configuration"),
        ).status_code == 409

        other = client.post("/dev/v1/sessions").json()
        other_url = (
            f"/dev/v1/sessions/{other['session_id']}"
            f"/presentations/{spec['exposure_id']}/navigation"
        )
        assert client.post(other_url, json=body).status_code == 404
        assert client.get(url + "/navigation").json()["events"] == []


def test_hard_settings_require_new_presentation_but_retry_is_preserved(backend):
    with TestClient(backend["application"]()) as client:
        _, base, spec, url = prepare(client)
        body = display_body(client, base, spec, "action:collect_pack")
        first = client.post(url + "/navigation", json=body)
        assert first.status_code == 200

        session = client.get(base).json()
        updated = client.patch(
            base + "/context",
            json={
                "expected_revision": session["revision"],
                "update": {"locks": {"presentation_mode": "OVERVIEW"}},
            },
        )
        assert updated.status_code == 200

        assert client.post(
            url + "/navigation", json=body
        ).json() == first.json()

        new_body = display_body(
            client, base, spec, "action:request_token"
        )
        rejected = client.post(url + "/navigation", json=new_body)
        assert rejected.status_code == 409
        assert len(client.get(url + "/navigation").json()["events"]) == 1


def test_feedback_after_navigation_uses_original_decision_and_recovers(backend):
    with TestClient(backend["application"]()) as client:
        procedure_id, base, spec, url = prepare(client)
        original = client.get(url + "/inspector").json()

        body = display_body(client, base, spec, "action:collect_pack")
        event = client.post(url + "/navigation", json=body)
        assert event.status_code == 200

        session = client.get(base).json()
        response = client.patch(
            base + "/context",
            json={
                "expected_revision": session["revision"],
                "update": {"preferences": {"prerequisite_cue": True}},
            },
        )
        assert response.status_code == 200

        accepted = client.post(
            url + "/feedback", json=feedback_body(spec)
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["receipt"]["decision_id"] == spec["decision_id"]
        assert accepted.json()["receipt"]["resulting_posterior_revision"] == 1
        assert client.get(url + "/inspector").json() == original

        duplicate = client.post(
            url + "/feedback", json=feedback_body(spec)
        )
        assert duplicate.json() == accepted.json()

        navigation = client.get(url + "/navigation").json()
        status = client.get("/dev/v1/policy").json()
        sampler = client.app.state.runtime.policy.export_state().rng_state_json

    with TestClient(backend["application"]()) as client:
        assert client.get(url + "/navigation").json() == navigation
        assert client.get(url + "/inspector").json() == original
        assert client.get(url + "/feedback").json() == accepted.json()
        assert client.get("/dev/v1/policy").json() == status
        assert (
            client.app.state.runtime.policy.export_state().rng_state_json
            == sampler
        )
        assert client.post(
            url + "/navigation", json=body
        ).json() == event.json()

        session = client.get(base).json()
        next_response = client.post(
            base + "/presentations",
            json={
                "procedure_id": procedure_id,
                "expected_revision": session["revision"],
            },
        )
        assert next_response.status_code == 201
        next_spec = next_response.json()["spec"]
        inspector = client.get(
            base
            + f"/presentations/{next_spec['exposure_id']}/inspector"
        ).json()
        assert inspector["decision"]["posterior_revision"] == 1


def install_legacy_snapshot(backend):
    with TestClient(backend["application"]()) as client:
        _, base, spec, url = prepare(client)
        accepted = client.post(
            url + "/feedback", json=feedback_body(spec)
        )
        assert accepted.status_code == 200
        old_policy = client.app.state.runtime.policy.export_state()
        old_inspector = client.get(url + "/inspector").json()

    row = backend["read_row"]()
    document = json.loads(row[2])
    document["format_version"] = "c4-runtime-state-1.0"
    payload = canonical(document)
    LegacyRuntimeState.model_validate_json(payload)

    manifest = manifest_for(
        PolicyConfig(), backend["kind"], legacy=True
    )
    legacy_row = (row[0], manifest, payload, checksum(payload))
    backend["replace_row"](legacy_row)
    return legacy_row, old_policy, old_inspector, url


def test_migration_preserves_learned_state_and_keeps_original_backup(backend):
    legacy_row, old_policy, old_inspector, url = install_legacy_snapshot(
        backend
    )

    with pytest.raises(StateCompatibilityError):
        with TestClient(backend["application"]()):
            pass

    result = backend["migrate"](backend["backup"])
    assert result["migrated"] is True
    assert result["feature_dimension"] == 656
    assert result["posterior_fingerprint"] == old_policy.posterior_fingerprint
    assert result["posterior_revision"] == old_policy.posterior_revision

    backup = json.loads(backend["backup"].read_text(encoding="utf-8"))
    assert backup["payload"] == legacy_row[2]
    assert backup["manifest"] == legacy_row[1]
    assert backup["checksum"] == legacy_row[3]

    migrated_row = backend["read_row"]()
    assert migrated_row[0] == legacy_row[0] + 1
    old_document = json.loads(legacy_row[2])
    new_document = json.loads(migrated_row[2])
    old_document["format_version"] = "c4-runtime-state-1.1"
    assert new_document == old_document

    with TestClient(backend["application"]()) as client:
        assert client.app.state.runtime.policy.export_state() == old_policy
        assert client.get(url + "/inspector").json() == old_inspector

    before_repeat = backend["read_row"]()
    repeated = backend["migrate"](backend["backup"])
    assert repeated["migrated"] is False
    assert backend["read_row"]() == before_repeat


def test_migration_rejects_changed_feature_manifest_without_writing(backend):
    row, _, _, _ = install_legacy_snapshot(backend)
    manifest = json.loads(row[1])
    manifest["feature_dimension"] = 655
    invalid_row = (row[0], canonical(manifest), row[2], row[3])
    backend["replace_row"](invalid_row)

    with pytest.raises(StateCompatibilityError):
        backend["migrate"](backend["backup"])

    assert backend["read_row"]() == invalid_row
    assert not backend["backup"].exists()


def test_migration_never_overwrites_an_existing_backup(backend):
    row, _, _, _ = install_legacy_snapshot(backend)
    backend["backup"].write_text("existing backup", encoding="utf-8")

    with pytest.raises(FileExistsError):
        backend["migrate"](backend["backup"])

    assert backend["read_row"]() == row
    assert backend["backup"].read_text(encoding="utf-8") == "existing backup"