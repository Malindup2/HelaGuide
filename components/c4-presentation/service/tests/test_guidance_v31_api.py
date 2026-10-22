"""Isolated c4-guidance-content-3.1 runtime: D2 and D3 independence, fallback, compatibility checks. 3.0 is never touched."""
import json
import shutil
from pathlib import Path
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from app.guidance import features, policy
from app.guidance.content_v31 import GuidanceContent31
from app.guidance.flavours import FLAVOUR_30, FLAVOUR_31
from app.guidance.registry import ContentRegistry
from app.guidance.v31_pipeline import ACTION_SCHEMA31, FEATURE_FINGERPRINT31, ContentRegistry31, config_key31, manifest31
from app.v2.api import create_app
from app.v2.identity import WorkspaceRuntime
from app.v2.registration import workspace_registry

C4 = Path(__file__).resolve().parents[2]
ROOT = '/workspace/guidance'
PID = 'synthetic-practice-v2'
TOKEN = 'test-only-capability-not-a-real-user-secret-' + ('x' * 16)
FIXTURE = C4 / 'research' / 'data' / 'guidance' / 'fictional-v31' / (PID + '.json')
BASE = {'navigation': 'overview', 'explanation': 'concise', 'disclosure': 'off', 'relationships': 'none', 'recap': 'off', 'segmentation': 'off'}


@pytest.fixture(scope='module')
def entries():
    return workspace_registry()


@pytest.fixture
def running(entries):
    directory = C4 / 'service' / '.local' / 'prepared-content' / 'v31-tests' / uuid4().hex[:8] / 'v31'
    runtime = WorkspaceRuntime(procedures=entries)
    options = {'directory': directory, 'demo_fixtures': True, 'flavour': FLAVOUR_31}
    with TestClient(create_app(runtime=runtime, workspace=True, prepared_content_options=options,
                               guidance_api_options={'research_enabled': True, 'flavour': FLAVOUR_31})) as client:
        yield client, runtime
    runtime.close()
    shutil.rmtree(directory.parent, ignore_errors=True)


def guest(client):
    return client.post(ROOT + '/guests').json()['session_id']


def request(client, sid, pid=PID, config=None, **changes):
    body = {'request_id': str(uuid4()), 'session_id': sid, 'procedure_id': pid, 'capability_token': TOKEN, **changes}
    url = ROOT + '/requests'
    if config is not None:
        url = ROOT + '/research/previews'
        body.update(mode='research_preview', configuration=config)
    return client.post(url, json=body)


def event(client, j, type, **data):
    return client.post(ROOT + '/journeys/' + j['journey_id'] + '/events', headers={'X-C4-Token': TOKEN}, json={'event_id': str(uuid4()), 'view_id': j['view_id'], 'type': type, **data})


def fixture31():
    return GuidanceContent31.model_validate(json.loads(FIXTURE.read_text(encoding='utf-8'))['content'])


def preview(client, sid, **changes):
    response = request(client, sid, config={**BASE, **changes})
    assert response.status_code == 200, response.text
    return response.json()


def test_status_and_standard_guidance_report_3_1_versions(running):
    client, _ = running
    status = client.get(ROOT + '/status').json()
    assert status['action_schema'] == ACTION_SCHEMA31 and status['content_schema'] == 'c4-guidance-content-3.1'
    assert status['personalized_selection_available'] is False and status['policy'] is None
    j = request(client, guest(client)).json()
    assert j['selection']['kind'] == 'standard' and j['selection']['action_schema'] == ACTION_SCHEMA31
    assert j['preparation']['content_schema'] == 'c4-guidance-content-3.1' and j['document']['content_schema'] == 'c4-guidance-content-3.1'
    assert j['availability']['action_schema'] == ACTION_SCHEMA31 and j['availability']['feasibility_fingerprint']
    assert all(c['id'].startswith(ACTION_SCHEMA31 + ':') for c in j['availability']['candidates'])
    assert not any(j['controls'][k] for k in ('feedback', 'configuration_adjustment'))


def test_four_d2_d3_combinations_differ_exactly_as_intended(running):
    client, _ = running
    sid, content = guest(client), fixture31()
    prepared = {a.id: a for a in content.actions}
    shown = {}
    for explanation in ('concise', 'detailed'):
        for disclosure in ('off', 'on'):
            doc = preview(client, sid, explanation=explanation, disclosure=disclosure)['document']
            shown[(explanation, disclosure)] = {a['id']: a for a in doc['actions']}
    for aid, a in prepared.items():
        cells = {key: value[aid] for key, value in shown.items()}
        for (explanation, disclosure), cell in cells.items():
            primary = (a.concise if explanation == 'concise' else a.detailed).text
            assert cell['essential'] == primary                       # D2 chooses the always-visible primary text
            assert cell['source_wording'] == a.source_wording.text    # exact source stays available, never instead
            assert cell['supplement_role'] == a.supplement.role
            if disclosure == 'off':                                   # D3 OFF: supplement shown plainly, no control
                assert cell['explanation_visible'] == a.supplement.text.text and cell['explanation_hidden'] is None and not cell['disclosure_available']
            else:                                                     # D3 ON: only the supplement is behind the control
                assert cell['explanation_visible'] is None and cell['explanation_hidden'] == a.supplement.text.text and cell['disclosure_available']
            assert a.supplement.text.text not in cell['essential']
        assert len(cells[('concise', 'off')]['essential']) < len(cells[('detailed', 'off')]['essential'])
        assert cells[('concise', 'on')]['essential'] == cells[('concise', 'off')]['essential']
        assert cells[('detailed', 'on')]['essential'] == cells[('detailed', 'off')]['essential']
        assert set(a.concise.claim_ids) <= set(a.detailed.claim_ids)
        assert cells[('concise', 'off')]['conditions'] == cells[('detailed', 'on')]['conditions']


def test_essentials_are_never_only_in_the_hideable_supplement(running):
    client, _ = running
    sid, content = guest(client), fixture31()
    doc = preview(client, sid, explanation='concise', disclosure='on')['document']
    for rendered in doc['actions']:
        action = next(a for a in content.actions if a.id == rendered['id'])
        assert rendered['essential'] and rendered['heading'] and rendered['explanation_visible'] is None
        assert action.supplement.text.claim_ids == () and not any(c.required for c in content.claims if c.id in action.supplement.text.claim_ids)
        for condition in rendered['conditions']:
            assert condition not in (rendered['explanation_hidden'] or '')


def test_disclosure_events_only_for_a_real_supplement(running):
    client, _ = running
    sid = guest(client)
    on = preview(client, sid, disclosure='on')
    first = on['document']['actions'][0]['id']
    assert event(client, on, 'view_displayed', action_ids=[first]).status_code == 200
    assert event(client, on, 'explanation_open', action_id=first).status_code == 200
    off = preview(client, sid, disclosure='off')
    assert event(client, off, 'explanation_open', action_id=first).status_code == 422


def test_rich_configuration_renders_phases_map_recap_and_guided_navigation(running):
    client, _ = running
    j = preview(guest_client := client, guest(client), navigation='guided', explanation='detailed', disclosure='on', relationships='map', recap='on', segmentation='on')
    doc = j['document']
    assert doc['phases'] and doc['relationship_aid']['map'] and doc['navigation']['mode'] == 'guided' and doc['navigation']['numbering_enabled']
    assert j['interaction']['navigation']['browsing_count'] >= 2 and guest_client is client


def test_hard_accessibility_restriction_blocks_disclosure_but_not_standard_guidance(running):
    client, _ = running
    sid = guest(client)
    blocked = request(client, sid, config={**BASE, 'disclosure': 'on'}, context={'constraints': {'no_disclosure': True}})
    assert blocked.status_code == 422 and blocked.json()['detail']['code'] == 'infeasible_configuration'
    assert request(client, sid, context={'constraints': {'no_disclosure': True}}).status_code == 200


def test_official_procedures_stay_on_source_fallback_with_only_the_safe_configurations(running):
    client, _ = running
    sid = guest(client)
    for pid in ('official-birth_copy-v3', 'official-nic_amendment-v3', 'official-company_pack-v3'):
        availability = client.get(ROOT + '/procedures/' + pid + '/availability', params={'session_id': sid}).json()
        assert availability['feasible_count'] == 4 and availability['action_schema'] == ACTION_SCHEMA31
        j = request(client, sid, pid).json()
        assert j['preparation']['content_state'] == 'source_fallback' and j['document']['content_fingerprint'] is None
        assert all(a['wording_status'] == 'source_fallback' and a['source_wording'] is None and a['explanation_visible'] is None for a in j['document']['actions'])
        for dimension, value in (('explanation', 'detailed'), ('disclosure', 'on'), ('recap', 'on'), ('segmentation', 'on')):
            assert request(client, sid, pid, {**BASE, dimension: value}).status_code == 422


def test_fictional_3_1_counts_after_internal_review(running):
    client, _ = running
    sid = guest(client)
    expected = {'synthetic-linear-v1': 48, 'synthetic-conditional-v1': 96, 'synthetic-parallel-v1': 96, PID: 96}
    for pid, count in expected.items():
        availability = client.get(ROOT + '/procedures/' + pid + '/availability', params={'session_id': sid}).json()
        assert availability['feasible_count'] == count
        for e in ('concise', 'detailed'):
            for d in ('off', 'on'):
                assert any(c['feasible'] and c['configuration']['explanation'] == e and c['configuration']['disclosure'] == d for c in availability['candidates'])


def test_personalized_selection_is_unavailable_and_never_reuses_a_3_0_policy(running):
    client, runtime = running
    result = request(client, guest(client), mode='personalized')
    assert result.status_code == 503 and result.json()['detail']['code'] == 'revised_policy_unavailable'
    assert 'content-3.1' in result.json()['detail']['message'] and result.json()['detail']['action_schema'] == ACTION_SCHEMA31
    assert not runtime.state['decisions']


def test_policy_options_are_refused_for_3_1_and_flavours_cannot_be_mixed(entries, tmp_path):
    directory = C4 / 'service' / '.local' / 'prepared-content' / 'v31-tests' / uuid4().hex[:8] / 'v31'
    runtime = WorkspaceRuntime(procedures=entries)
    try:
        with pytest.raises(ValueError, match='no PP1 policy is compatible'):
            with TestClient(create_app(runtime=runtime, workspace=True, prepared_content_options={'directory': directory, 'demo_fixtures': True, 'flavour': FLAVOUR_31},
                                       guidance_api_options={'flavour': FLAVOUR_31, 'policy_options': {'directory': str(tmp_path)}})):
                pass
        with pytest.raises(ValueError, match='same content schema'):
            with TestClient(create_app(runtime=runtime, workspace=True, prepared_content_options={'directory': directory, 'demo_fixtures': True, 'flavour': FLAVOUR_31},
                                       guidance_api_options={'flavour': FLAVOUR_30})):
                pass
    finally:
        runtime.close()
        shutil.rmtree(directory.parent, ignore_errors=True)


def test_registries_refuse_each_other_and_3_1_needs_its_own_directory():
    base = C4 / 'service' / '.local' / 'prepared-content' / 'v31-tests' / uuid4().hex[:8]
    try:
        three = base / 'v30'
        ContentRegistry(three)
        with pytest.raises(ValueError, match='v31 directory'):
            ContentRegistry31(three)
        both = base / 'v31'
        ContentRegistry31(both)
        with pytest.raises(ValueError, match='incompatible content registry'):
            ContentRegistry(both)
        mixed = base / 'prepared-content' / 'v31'
        mixed.mkdir(parents=True)
        shutil.copy(three / 'registry.sqlite3', mixed / 'registry.sqlite3')
        with pytest.raises(ValueError, match='incompatible content registry'):
            ContentRegistry31(mixed)
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_manifest_versions_are_enforced_not_bypassed():
    old, new = policy.manifest(), manifest31()
    assert [k for k in old if old[k] != new[k]] == ['action', 'features', 'feature_fingerprint', 'content']
    assert old['dimension'] == new['dimension'] == 525 and old['variant'] == new['variant']
    assert FEATURE_FINGERPRINT31 != features.FINGERPRINT
    blob = policy.Model().state()
    with pytest.raises(ValueError, match='incompatible PP1 checkpoint manifest'):
        policy.Model.restore(blob, expected=new)
    assert policy.Model.restore(blob, expected=old).revision == 0
    sample = policy.Model()
    assert config_key31(next(iter(__import__('app.guidance.catalogue', fromlist=['CATALOGUE']).CATALOGUE))).startswith(ACTION_SCHEMA31)
    assert sample.manifest == old


def test_default_runtime_is_still_3_0(entries):
    assert FLAVOUR_30.content_schema == 'c4-guidance-content-3.0' and FLAVOUR_30.action_schema == 'c4-scaffolds-v3.0' and FLAVOUR_30.supports_policy
    assert not FLAVOUR_31.supports_policy and FLAVOUR_31.policy_manifest()['content'] == 'c4-guidance-content-3.1'
