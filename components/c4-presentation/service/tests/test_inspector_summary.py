"""The Research Inspector summary reports only stored decision values and separates the reasons a process map can be unavailable."""
from pathlib import Path
from uuid import uuid4
from fastapi.testclient import TestClient
from app.guidance.flavours import FLAVOUR_31
from app.host.application import create_app
from app.host.identity import WorkspaceRuntime
from app.procedures.registration import workspace_registry

C4 = Path(__file__).resolve().parents[2]
ROOT = '/workspace/guidance'
TOKEN = 'inspector-summary-capability-' + 'x' * 20
H = {'X-C4-Token': TOKEN}
NIC, PARALLEL = 'official-nic_amendment-v4', 'synthetic-parallel-v1'


def build(tmp: Path):
    entries = workspace_registry()
    options = {'research_enabled': True, 'flavour': FLAVOUR_31, 'demo_accepted': True, 'demo_provisional': True,
               'policy_options': {'directory': C4 / 'service' / '.local' / 'pp1-learning' / 'v31-tests' / ('insp-' + uuid4().hex[:8]), 'seed': 21}}
    return {'path': tmp / 'v2' / 'workspace' / 'api.sqlite3', 'workspace': True, 'runtime_class': lambda path, **kw: WorkspaceRuntime(path, procedures=entries, **kw),
            'prepared_content_options': {'directory': tmp / 'prepared-content' / 'v31', 'demo_fixtures': True, 'flavour': FLAVOUR_31}, 'guidance_api_options': options}


def profile(client, pid, *, no_map=False, layout=None):
    service = next(p['service_id'] for p in client.get(ROOT + '/procedures').json() if p['procedure_id'] == pid)
    r = client.post(ROOT + '/profiles', json={'profile_id': 'profile:' + uuid4().hex, 'display_name': 'inspector test', 'personalization_enabled': True,
                                              'initial_context': {'navigation_capability': 1, 'familiarity': [{'service_id': service, 'score': 1}],
                                                                  'preferences': {'presentation_mode': layout} if layout else {},
                                                                  'accessibility': {'allow_relationship_visuals': not no_map, 'allow_collapsed_content': True, 'allow_guided_navigation': True}}})
    assert r.status_code == 200, r.text
    return r.json()['session']['session_id']


def ask(client, pid, sid, mode='personalized'):
    r = client.post(ROOT + '/requests', json={'request_id': uuid4().hex, 'session_id': sid, 'procedure_id': pid, 'capability_token': TOKEN, 'mode': mode})
    assert r.status_code == 200, r.text
    return r.json()


def inspect(client, journey):
    return client.get(ROOT + '/journeys/' + journey['journey_id'] + '/inspector', headers=H).json()


def test_the_summary_matches_the_stored_decision_record(tmp_path):
    with TestClient(create_app(**build(tmp_path))) as client:
        sid = profile(client, NIC, layout='GUIDED')
        j = ask(client, NIC, sid)
        record = inspect(client, j)
        s, decision = record['summary'], record['policy']
        chosen = next(c for c in decision['candidates'] if c['id'] == decision['selected_id'])
        assert s['personalized'] and s['kind'] == 'shared_gaussian_lints'
        assert s['selected_configuration'] == j['selection']['configuration'] == chosen['configuration']
        assert s['sampled_score'] == chosen['sampled_score'] and s['posterior_mean'] == chosen['posterior_mean']
        assert s['policy']['decision_id'] == decision['policy']['decision_id'] == j['selection']['policy']['decision_id']
        assert s['policy']['posterior_revision'] == decision['policy']['posterior_revision'] and s['policy']['model_manifest_fingerprint'] == decision['policy']['model_manifest_fingerprint']
        assert s['feasible_count'] == j['availability']['feasible_count'] == len(decision['candidates']) == 64
        assert s['effective_context']['familiarity'] == 1 and s['effective_context']['confidence'] == 1
        assert s['effective_context']['soft_preferences'] == {'navigation': 'guided'}
        assert s['hard_restrictions'] == {'no_guided': False, 'no_map': False, 'no_disclosure': False, 'locks': {}}
        assert s['structure']['step_count'] == {'observed': 7, 'completeness': 'complete'} and s['structure']['parallel_group_count']['completeness'] == 'unknown'
        assert s['learning']['eligible'] is True
        assert s['selected_description'] in s['explanation'] and 'highest sampled score' in s['explanation'] and 'because' not in s['explanation'].lower()


def test_standard_guidance_is_reported_as_standard_with_no_scoring(tmp_path):
    with TestClient(create_app(**build(tmp_path))) as client:
        guest = client.post(ROOT + '/guests').json()['session_id']
        j = ask(client, NIC, guest, mode='standard')
        s = inspect(client, j)['summary']
        assert not s['personalized'] and s['sampled_score'] is None and s['policy'] is None and s['learning']['eligible'] is False
        assert 'No model scoring was run' in s['explanation']


def test_eligibility_follows_rating_and_manual_adjustment(tmp_path):
    with TestClient(create_app(**build(tmp_path))) as client:
        rated, adjusted = ask(client, NIC, profile(client, NIC)), ask(client, NIC, profile(client, NIC))
        for j in (rated, adjusted):
            client.post(ROOT + '/journeys/' + j['journey_id'] + '/events', headers=H, json={'event_id': uuid4().hex, 'view_id': j['view_id'], 'type': 'view_displayed', 'action_ids': [j['document']['actions'][0]['id']]})
        assert client.post(ROOT + '/journeys/' + rated['journey_id'] + '/ratings', headers=H, json={'event_id': uuid4().hex, 'view_id': rated['view_id'], 'rating': 'fits', 'reasons': []}).status_code == 200
        assert inspect(client, rated)['summary']['learning'] == {'eligible': False, 'reason': 'The original view has already been rated; one rating updates the model once.'}
        other = {**adjusted['selection']['configuration'], 'disclosure': 'off' if adjusted['selection']['configuration']['disclosure'] == 'on' else 'on'}
        assert client.post(ROOT + '/journeys/' + adjusted['journey_id'] + '/views', headers=H, json={'request_id': uuid4().hex, 'parent_view_id': adjusted['view_id'], 'configuration': other}).status_code == 200
        s = inspect(client, adjusted)['summary']
        assert s['adjusted_by_citizen'] and s['learning']['eligible'] is False and s['selected_configuration'] == adjusted['selection']['configuration'] and s['displayed_configuration'] == other


def test_map_availability_separates_coverage_accessibility_and_policy_choice(tmp_path):
    with TestClient(create_app(**build(tmp_path))) as client:
        nic = inspect(client, ask(client, NIC, profile(client, NIC)))['summary']['map']
        assert nic['status'] == 'coverage_incomplete' and 'parallel_groups' in nic['detail'] and nic['map_configurations_feasible'] == 0
        blocked = inspect(client, ask(client, PARALLEL, profile(client, PARALLEL, no_map=True)))['summary']['map']
        assert blocked['status'] == 'accessibility_restriction' and blocked['map_configurations_feasible'] == 0
        statuses = set()
        for _ in range(12):
            j = ask(client, PARALLEL, profile(client, PARALLEL))
            m = inspect(client, j)['summary']['map']
            assert m['map_configurations_feasible'] == 32 and m['status'] in ('selected', 'feasible_not_selected')   # the map is feasible; whether the policy picked it is a separate fact
            assert (m['status'] == 'selected') == (j['selection']['configuration']['relationships'] == 'map')
            statuses.add(m['status'])
        assert statuses
