"""PP1 Shared Gaussian LinTS under content 3.1: a fresh compatible policy, real selection, attributed feedback, restart, no 3.0 reuse."""
import shutil
from pathlib import Path
from uuid import uuid4
import numpy as np
import pytest
from fastapi.testclient import TestClient
from app.guidance import features, policy
from app.guidance.catalogue import CATALOGUE
from app.guidance.flavours import FLAVOUR_31
from app.guidance.policy import PROFILE_30, Model, PolicyStore
from app.guidance.v31_pipeline import ACTION_SCHEMA31, FEATURE_FINGERPRINT31, FEATURE_SCHEMA31, PROFILE_31, manifest31
from app.v2.api import create_app
from app.v2.identity import WorkspaceRuntime
from app.v2.registration import workspace_registry

C4 = Path(__file__).resolve().parents[2]
ROOT = '/workspace/guidance'
PID = 'synthetic-practice-v2'
TOKEN = 'pp1-v31-test-capability-' + ('x' * 40)


@pytest.fixture
def active():
    tag = uuid4().hex[:8]
    prepared = C4 / 'service' / '.local' / 'prepared-content' / 'v31-tests' / tag / 'v31'
    store = C4 / 'service' / '.local' / 'pp1-learning' / 'v31-tests' / tag
    runtime = WorkspaceRuntime(procedures=workspace_registry())
    policy_options = {'directory': store / 'interactive', 'seed': 3}
    options = {'directory': prepared, 'demo_fixtures': True, 'flavour': FLAVOUR_31}
    with TestClient(create_app(runtime=runtime, workspace=True, prepared_content_options=options,
                               guidance_api_options={'research_enabled': True, 'flavour': FLAVOUR_31, 'policy_options': policy_options})) as client:
        yield client, runtime, client.app.state.guidance_api, policy_options
    runtime.close()
    shutil.rmtree(prepared.parent, ignore_errors=True)
    shutil.rmtree(store, ignore_errors=True)


def profile(client, familiarity=1, confidence=1, pid=PID):
    service = next(p['service_id'] for p in client.get(ROOT + '/procedures').json() if p['procedure_id'] == pid)
    result = client.post(ROOT + '/profiles', json={'profile_id': 'profile:' + uuid4().hex, 'display_name': 'PP1 3.1 synthetic test profile', 'personalization_enabled': True,
                                                  'initial_context': {'navigation_capability': confidence, 'familiarity': [{'service_id': service, 'score': familiarity}]}})
    assert result.status_code == 200, result.text
    return result.json()['session']['session_id']


def start(client, sid, pid=PID, **extra):
    return client.post(ROOT + '/requests', json={'request_id': uuid4().hex, 'session_id': sid, 'procedure_id': pid, 'capability_token': TOKEN, 'mode': 'personalized', **extra})


def displayed(client, j):
    return client.post(ROOT + '/journeys/' + j['journey_id'] + '/events', headers={'X-C4-Token': TOKEN},
                       json={'event_id': uuid4().hex, 'view_id': j['view_id'], 'type': 'view_displayed', 'action_ids': [j['document']['actions'][0]['id']]})


def rating(client, j, r='fits', identifier=None):
    return client.post(ROOT + '/journeys/' + j['journey_id'] + '/ratings', headers={'X-C4-Token': TOKEN}, json={'event_id': identifier or uuid4().hex, 'view_id': j['view_id'], 'rating': r})


def test_versions_and_fresh_prior_are_bound_to_3_1(active):
    client, runtime, api, options = active
    status = client.get(ROOT + '/status').json()
    assert status['personalized_selection_available'] and status['encoder_status'] == FEATURE_SCHEMA31
    assert status['policy']['posterior_revision'] == 0 and status['policy']['training_provenance'] == 'fresh_prior'
    assert status['policy']['manifest'] == manifest31()
    assert api.policy.expected['features'] == FEATURE_SCHEMA31 and api.policy.expected['feature_fingerprint'] == FEATURE_FINGERPRINT31
    assert features.FINGERPRINT != FEATURE_FINGERPRINT31 and manifest31()['dimension'] == 525


def test_personalized_selection_records_everything_needed_to_inspect_it(active):
    client, runtime, api, _ = active
    sid = profile(client)
    j = start(client, sid).json()
    assert j['selection']['kind'] == 'shared_gaussian_lints' and j['selection']['learning_eligible']
    assert j['selection']['action_schema'] == ACTION_SCHEMA31 and j['selection']['policy']['encoder_schema'] == FEATURE_SCHEMA31
    assert j['availability']['feasibility_fingerprint'] and j['document']['content_schema'] == 'c4-guidance-content-3.1'
    record = client.get(ROOT + '/journeys/' + j['journey_id'] + '/inspector', headers={'X-C4-Token': TOKEN}).json()
    decision = record['policy']
    assert len(decision['selected_features']) == 525 and decision['feature_fingerprint'] == FEATURE_FINGERPRINT31
    assert decision['content_schema'] == 'c4-guidance-content-3.1' and decision['action_schema'] == ACTION_SCHEMA31
    assert decision['feasibility_fingerprint'] == j['availability']['feasibility_fingerprint'] and decision['manifest'] == manifest31()
    feasible = [c['configuration'] for c in j['availability']['candidates'] if c['feasible']]
    assert [c['configuration'] for c in decision['candidates']] == feasible
    assert all(c['id'].startswith(ACTION_SCHEMA31 + ':') and 'sampled_score' in c for c in decision['candidates'])
    best = max(decision['candidates'], key=lambda c: c['sampled_score'])
    assert best['configuration'] == j['selection']['configuration']


def test_feedback_updates_the_3_1_policy_exactly_once_and_survives_restart(active):
    client, runtime, api, options = active
    j = start(client, profile(client)).json()
    assert rating(client, j).status_code == 409                       # display not yet acknowledged
    assert displayed(client, j).status_code == 200
    before, identifier = api.policy.status(), uuid4().hex
    receipt = rating(client, j, identifier=identifier)
    assert receipt.status_code == 200 and receipt.json()['policy_updated'] and receipt.json()['reward'] == 1
    assert rating(client, j, identifier=identifier).json() == receipt.json()   # same event: idempotent
    assert rating(client, j, r='does_not_fit').status_code == 409              # second rating refused
    after = api.policy.status()
    assert after['posterior_revision'] == before['posterior_revision'] + 1 and after['accepted_feedback_count'] == 1
    assert PolicyStore(**options, profile=PROFILE_31).status() == after       # restart: same compatible state loads


def test_does_not_fit_trains_with_reward_zero(active):
    client, _, api, _ = active
    j = start(client, profile(client)).json()
    displayed(client, j)
    receipt = rating(client, j, r='does_not_fit').json()
    assert receipt['reward'] == 0 and receipt['policy_updated'] and api.policy.status()['posterior_revision'] == 1


def test_guest_previews_manual_views_and_personalization_off_never_train(active):
    client, _, api, _ = active
    sid = profile(client)
    j = start(client, sid).json()
    displayed(client, j)
    before = api.policy.status()
    config = j['selection']['configuration']
    child = client.post(ROOT + '/journeys/' + j['journey_id'] + '/views', headers={'X-C4-Token': TOKEN}, json={'request_id': uuid4().hex, 'parent_view_id': j['view_id'], 'configuration': config})
    assert child.status_code == 200 and child.json()['selection']['kind'] == 'manual_adjustment'
    assert rating(client, child.json()).json()['policy_updated'] is False
    guest = client.post(ROOT + '/guests').json()['session_id']
    g = start(client, guest).json()
    assert g['selection']['kind'] == 'standard' and rating(client, g).status_code == 403
    preview = client.post(ROOT + '/research/previews', json={'request_id': uuid4().hex, 'session_id': sid, 'procedure_id': PID, 'capability_token': TOKEN, 'configuration': config, 'mode': 'research_preview'}).json()
    assert rating(client, preview).json()['policy_updated'] is False
    assert api.policy.status() == before


def test_hard_accessibility_constraints_bind_the_selection(active):
    client, _, _, _ = active
    sid = profile(client)
    ctx = client.get(ROOT + '/context/' + sid, params={'procedure_id': PID}).json()
    patch = {'request_id': uuid4().hex, 'expected_revision': ctx['revision'], 'accessibility': {'no_map': True, 'no_guided': True, 'no_disclosure': True}}
    assert client.patch(ROOT + '/context/' + sid, json=patch).status_code == 200
    for _ in range(5):
        c = start(client, sid).json()['selection']['configuration']
        assert c['relationships'] != 'map' and c['navigation'] == 'overview' and c['disclosure'] == 'off'


def test_official_procedures_select_only_from_their_safe_feasible_set(active):
    client, _, _, _ = active
    pid = 'official-nic_amendment-v3'
    sid = profile(client, pid=pid)
    j = start(client, sid, pid=pid).json()
    c = j['selection']['configuration']
    assert c['explanation'] == 'concise' and c['disclosure'] == 'off' and c['recap'] == 'off' and c['segmentation'] == 'off'
    assert j['preparation']['content_state'] == 'source_fallback'


def test_a_3_0_store_checkpoint_and_manifest_can_never_load_into_3_1(tmp_path):
    base = C4 / 'service' / '.local' / 'pp1-learning' / 'v31-tests' / uuid4().hex[:8]
    try:
        old_store = PolicyStore(base / 'old')
        with pytest.raises(ValueError, match='existing PP1 state manifest differs'):
            PolicyStore(base / 'old', profile=PROFILE_31)
        with pytest.raises(ValueError, match='existing PP1 state manifest differs'):
            PolicyStore(base / 'old', profile=PROFILE_30, seed=9)
        new_store = PolicyStore(base / 'new', profile=PROFILE_31)
        with pytest.raises(ValueError, match='existing PP1 state manifest differs'):
            PolicyStore(base / 'new')
        old_model = Model()
        blob = old_model.state()
        with pytest.raises(ValueError, match='incompatible PP1 checkpoint manifest'):
            Model.restore(blob, manifest31(), PROFILE_31)
        with pytest.raises(ValueError, match='incompatible PP1 checkpoint manifest'):
            PolicyStore(base / 'seeded', checkpoint=_save(old_model, base), profile=PROFILE_31)
        assert old_store.status()['posterior_revision'] == 0 and new_store.status()['manifest'] == manifest31()
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _save(model, base):
    path = base / 'old-checkpoint.npz'
    model.save(path)
    return path


@pytest.mark.parametrize('variant', ['416', '451', '516', '525'])
def test_ablation_variants_keep_working_under_3_1(variant):
    model = Model(variant, profile=PROFILE_31)
    assert model.manifest['dimension'] == int(variant) and model.manifest['action'] == ACTION_SCHEMA31
    m = next(iter(workspace_registry().values()))
    from app.guidance.sources import ProcedureSource
    from app.v2.measurements import measurements
    meas = measurements(m['graph'], m.get('overlay'))
    matrix = np.array([features.encode(meas, {'familiarity': 2, 'confidence': 4}, c, variant) for c in CATALOGUE])
    index, scores, _, _ = model.score(matrix, 5)
    assert matrix.shape == (96, int(variant)) and 0 <= index < 96 and np.isfinite(scores).all()
    model.update(matrix[index], 1)
    restored = Model.restore(model.state(), model.manifest, PROFILE_31)
    assert restored.state() == model.state() and restored.revision == 1
    assert ProcedureSource is not None


def test_exploration_scale_is_part_of_the_manifest_so_stores_and_checkpoints_cannot_be_mixed():
    base = C4 / 'service' / '.local' / 'pp1-learning' / 'v31-tests' / uuid4().hex[:8]
    try:
        tuned = PolicyStore(base / 'tuned', profile=PROFILE_31, exploration=0.25)
        assert tuned.status()['manifest']['exploration'] == 0.25
        with pytest.raises(ValueError, match='existing PP1 state manifest differs'):
            PolicyStore(base / 'tuned', profile=PROFILE_31)
        blob = Model(exploration=0.25, profile=PROFILE_31)
        path = base / 'tuned-checkpoint.npz'
        blob.save(path)
        PolicyStore(base / 'seeded', profile=PROFILE_31, exploration=0.25, checkpoint=path)
        with pytest.raises(ValueError, match='incompatible PP1 checkpoint manifest'):
            PolicyStore(base / 'seeded-default', profile=PROFILE_31, checkpoint=path)
    finally:
        shutil.rmtree(base, ignore_errors=True)
