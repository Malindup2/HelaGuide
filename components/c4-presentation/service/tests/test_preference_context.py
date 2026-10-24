"""Citizen preferences reach the PP1 context as SOFT, optional values; unanswered stays unknown; accessibility stays a HARD restriction."""
from pathlib import Path
from uuid import uuid4
from fastapi.testclient import TestClient
from app.guidance.flavours import FLAVOUR_31
from app.host.application import create_app
from app.host.identity import WorkspaceRuntime
from app.procedures.registration import workspace_registry

C4 = Path(__file__).resolve().parents[2]
ROOT = '/workspace/guidance'
PID = 'official-nic_amendment-v4'
TOKEN = 'preference-test-capability-' + 'x' * 20


def build(tmp: Path):
    entries = workspace_registry()
    options = {'research_enabled': True, 'flavour': FLAVOUR_31, 'demo_accepted': True, 'demo_provisional': True,
               'policy_options': {'directory': C4 / 'service' / '.local' / 'pp1-learning' / 'v31-tests' / ('pref-' + uuid4().hex[:8]), 'seed': 12}}
    return {'path': tmp / 'v2' / 'workspace' / 'api.sqlite3', 'workspace': True, 'runtime_class': lambda path, **kw: WorkspaceRuntime(path, procedures=entries, **kw),
            'prepared_content_options': {'directory': tmp / 'prepared-content' / 'v31', 'demo_fixtures': True, 'flavour': FLAVOUR_31}, 'guidance_api_options': options}


def profile(client, *, layout=None, allow_guided=True):
    service = next(p['service_id'] for p in client.get(ROOT + '/procedures').json() if p['procedure_id'] == PID)
    body = {'profile_id': 'profile:' + uuid4().hex, 'display_name': 'preference test', 'personalization_enabled': True,
            'initial_context': {'navigation_capability': 2, 'familiarity': [{'service_id': service, 'score': 2}],
                                'preferences': {'presentation_mode': layout} if layout else {},
                                'accessibility': {'allow_relationship_visuals': True, 'allow_collapsed_content': True, 'allow_guided_navigation': allow_guided}}}
    r = client.post(ROOT + '/profiles', json=body)
    assert r.status_code == 200, r.text
    return r.json()['session']['session_id']


def context(client, sid):
    return client.get(ROOT + '/context/' + sid, params={'procedure_id': PID}).json()


def ask(client, sid):
    r = client.post(ROOT + '/requests', json={'request_id': uuid4().hex, 'session_id': sid, 'procedure_id': PID, 'capability_token': TOKEN, 'mode': 'personalized'})
    assert r.status_code == 200, r.text
    return r.json()


def active_preference_features(client, journey):
    f = client.get(ROOT + '/journeys/' + journey['journey_id'] + '/inspector', headers={'X-C4-Token': TOKEN}).json()['features']
    return sorted({n.split('*')[0] for n, v in zip(f['names'], f['selected']) if n.startswith('preference.') and v})


def test_a_saved_layout_preference_reaches_the_effective_context_and_the_encoder(tmp_path):
    with TestClient(create_app(**build(tmp_path))) as client:
        sid = profile(client, layout='GUIDED')
        ctx = context(client, sid)
        assert ctx['preferences'] == {'navigation': 'guided'}
        assert ctx['sources']['preferences'] == 'saved_layout_preference_and_explicit_revised_settings'
        assert 'navigation' not in ctx['legacy']['preferences_not_imported']
        assert active_preference_features(client, ask(client, sid)) == ['preference.navigation.guided']


def test_an_unanswered_preference_stays_unknown_and_is_not_encoded(tmp_path):
    with TestClient(create_app(**build(tmp_path))) as client:
        sid = profile(client)
        assert context(client, sid)['preferences'] == {}
        assert active_preference_features(client, ask(client, sid)) == []


def test_other_dimensions_use_the_existing_context_patch_and_an_explicit_value_beats_the_saved_layout(tmp_path):
    with TestClient(create_app(**build(tmp_path))) as client:
        sid = profile(client, layout='GUIDED')
        revision = context(client, sid)['revision']
        patch = client.patch(ROOT + '/context/' + sid, json={'request_id': uuid4().hex, 'expected_revision': revision,
                                                              'preferences': {'navigation': 'overview', 'explanation': 'detailed', 'recap': 'on'}})
        assert patch.status_code == 200, patch.text
        assert context(client, sid)['preferences'] == {'navigation': 'overview', 'explanation': 'detailed', 'recap': 'on'}
        assert active_preference_features(client, ask(client, sid)) == ['preference.explanation.detailed', 'preference.navigation.overview', 'preference.recap.on']


def test_a_soft_preference_never_changes_what_is_feasible_but_a_hard_restriction_does(tmp_path):
    with TestClient(create_app(**build(tmp_path))) as client:
        plain, wants_guided, blocked = profile(client), profile(client, layout='GUIDED'), profile(client, layout='GUIDED', allow_guided=False)
        counts = {}
        for name, sid in (('plain', plain), ('guided', wants_guided), ('blocked', blocked)):
            j = ask(client, sid)
            counts[name] = (j['availability']['feasible_count'], {c['configuration']['navigation'] for c in j['availability']['candidates'] if c['feasible']})
        assert counts['plain'] == counts['guided'] and counts['guided'][1] == {'overview', 'guided'}      # a preference removes nothing
        assert counts['blocked'][1] == {'overview'} and counts['blocked'][0] < counts['plain'][0]          # the restriction does, even though guided is preferred
        for _ in range(8):
            assert ask(client, blocked)['selection']['configuration']['navigation'] == 'overview'


def test_saving_revised_preferences_without_a_layout_clears_the_imported_layout(tmp_path):
    with TestClient(create_app(**build(tmp_path))) as client:
        sid = profile(client, layout='GUIDED')
        revision = context(client, sid)['revision']
        assert client.patch(ROOT + '/context/' + sid, json={'request_id': uuid4().hex, 'expected_revision': revision, 'preferences': {'explanation': 'concise'}}).status_code == 200
        assert context(client, sid)['preferences'] == {'explanation': 'concise'}
