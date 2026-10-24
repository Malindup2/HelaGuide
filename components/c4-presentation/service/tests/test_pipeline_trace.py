"""Trace original decisions, not a fabricated execution log. Offline providers only."""

import json
import sqlite3
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.legacy.prior import load_prior
from app.dev_main import create_app
from app.models.policy import PolicyConfig
from app.models.runtime_state import RuntimeState
from tests.test_corrections import correction_body
from tests.test_explanations import FakeProvider
from tests.test_feedback_persistence import feedback_body
from tests.test_guidance_routing import (anonymous, change_mode, display_body, profile,
                                       request_guidance, presentation_url, session_base)
from tests.test_wording_ui_api import seed


def config():
    return PolicyConfig(cold_start_updates=0, prior=load_prior(
        Path(__file__).resolve().parents[1] / "priors" / "pp1-provisional-v1.json"))


def backend(tmp_path, *, cfg=None, wording=False, graphs=None):
    return create_app(
        provider=FakeProvider(failure="offline_test"), database_path=tmp_path / "trace.sqlite3",
        policy_config=cfg or config(), allow_legacy_adaptive_sessions=False,
        prepared_wording_directory=tmp_path / "prepared" if wording else None,
        wording_views_directory=tmp_path / "views" if wording else None,
        graphs=graphs,
    )


def offer(client, *, owner=None, acknowledge=False):
    owner = owner or profile(client, lock_guided=True)
    result = request_guidance(client, owner["session"])
    assert result.status_code == 200, result.text
    spec = result.json()["spec"]
    url = presentation_url(owner["session"], spec)
    if acknowledge:
        assert client.post(url + "/ack", json=display_body(spec)).status_code == 200
    return owner, spec, url


def trace(client, url):
    response = client.get(url + "/pipeline-trace")
    assert response.status_code == 200, response.text
    assert response.headers["Cache-Control"] == "no-store"
    return response.json()


def row(tmp_path):
    with sqlite3.connect(tmp_path / "trace.sqlite3") as connection:
        return connection.execute("SELECT revision,manifest,payload,checksum FROM c4_snapshot").fetchone()


def test_original_records_all_candidates_and_evidence_boundaries(tmp_path):
    with TestClient(backend(tmp_path)) as client:
        owner, spec, url = offer(client)
        result = trace(client, url)
        original = client.get(url + "/inspector").json()
        assert result["records"]["policy_offer"] == original
        assert result["records"]["presentation"] == spec
        assert result["input"]["fingerprint_matches_saved_graph"]
        assert result["input"]["source_authenticity"] == "synthetic"
        assert result["input"]["historical_validation_event"] == "not_recorded"
        assert result["input"]["raw_plan_payload"] == "not_stored"
        assert len(result["structural_features"]) == 7
        for feature in result["structural_features"]:
            assert feature["measurement"] == original["decision"]["structural_features"][feature["name"]]
        assert len(result["candidates"]) == 64
        recorded_scores = {s["configuration"]["configuration_id"]: s for s in original["decision"]["candidate_scores"]}
        for candidate in result["candidates"]:
            cid = candidate["configuration"]["configuration_id"]
            assert candidate["score"] == recorded_scores.get(cid)
            if not candidate["feasible"]:
                assert candidate["score_status"] == "not_scored"
                assert candidate["score"] is None and candidate["rejections"]
        assert sum(c["selected"] for c in result["candidates"]) == 1
        assert result["selection"]["selection_mode"] == "thompson"
        assert result["selection"]["prior_status"] == "provisional_pending_expert_validation"
        assert len(result["selection"]["feature_names"]) == 656
        assert len(result["selection"]["context_encoding"]) == 81
        assert result["content"]["explanation_origin"] == "fallback"
        assert result["content"]["wording_status"] == "snapshot_not_available"
        assert result["learning"]["status"] == "awaiting_display_acknowledgment"
        assert result["learning"]["reward"] is None
        assert result["learning"]["linear_delta_b"] is None
        assert {b["kind"] for b in result["evidence_boundaries"]} == {"recorded", "derived", "unavailable"}
        index = client.get(session_base(owner["session"]) + "/pipeline-traces").json()
        assert index["presentations"][0]["exposure_id"] == spec["exposure_id"]


def test_repeated_reads_do_not_evaluate_generate_sample_learn_write_or_advance_rng(tmp_path, monkeypatch):
    seed(tmp_path / "prepared")
    application = backend(tmp_path, wording=True)
    with TestClient(application) as client:
        owner, _, url = offer(client, acknowledge=True)
        runtime = application.state.runtime
        before = runtime.export_state()
        saved_row = row(tmp_path)
        files = {p.name: p.read_bytes() for p in (tmp_path / "views").glob("*.json")}
        calls = list(runtime.provider.calls)
        def forbidden(*args, **kwargs):
            raise AssertionError("trace read invoked a mutation or generation path")
        monkeypatch.setattr(runtime.contexts, "evaluate", forbidden)
        monkeypatch.setattr(runtime.policy, "select_and_offer", forbidden)
        monkeypatch.setattr(runtime.policy, "apply_feedback", forbidden)
        monkeypatch.setattr(runtime.explanations, "explain", forbidden)
        monkeypatch.setattr(runtime.wording_views, "prepare", forbidden)
        monkeypatch.setattr(runtime.wording_views, "capture", forbidden)
        monkeypatch.setattr(runtime.wording_views.files, "write_text", forbidden)
        monkeypatch.setattr(runtime.store, "save", forbidden)
        first = trace(client, url)
        assert trace(client, url) == first
        assert client.get(session_base(owner["session"]) + "/pipeline-traces").status_code == 200
        assert runtime.export_state() == before
        assert row(tmp_path) == saved_row
        assert files == {p.name: p.read_bytes() for p in (tmp_path / "views").glob("*.json")}
        assert runtime.provider.calls == calls


def test_display_navigation_and_original_feedback_delta(tmp_path):
    with TestClient(backend(tmp_path)) as client:
        _, spec, url = offer(client, acknowledge=True)
        before = trace(client, url)
        assert before["learning"]["status"] == "no_accepted_feedback"
        assert before["display"]["displayed_action_ids"] == [spec["initial_action_id"]]
        revision = before["current"]["guidance"]["session_revision"]
        action = spec["pages"][1]["action_id"]
        response = client.post(url + "/navigation", json={
            "event_id": "event:" + uuid4().hex, "expected_revision": revision,
            "presentation_id": spec["presentation_id"],
            "configuration_id": spec["configuration"]["configuration_id"], "action_id": action})
        assert response.status_code == 200, response.text
        accepted = client.post(url + "/feedback", json=feedback_body(spec, "need_more"))
        assert accepted.status_code == 200
        result = trace(client, url)
        assert result["records"]["feedback"] == accepted.json()
        assert result["display"]["current_action_id"] == action
        assert result["display"]["navigation_event_count"] == 1
        assert result["learning"]["reward"] == 0
        assert result["learning"]["centered_reward"] == -0.5
        phi = result["records"]["policy_offer"]["decision"]["selected_features"]
        assert np.allclose(result["learning"]["linear_delta_b"], np.asarray(phi) * -0.5)
        correction = client.post(url + "/correction", json=correction_body(spec, "show_prerequisite_cues"))
        assert correction.status_code == 200, correction.text
        corrected = trace(client, url)
        assert corrected["records"]["correction"] == correction.json()
        assert corrected["learning"] == result["learning"]
        assert corrected["current"]["shared_posterior_revision"] == 1


def test_late_feedback_distinguishes_selection_update_and_current_revisions(tmp_path):
    with TestClient(backend(tmp_path)) as client:
        _, first, first_url = offer(client, acknowledge=True)
        _, second, second_url = offer(client, acknowledge=True)
        assert client.post(second_url + "/feedback", json=feedback_body(second)).status_code == 200
        assert client.post(first_url + "/feedback", json=feedback_body(first)).status_code == 200
        _, third, third_url = offer(client, acknowledge=True)
        assert client.post(third_url + "/feedback", json=feedback_body(third)).status_code == 200
        result = trace(client, first_url)
        assert result["selection"]["selection_posterior_revision"] == 0
        assert result["learning"]["revision_immediately_before_update"] == 1
        assert result["learning"]["resulting_posterior_revision"] == 2
        assert result["current"]["shared_posterior_revision"] == 3
        assert result["learning"]["historical_post_update_parameters"] == "not_separately_stored"


def test_original_context_graph_and_scores_survive_current_changes(tmp_path):
    application = backend(tmp_path)
    with TestClient(application) as client:
        owner, _, url = offer(client, acknowledge=True)
        original = trace(client, url)
        base = session_base(owner["session"])
        session = client.get(base).json()
        response = client.patch(base + "/context", json={"expected_revision": session["revision"],
                                "update": {"navigation_capability": 1}})
        assert response.status_code == 200
        # Trace historical records even if today's catalogue no longer has this procedure.
        application.state.runtime.procedures.clear()
        changed = trace(client, url)
        assert changed["records"] == original["records"]
        assert changed["candidates"] == original["candidates"]
        assert changed["selection"] == original["selection"]
        assert changed["current"]["user_settings"]["navigation_capability"] == 1
        assert changed["current"]["stale_for_display"] is True


def test_wording_trace_uses_frozen_snapshot_and_rejects_corrupt_sidecar(tmp_path):
    artifact = seed(tmp_path / "prepared")
    application = backend(tmp_path, wording=True)
    with TestClient(application) as client:
        _, _, url = offer(client)
        original = trace(client, url)
        assert original["content"]["wording_status"] == "reviewed_snapshot"
        assert original["records"]["wording_artifact"]["origin"] == "human_prepared"
        assert original["records"]["wording_artifact"]["review"] is not None
        (tmp_path / "prepared" / f"{artifact.request_key}.json").unlink()
        seed(tmp_path / "prepared", heading="A newer wording asset")
        assert trace(client, url)["records"]["wording"] == original["records"]["wording"]
        path = next((tmp_path / "views").glob("*.json"))
        data = json.loads(path.read_text(encoding="utf-8"))
        data["checksum"] = "bad"
        path.write_text(json.dumps(data), encoding="utf-8")
        state = application.state.runtime.export_state()
        assert client.get(url + "/pipeline-trace").status_code == 503
        assert application.state.runtime.export_state() == state


def test_missing_reviewed_wording_remains_fallback_in_trace(tmp_path):
    seed(tmp_path / "prepared", reviewed=False)
    with TestClient(backend(tmp_path, wording=True)) as client:
        _, _, url = offer(client)
        result = trace(client, url)
        assert result["content"]["wording_status"] == "snapshot_source_fallback"
        assert "wording_human_review_required" in result["content"]["wording_diagnostics"]
        assert result["content"]["wording_digest"] is None


def test_trace_recovers_unchanged_after_restart_and_does_not_change_manifest(tmp_path):
    application = backend(tmp_path)
    with TestClient(application) as client:
        _, spec, url = offer(client, acknowledge=True)
        client.post(url + "/feedback", json=feedback_body(spec))
        original = trace(client, url)
        saved_row = row(tmp_path)
    with TestClient(backend(tmp_path)) as client:
        assert trace(client, url) == original
        assert row(tmp_path) == saved_row
    assert "PipelineTrace" not in json.dumps(RuntimeState.model_json_schema())


@pytest.mark.parametrize("forced", [False, True])
def test_cold_start_and_forced_decisions_do_not_invent_sampled_scores(tmp_path, forced):
    cfg = PolicyConfig()  # historical neutral baseline mode
    with TestClient(backend(tmp_path, cfg=cfg)) as client:
        owner = profile(client)
        if forced:
            session = owner["session"]
            response = client.patch(session_base(session) + "/context", json={
                "expected_revision": session["revision"], "update": {"locks": {
                    "presentation_mode": "OVERVIEW", "progressive_disclosure": False,
                    "previous_context_recap": False, "relationship_visual": "NONE", "prerequisite_cue": False}}})
            assert response.status_code == 200
        _, _, url = offer(client, owner=owner)
        result = trace(client, url)
        assert result["selection"]["selection_mode"] == ("forced" if forced else "cold_start_baseline")
        assert result["selection"]["prior_version"] == "neutral"
        assert result["selection"]["sampled_candidate_count"] == 0
        assert all(c["score"]["sampled_score"] is None for c in result["candidates"] if c["feasible"])


def test_standard_status_ownership_and_disabled_profile_historical_reads(tmp_path):
    with TestClient(backend(tmp_path)) as client:
        for session in (anonymous(client), profile(client, enabled=False)["session"]):
            result = client.get(session_base(session) + "/pipeline-traces")
            assert result.status_code == 200
            assert result.json()["current_request_routing"] == "standard"
            assert result.json()["presentations"] == []
            assert result.json()["standard_guidance_history"] == "not_persisted_no_policy_or_learning_record"
        owner, _, url = offer(client, acknowledge=True)
        stranger = anonymous(client)
        exposure_path = url[url.index("/presentations/"):]
        assert client.get(session_base(stranger) + exposure_path + "/pipeline-trace").status_code == 404
        assert client.get("/dev/v1/sessions/guest:" + "0" * 32 + "/pipeline-traces").status_code == 404
        change_mode(client, owner["profile"], False)
        index = client.get(session_base(owner["session"]) + "/pipeline-traces").json()
        assert index["current_request_routing"] == "standard"
        assert len(index["presentations"]) == 1
        assert trace(client, url)["current"]["stale_for_display"] is True


def test_partial_measurements_do_not_become_exact_in_trace(tmp_path):
    from app.procedures.demo_procedures import load_demo_procedures
    graph = load_demo_procedures()[0][0]
    graph = graph.model_copy(update={"completeness": graph.completeness.model_copy(update={
        "actions": "partial", "content": "partial", "prerequisites": "unknown"})})
    with TestClient(backend(tmp_path, graphs=(graph,))) as client:
        _, _, url = offer(client, owner=profile(client))
        features = {f["name"]: f["measurement"] for f in trace(client, url)["structural_features"]}
        assert features["step_count"]["completeness"] == "partial"
        assert features["step_count"]["observed"] > 0
        assert features["step_count"]["exact_value"] is None
        assert features["dependency_count"]["completeness"] == "unknown"


def test_inconsistent_score_join_fails_closed_without_sampling(tmp_path):
    application = backend(tmp_path)
    with TestClient(application) as client:
        _, spec, url = offer(client)
        runtime = application.state.runtime
        selected = runtime.policy.get_offer(spec["exposure_id"])
        runtime.policy._offers[spec["exposure_id"]] = selected.model_copy(update={
            "decision": selected.decision.model_copy(update={"candidate_scores": ()})})
        assert client.get(url + "/pipeline-trace").status_code == 503
