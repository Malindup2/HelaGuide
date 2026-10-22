"""LOCAL RESEARCH DEMO acceptance of the cached source-grounded official-procedure wording: ordinary guidance uses it, the unchanged
3.1 policy selects among the content-and-structure-supported configurations, structural limits still bind, and nothing is claimed as externally reviewed."""
import shutil
from pathlib import Path
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from app.guidance.flavours import FLAVOUR_31
from app.v2.api import create_app
from app.v2.identity import WorkspaceRuntime
from app.v2.registration import workspace_registry

C4 = Path(__file__).resolve().parents[2]
ROOT = '/workspace/guidance'
TOKEN = 'accepted-test-capability-' + 'x' * 20
OFFICIAL = ('official-birth_copy-v3', 'official-nic_amendment-v3', 'official-company_pack-v3')
EXPECTED = {'official-birth_copy-v3': 32, 'official-nic_amendment-v3': 32, 'official-company_pack-v3': 64}
BASE = {'navigation': 'overview', 'explanation': 'concise', 'disclosure': 'off', 'relationships': 'none', 'recap': 'off', 'segmentation': 'off'}


def build(accepted):
    tag = uuid4().hex[:8]
    prepared = C4 / 'service' / '.local' / 'prepared-content' / 'v31-tests' / tag / 'v31'
    store = C4 / 'service' / '.local' / 'pp1-learning' / 'v31-tests' / tag
    runtime = WorkspaceRuntime(procedures=workspace_registry())
    options = {'research_enabled': True, 'flavour': FLAVOUR_31, 'policy_options': {'directory': store, 'seed': 5}, **({'demo_accepted': True, 'demo_provisional': True} if accepted else {})}
    client = TestClient(create_app(runtime=runtime, workspace=True, prepared_content_options={'directory': prepared, 'demo_fixtures': True, 'flavour': FLAVOUR_31}, guidance_api_options=options))
    return client, runtime, prepared, store


@pytest.fixture
def accepted():
    client, runtime, prepared, store = build(True)
    with client:
        yield client
    runtime.close()
    shutil.rmtree(prepared.parent, ignore_errors=True); shutil.rmtree(store, ignore_errors=True)


@pytest.fixture
def strict():
    client, runtime, prepared, store = build(False)
    with client:
        yield client
    runtime.close()
    shutil.rmtree(prepared.parent, ignore_errors=True); shutil.rmtree(store, ignore_errors=True)


def personalised(client, pid, familiarity=1, confidence=1):
    service = next(p['service_id'] for p in client.get(ROOT + '/procedures').json() if p['procedure_id'] == pid)
    r = client.post(ROOT + '/profiles', json={'profile_id': 'profile:' + uuid4().hex, 'display_name': 'demo accepted test profile', 'personalization_enabled': True,
                                              'initial_context': {'navigation_capability': confidence, 'familiarity': [{'service_id': service, 'score': familiarity}]}})
    assert r.status_code == 200, r.text
    return r.json()['session']['session_id']


def ask(client, pid, sid=None, config=None, relaxed=False, mode='personalized', expect=200):
    sid = sid or client.post(ROOT + '/guests').json()['session_id']
    body = {'request_id': uuid4().hex, 'session_id': sid, 'procedure_id': pid, 'capability_token': TOKEN}
    if config:
        body.update(mode='research_preview', configuration=config, allow_provisional=relaxed)
    else:
        body['mode'] = mode
    r = client.post(ROOT + ('/research/previews' if config else '/requests'), json=body)
    assert r.status_code == expect, r.text
    return r.json()


@pytest.mark.parametrize('pid', OFFICIAL)
def test_feasible_counts_before_and_after_and_structural_limits(strict, accepted, pid):
    sid = strict.post(ROOT + '/guests').json()['session_id']
    before = strict.get(ROOT + '/procedures/' + pid + '/availability', params={'session_id': sid}).json()
    sid2 = accepted.post(ROOT + '/guests').json()['session_id']
    after = accepted.get(ROOT + '/procedures/' + pid + '/availability', params={'session_id': sid2}).json()
    assert before['feasible_count'] == 4 and before['preparation']['content_state'] == 'source_fallback'
    assert after['feasible_count'] == EXPECTED[pid] < 96 and after['preparation']['content_state'] == 'demo_accepted'
    ok = [c['configuration'] for c in after['candidates'] if c['feasible']]
    assert {c['explanation'] for c in ok} == {'concise', 'detailed'} and {c['disclosure'] for c in ok} == {'on', 'off'}
    assert all(c['relationships'] != 'map' for c in ok)                      # parallel coverage unknown: the map stays structurally unavailable
    assert all(c['segmentation'] == 'off' for c in ok) == (pid != 'official-company_pack-v3')   # phases only where the structure supports them


def test_the_unchanged_strict_server_is_unaffected_by_the_existence_of_this_mode(strict):
    assert strict.get(ROOT + '/status').json()['demo_accepted_content'] == []
    j = ask(strict, 'official-nic_amendment-v3')
    assert j['preparation']['content_state'] == 'source_fallback'


@pytest.mark.parametrize('pid', OFFICIAL)
def test_guest_standard_guidance_uses_the_accepted_wording_and_never_trains(accepted, pid):
    j = ask(accepted, pid, mode='standard')
    assert j['selection']['kind'] == 'standard' and not j['selection']['learning_eligible'] and j['selection']['policy'] is None
    assert j['preparation']['content_state'] == 'demo_accepted'
    assert all(a['wording_status'] == 'provisional' for a in j['document']['actions'])


@pytest.mark.parametrize('pid', OFFICIAL)
def test_personalised_guidance_is_a_genuine_lints_selection_among_the_expanded_set(accepted, pid):
    sid = personalised(accepted, pid, familiarity=1, confidence=1)
    j = ask(accepted, pid, sid)
    sel, prep = j['selection'], j['preparation']
    assert sel['kind'] == 'shared_gaussian_lints' and sel['learning_eligible'] and sel['scoring_status'] == 'executed' and sel['policy']
    assert prep['content_state'] == 'demo_accepted' and prep['content_origin'] == 'demo_mock'
    assert prep['source_review']['independent_government_validation'] is False
    assert 'no external expert' in prep['source_review']['reviewer'].lower() and 'LOCAL RESEARCH DEMO' in prep['source_review']['reviewer']
    assert j['availability']['feasible_count'] == EXPECTED[pid]
    inspection = accepted.get(ROOT + '/journeys/' + j['journey_id'] + '/inspector', headers={'X-C4-Token': TOKEN}).json()
    scored = inspection['sampled_scores']
    assert len(scored) == EXPECTED[pid]                                       # every demo-feasible candidate was scored by the real policy
    assert len(inspection['features']['names']) == 525 and inspection['features']['fingerprint']
    assert inspection['policy']['content_state'] == 'demo_accepted'


def test_the_policy_can_select_compact_and_richer_configurations_for_different_citizens(accepted):
    pid = 'official-company_pack-v3'
    seen = set()
    for familiarity, confidence in ((1, 1), (5, 5), (3, 2), (2, 5), (5, 1)):
        for _ in range(6):
            sid = personalised(accepted, pid, familiarity, confidence)
            c = ask(accepted, pid, sid)['selection']['configuration']
            seen.add(tuple(c.values()))
    assert len(seen) > 1 and all(c[1] in ('concise', 'detailed') for c in seen)


def test_four_d2_d3_combinations_are_independent_and_really_different(accepted):
    pid = 'official-birth_copy-v3'
    views = {}
    for e in ('concise', 'detailed'):
        for d in ('off', 'on'):
            j = ask(accepted, pid, config={**BASE, 'explanation': e, 'disclosure': d})
            assert j['selection']['kind'] == 'research_preview' and not j['selection']['learning_eligible']
            views[e, d] = {a['id']: a for a in j['document']['actions']}
    pay = 'action:birth_pay'
    assert len(views['detailed', 'off'][pay]['essential']) > 1.5 * len(views['concise', 'off'][pay]['essential'])
    assert views['concise', 'on'][pay]['essential'] == views['concise', 'off'][pay]['essential']
    assert views['detailed', 'on'][pay]['essential'] == views['detailed', 'off'][pay]['essential']
    for e in ('concise', 'detailed'):
        off, on = views[e, 'off'][pay], views[e, 'on'][pay]
        assert off['explanation_visible'] and not off['explanation_hidden']
        assert on['explanation_hidden'] and not on['explanation_visible'] and on['disclosure_available']
        assert on['explanation_hidden'] == off['explanation_visible']
    assert [f['fact'] for f in views['concise', 'on'][pay]['facts']] == [f['fact'] for f in views['detailed', 'off'][pay]['facts']]


def test_nic_routes_and_action_facts_remain_attributed_in_ordinary_journeys(accepted):
    j = ask(accepted, 'official-nic_amendment-v3', personalised(accepted, 'official-nic_amendment-v3'))
    doc = j['document']
    assert len(doc['routes']) == 1 and sorted(len(o['action_ids']) for o in doc['routes'][0]['options']) == [1, 2]
    assert not [f for f in doc['facts'] if f['scope'] == 'route']                                    # the fee is paid through the certifying officer, so it sits on the certification steps
    assert {a['id'] for a in doc['actions'] if any(f['fact']['kind'] == 'fee' for f in a['facts'])} == {'action:nic_estate', 'action:nic_gn'}


def test_a_map_is_refused_in_ordinary_journeys_and_only_available_as_an_explicit_relaxed_preview(accepted):
    refused = ask(accepted, 'official-nic_amendment-v3', config={**BASE, 'relationships': 'map'}, expect=422)
    assert refused['detail']['code'] == 'infeasible_configuration'
    shown = ask(accepted, 'official-nic_amendment-v3', config={**BASE, 'relationships': 'map'}, relaxed=True)
    assert shown['document']['relationship_aid']['map'] is not None and shown['selection']['kind'] == 'research_preview'


def test_segmentation_is_structurally_refused_where_no_phase_structure_exists(accepted):
    for pid in ('official-nic_amendment-v3', 'official-birth_copy-v3'):
        assert ask(accepted, pid, config={**BASE, 'segmentation': 'on'}, expect=422)['detail']['code'] == 'infeasible_configuration'
    assert [p['label']['text'] for p in ask(accepted, 'official-company_pack-v3', config={**BASE, 'segmentation': 'on', 'recap': 'on'})['document']['phases']] == ['Prepare the four document sets', 'Submit for the format check']


def test_hard_accessibility_restrictions_are_still_respected(accepted):
    sid = personalised(accepted, 'official-company_pack-v3')
    body = {'request_id': uuid4().hex, 'session_id': sid, 'procedure_id': 'official-company_pack-v3', 'capability_token': TOKEN, 'mode': 'personalized',
            'context': {'constraints': {'no_guided': True, 'no_disclosure': True}}}
    r = accepted.post(ROOT + '/requests', json=body)
    assert r.status_code == 200, r.text
    c = r.json()['selection']['configuration']
    assert c['navigation'] == 'overview' and c['disclosure'] == 'off'


def test_feedback_updates_the_policy_exactly_once_for_the_original_view_and_never_for_guest_or_manual_views(accepted):
    pid = 'official-nic_amendment-v3'
    j = ask(accepted, pid, personalised(accepted, pid))
    H = {'X-C4-Token': TOKEN}
    base = accepted.get(ROOT + '/status').json()['policy']['posterior_revision']
    accepted.post(ROOT + '/journeys/' + j['journey_id'] + '/events', headers=H, json={'event_id': uuid4().hex, 'type': 'view_displayed', 'view_id': j['view_id'], 'action_ids': [j['document']['actions'][0]['id']]})
    rate = {'event_id': uuid4().hex, 'view_id': j['view_id'], 'rating': 'fits', 'reasons': []}
    first = accepted.post(ROOT + '/journeys/' + j['journey_id'] + '/ratings', headers=H, json=rate)
    assert first.status_code == 200, first.text
    assert accepted.get(ROOT + '/status').json()['policy']['posterior_revision'] == base + 1
    assert accepted.post(ROOT + '/journeys/' + j['journey_id'] + '/ratings', headers=H, json=rate).json() == first.json()      # replay is idempotent
    assert accepted.get(ROOT + '/status').json()['policy']['posterior_revision'] == base + 1
    guest = ask(accepted, pid, mode='standard')
    assert accepted.post(ROOT + '/journeys/' + guest['journey_id'] + '/ratings', headers=H, json={**rate, 'event_id': uuid4().hex, 'view_id': guest['view_id']}).status_code == 403
    assert accepted.get(ROOT + '/status').json()['policy']['posterior_revision'] == base + 1
