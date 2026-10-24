"""Bounded priors, live feedback, recovery and explicit simulation restart."""

import json
import sqlite3
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.legacy.v1_policy import (FEATURE_DIMENSION, FEATURE_NAMES_SHARED, FEATURE_SCALE,
                             SharedLinTSPolicy, _GaussianPosterior, feature_vector)
from app.legacy.prior import compile_prior, load_prior, prior_digest
from app.procedures.procedure_features import extract_structural_features
from app.procedures.demo_procedures import load_demo_procedures
from app.legacy.state_store import StateCompatibilityError, StateStoreError
from app.host.user_context import InMemoryContextService
from app.dev_main import create_app
from app.models.policy import PolicyConfig
from app.models.user_context import ContextUpdate, FamiliarityReport
from app.legacy.policy_runs import (LEGACY_SCHEMA, checksum, fresh_state, operate_sqlite, read_state)
from tests.test_explanations import FakeProvider
from tests.test_feedback_persistence import feedback_body
from tests.test_guidance_routing import (anonymous, profile, request_guidance,
                                       display_body, presentation_url)


PRIOR_PATH = Path(__file__).resolve().parents[1] / "priors" / "pp1-provisional-v1.json"


def config():
    return PolicyConfig(cold_start_updates=0, prior=load_prior(PRIOR_PATH))


def application(path=None, cfg=None):
    return create_app(provider=FakeProvider(failure="offline_test"), database_path=path,
                      policy_config=cfg or config(), allow_legacy_adaptive_sessions=False)


def select_and_rate(client):
    owner = profile(client, lock_guided=True)
    response = request_guidance(client, owner["session"])
    assert response.status_code == 200, response.text
    spec = response.json()["spec"]
    url = presentation_url(owner["session"], spec)
    assert client.post(url + "/ack", json=display_body(spec)).status_code == 200
    receipt = client.post(url + "/feedback", json=feedback_body(spec))
    assert receipt.status_code == 200, receipt.text
    return owner, spec, url


def test_bounded_mean_has_no_pseudo_feedback_and_same_uncertainty():
    cfg = config()
    seeded = _GaussianPosterior(FEATURE_DIMENSION, cfg)
    neutral = _GaussianPosterior(FEATURE_DIMENSION, PolicyConfig(cold_start_updates=0))
    assert seeded.revision == 0
    assert np.array_equal(seeded._precision, neutral._precision)
    assert np.array_equal(seeded._factor, neutral._factor)
    assert np.allclose(seeded._b, seeded._precision @ seeded._mean)
    assert seeded._mean.any()
    graph = load_demo_procedures()[0][0]
    features = extract_structural_features(graph)
    contexts = InMemoryContextService()
    session = contexts.create_session()
    snapshot = contexts.evaluate(session.session_id, graph, features).snapshot
    from app.procedures.scaffolds import enumerate_scaffolds
    matrix = np.stack([feature_vector(features, snapshot, c) for c in enumerate_scaffolds()])
    means, std = seeded.moments(matrix)
    assert np.max(abs(means - 0.5)) <= 0.25
    assert np.array_equal(std, neutral.moments(matrix)[1])
    assert prior_digest(cfg.prior) == prior_digest(load_prior(PRIOR_PATH))


def test_low_and_high_familiarity_mean_contrasts_and_unknown():
    cfg = config()
    mean = compile_prior(cfg.prior, FEATURE_NAMES_SHARED, FEATURE_SCALE)
    assert mean[FEATURE_NAMES_SHARED.index("user.familiarity.unknown * guided")] == 0
    graph = load_demo_procedures()[0][0]
    features = extract_structural_features(graph)
    contexts = InMemoryContextService()
    from app.procedures.scaffolds import enumerate_scaffolds
    overview = enumerate_scaffolds()[0]
    guided = next(c for c in enumerate_scaffolds() if c.presentation_mode == "GUIDED"
                  and not c.progressive_disclosure and not c.previous_context_recap
                  and c.relationship_visual == "NONE" and not c.prerequisite_cue)
    contrasts = []
    for score in (1, 5):
        session = contexts.create_session()
        contexts.update_context(session.session_id, ContextUpdate(familiarity=FamiliarityReport(
            service_id=features.requested_service_id, score=score)), expected_revision=0)
        snapshot = contexts.evaluate(session.session_id, graph, features).snapshot
        contrasts.append((feature_vector(features, snapshot, guided) - feature_vector(features, snapshot, overview)) @ mean)
    assert contrasts[0] > 0 > contrasts[1]


@pytest.mark.parametrize("bad", ["unknown", "duplicate", "too_strong", "fake_expert", "bad_source", "nan"])
def test_invalid_prior_rejected(bad, tmp_path):
    data = load_prior(PRIOR_PATH).model_dump(mode="json")
    if bad == "unknown":
        data["judgments"][0]["context"] = "user.familiarity.fake"
    elif bad == "duplicate":
        data["judgments"].append(data["judgments"][0])
    elif bad == "too_strong":
        data["judgments"][0]["score_delta"] = 0.9
    elif bad == "fake_expert":
        data["status"] = "expert_validated"
    elif bad == "bad_source":
        data["judgments"][0]["source_ids"] = ["missing"]
    else:
        data["judgments"][0]["score_delta"] = float("nan")
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        load_prior(path)


def test_prior_cannot_be_bypassed_by_cold_start_gate():
    with pytest.raises(ValidationError):
        PolicyConfig(prior=load_prior(PRIOR_PATH))


@pytest.mark.parametrize("reward", [0, 1])
def test_real_observation_updates_from_prior_with_existing_centered_reward_math(reward):
    cfg = config()
    posterior = _GaussianPosterior(FEATURE_DIMENSION, cfg)
    vector = np.zeros(FEATURE_DIMENSION)
    vector[FEATURE_NAMES_SHARED.index("user.familiarity.level_1 * guided")] = 1 / FEATURE_SCALE
    precision = posterior._precision.copy()
    b = posterior._b.copy()
    posterior.observe(vector, reward)
    assert posterior.revision == 1
    assert np.allclose(posterior._precision, precision + np.outer(vector, vector))
    assert np.allclose(posterior._b, b + vector * (reward - 0.5))
    assert np.allclose(posterior._precision @ posterior._mean, posterior._b)


def test_new_profiles_use_shared_policy_before_and_after_feedback(tmp_path):
    path = tmp_path / "state.sqlite3"
    with TestClient(application(path)) as client:
        runtime = client.app.state.runtime
        before = runtime.policy.posterior_fingerprint()
        owner, spec, url = select_and_rate(client)
        offer = runtime.policy.get_offer(spec["exposure_id"])
        assert offer.decision.selection_mode == "thompson"
        assert offer.decision.posterior_revision == 0
        assert offer.decision.config.prior == config().prior
        assert runtime.policy.posterior_revision == 1
        assert runtime.policy.posterior_fingerprint() != before
        client.post(url + "/feedback", json=feedback_body(spec))
        assert runtime.policy.posterior_revision == 1
        new_owner = profile(client)
        assert runtime.policy.posterior_revision == 1  # creation is not learning
        result = request_guidance(client, new_owner["session"]).json()
        new_offer = runtime.policy.get_offer(result["spec"]["exposure_id"])
        assert new_offer.decision.selection_mode == "thompson"
        assert new_offer.decision.posterior_revision == 1
        saved = runtime.policy.export_state()
        status = client.get("/dev/v1/policy").json()
        assert status["prior_status"] == "provisional_pending_expert_validation"
        for session in (anonymous(client), profile(client, enabled=False)["session"]):
            assert request_guidance(client, session).json()["mode"] == "standard"
        assert runtime.policy.export_state() == saved
    with TestClient(application(path)) as client:
        assert client.app.state.runtime.policy.export_state() == saved
        assert client.get(url).status_code == 200
        assert client.post(url + "/feedback", json=feedback_body(spec)).status_code == 200
        assert client.app.state.runtime.policy.posterior_revision == 1


def test_replacing_prior_requires_explicit_new_run(tmp_path):
    path = tmp_path / "state.sqlite3"
    with TestClient(application(path)) as client:
        select_and_rate(client)
    changed = config().prior.model_copy(update={"version": "expert-reviewed-v2"})
    with pytest.raises(StateCompatibilityError):
        with TestClient(application(path, PolicyConfig(cold_start_updates=0, prior=changed))):
            pass


def test_restart_archives_full_snapshot_retains_profiles_and_blocks_old_feedback(tmp_path):
    path = tmp_path / "state.sqlite3"
    with TestClient(application(path, PolicyConfig())) as client:
        owner, spec, url = select_and_rate(client)
        old = client.app.state.runtime.export_state()
    backup = tmp_path / "archive.json"
    run = old.policy.policy_run_id
    report = operate_sqlite(path, backup, config(), run)
    archived = json.loads(backup.read_text(encoding="utf-8"))
    assert archived["checksum"] == checksum(archived["payload"])
    assert json.loads(archived["payload"])["policy"]["policy_run_id"] == run
    assert json.loads(archived["payload"])["feedback"]
    assert report["policy_run_id"] != run
    assert report["posterior_revision"] == report["accepted_feedback_count"] == 0
    assert report["profile_count"] == 1
    with TestClient(application(path)) as client:
        runtime = client.app.state.runtime
        assert runtime.profiles[owner["profile"]["profile_id"]].model_dump(mode="json") == owner["profile"]
        assert runtime.contexts.get_session(owner["session"]["session_id"]).settings == old.sessions[0].session.settings
        assert not runtime.presentations and not runtime.feedback and not runtime.corrections
        assert all(not s.offers for s in runtime.export_state().sessions)
        assert client.get(url).status_code == 404
        assert client.post(url + "/feedback", json=feedback_body(spec)).status_code == 404
        fresh = request_guidance(client, owner["session"])
        assert fresh.status_code == 200, fresh.text
        assert fresh.json()["spec"]["exposure_id"] != spec["exposure_id"]
        assert runtime.policy.posterior_revision == 0
    # A repeated stale command cannot silently reset this new run again.
    with pytest.raises(StateStoreError, match="run changed"):
        operate_sqlite(path, tmp_path / "again.json", config(), run)
    assert not (tmp_path / "again.json").exists()


def test_exact_previous_schema_is_supported_and_backup_failure_rolls_back(tmp_path):
    path = tmp_path / "state.sqlite3"
    with TestClient(application(path, PolicyConfig())) as client:
        select_and_rate(client)
        old = client.app.state.runtime.export_state()
    with sqlite3.connect(path) as connection:
        revision, manifest, payload, digest = connection.execute(
            "SELECT revision,manifest,payload,checksum FROM c4_snapshot").fetchone()
        manifest = json.loads(manifest)
        manifest["runtime_schema_fingerprint"] = LEGACY_SCHEMA
        manifest["policy_config"].pop("prior")
        data = json.loads(payload)
        data["policy"]["config"].pop("prior")
        for offer in data["policy"]["offers"]:
            offer["decision"]["config"].pop("prior")
        payload = json.dumps(data)
        row = (revision, json.dumps(manifest), payload, checksum(payload))
        connection.execute("UPDATE c4_snapshot SET revision=?,manifest=?,payload=?,checksum=?", row)
    assert read_state(row, "sqlite").policy.policy_run_id == old.policy.policy_run_id
    backup = tmp_path / "existing.json"
    backup.write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        operate_sqlite(path, backup, config(), old.policy.policy_run_id)
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT revision,manifest,payload,checksum FROM c4_snapshot").fetchone() == row
    operate_sqlite(path, tmp_path / "archive.json", config(), old.policy.policy_run_id)


def test_neutral_restart_and_participant_protection(tmp_path):
    with TestClient(application(cfg=PolicyConfig())) as client:
        old = client.app.state.runtime.export_state()
    state = fresh_state(old, PolicyConfig(cold_start_updates=0))
    assert state.policy.config.prior is None
    assert state.policy.posterior_revision == 0
    with pytest.raises(StateStoreError, match="simulation-only"):
        fresh_state(old, PolicyConfig(feedback_mode="participant"))


def test_prior_never_overrides_hard_feasibility():
    from app.models.scaffolds import PresentationLocks
    graph = load_demo_procedures()[0][0]
    features = extract_structural_features(graph)
    contexts = InMemoryContextService()
    session = contexts.create_session()
    contexts.update_context(session.session_id, ContextUpdate(locks=PresentationLocks(
        presentation_mode="OVERVIEW", progressive_disclosure=False, previous_context_recap=False,
        relationship_visual="NONE", prerequisite_cue=False)), expected_revision=0)
    policy = SharedLinTSPolicy(contexts, config=config())
    selected = policy.select_and_offer(session.session_id, graph, features,
                                      intended_action_ids=tuple(a.action_id for a in graph.actions))
    assert selected.decision.selection_mode == "forced"
    assert selected.decision.configuration.presentation_mode == "OVERVIEW"
    assert policy.posterior_revision == 0
