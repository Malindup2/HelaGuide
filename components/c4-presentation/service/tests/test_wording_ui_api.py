"""UI envelope and recovery tests. No real provider or database credentials."""

import json

import pytest
from fastapi.testclient import TestClient

from app.core.demo_procedures import load_demo_procedures
from app.core.explanation_store import ArtifactStoreError
from app.core.prepared_wording import prepare_wording_packet
from app.core.wording_service import PreparedWordingStore, make_human_artifact
from app.dev_main import create_app
from tests.test_explanations import FakeProvider
from tests.test_feedback_persistence import feedback_body
from tests.test_guidance_routing import (
    anonymous, profile, request_guidance, presentation_url, display_body,
)
from tests.test_prepared_wording import filled_draft


def seed(directory, *, reviewed=True, heading="Request the demo token", style="plain"):
    graph = load_demo_procedures()[0][0]
    packet = prepare_wording_packet(graph, writing_style=style)
    draft = filled_draft(packet)
    draft = draft.model_copy(update={"items": tuple(
        item.model_copy(update={"text": heading})
        if item.slot_id == "action_heading/action/action:request_token" else item
        for item in draft.items
    )})
    artifact = make_human_artifact(packet, draft, author_reference="test-author")
    store = PreparedWordingStore(directory)
    store.save(artifact)
    if reviewed:
        store.review(artifact.request_key, reviewer_reference="test-review")
    return artifact


def backend(tmp_path, *, enabled=True, provider=None):
    return create_app(
        provider=provider or FakeProvider(failure="offline_test"),
        database_path=tmp_path / "state.sqlite3",
        prepared_wording_directory=tmp_path / "prepared" if enabled else None,
        wording_views_directory=tmp_path / "views" if enabled else None,
        allow_legacy_adaptive_sessions=False,
    )


def title(wording):
    return next(item["text"] for item in wording["items"]
                if item["slot_id"] == "action_heading/action/action:request_token")


def test_guest_wording_is_offline_and_never_creates_a_policy_offer(tmp_path):
    seed(tmp_path / "prepared")
    application = backend(tmp_path)
    with TestClient(application) as client:
        session = anonymous(client)
        before = application.state.runtime.policy.export_state()
        response = request_guidance(client, session)
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["mode"] == "standard"
        assert title(result["wording"]) == "Request the demo token"
        assert result["wording"]["artifact_digest"]
        assert result["guidance"]["learning_eligible"] is False
        assert application.state.runtime.policy.export_state() == before
        assert not list((tmp_path / "views").glob("*.json"))


def test_prepared_wording_is_bound_to_original_exposure_and_survives_restart(tmp_path):
    artifact = seed(tmp_path / "prepared")
    application = backend(tmp_path)
    with TestClient(application) as client:
        owner = profile(client, lock_guided=True)
        session = owner["session"]
        response = request_guidance(client, session)
        assert response.status_code == 200, response.text
        original = response.json()
        assert title(original["wording"]) == "Request the demo token"
        url = presentation_url(session, original["spec"])
        assert client.post(url + "/ack", json=display_body(original["spec"])).status_code == 200
        policy_before = application.state.runtime.policy.export_state()
        assert client.get(url).json()["wording"] == original["wording"]
        assert application.state.runtime.policy.export_state() == policy_before
    # Replace the current registry asset; historical view must stay unchanged.
    (tmp_path / "prepared" / f"{artifact.request_key}.json").unlink()
    seed(tmp_path / "prepared", heading="A revised demo heading")
    restarted = backend(tmp_path)
    with TestClient(restarted) as client:
        restored = client.get(url)
        assert restored.status_code == 200, restored.text
        saved = restored.json()
        assert saved["spec"] == original["spec"]
        assert saved["wording"] == original["wording"]
        fresh = request_guidance(client, session).json()
        assert title(fresh["wording"]) == "A revised demo heading"
        assert fresh["spec"]["exposure_id"] != original["spec"]["exposure_id"]
        body = feedback_body(original["spec"])
        first = client.post(url + "/feedback", json=body)
        assert first.status_code == 200, first.text
        duplicate = client.post(url + "/feedback", json=body)
        assert duplicate.json() == first.json()
        assert restarted.state.runtime.policy.posterior_revision == 1


def test_old_database_and_old_presentation_are_not_rewritten(tmp_path):
    with TestClient(backend(tmp_path, enabled=False)) as client:
        owner = profile(client, lock_guided=True)
        session = owner["session"]
        old = request_guidance(client, session).json()
        url = presentation_url(session, old["spec"])
    seed(tmp_path / "prepared")
    with TestClient(backend(tmp_path)) as client:
        restored = client.get(url)
        assert restored.status_code == 200, restored.text
        assert restored.json()["spec"] == old["spec"]
        assert restored.json()["wording"] is None
        fresh = request_guidance(client, session).json()
        assert fresh["wording"]["artifact_digest"]


def test_pending_review_is_frozen_as_fallback_until_a_new_request(tmp_path):
    artifact = seed(tmp_path / "prepared", reviewed=False)
    with TestClient(backend(tmp_path)) as client:
        owner = profile(client, lock_guided=True)
        session = owner["session"]
        old = request_guidance(client, session).json()
        assert old["wording"]["artifact_digest"] is None
        assert "wording_human_review_required" in old["wording"]["diagnostics"]
        PreparedWordingStore(tmp_path / "prepared").review(artifact.request_key, reviewer_reference="test-review")
        assert client.get(presentation_url(session, old["spec"])).json()["wording"] == old["wording"]
        assert request_guidance(client, session).json()["wording"]["artifact_digest"]


def test_unknown_familiarity_does_not_select_concise_wording(tmp_path):
    seed(tmp_path / "prepared", style="concise")
    with TestClient(backend(tmp_path)) as client:
        owner = profile(client)
        result = request_guidance(client, owner["session"]).json()
        assert result["wording"]["artifact_digest"] is None
        assert "wording_not_prepared" in result["wording"]["diagnostics"]


def test_corrupt_ui_snapshot_fails_closed_without_resampling(tmp_path):
    seed(tmp_path / "prepared")
    application = backend(tmp_path)
    with TestClient(application) as client:
        owner = profile(client)
        session = owner["session"]
        result = request_guidance(client, session).json()
        before = application.state.runtime.policy.export_state()
        path = next((tmp_path / "views").glob("*.json"))
        data = json.loads(path.read_text(encoding="utf-8"))
        data["checksum"] = "bad"
        path.write_text(json.dumps(data), encoding="utf-8")
        response = client.get(presentation_url(session, result["spec"]))
        assert response.status_code == 503
        assert application.state.runtime.policy.export_state() == before


def test_snapshot_write_failure_rolls_back_the_new_offer(tmp_path, monkeypatch):
    application = backend(tmp_path)
    with TestClient(application) as client:
        owner = profile(client)
        runtime = application.state.runtime
        before = runtime.export_state()
        def fail(*args):
            raise ArtifactStoreError("artifact_write_failed")
        monkeypatch.setattr(runtime.wording_views.files, "write_text", fail)
        response = request_guidance(client, owner["session"])
        assert response.status_code == 503
        assert runtime.export_state() == before
