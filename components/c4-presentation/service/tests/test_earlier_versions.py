"""The three earlier official procedures: improved demo wording over UNCHANGED graphs, strict feasibility, honest map restriction."""
import json
import re
from pathlib import Path
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from app.guidance import provisional
from app.guidance.flavours import FLAVOUR_31
from app.guidance.sources import ProcedureSource
from app.host.application import create_app
from app.host.identity import WorkspaceRuntime
from app.procedures.registration import workspace_registry

C4 = Path(__file__).resolve().parents[2]
ROOT = '/workspace/guidance'
TOKEN = 'earlier-versions-capability-' + 'x' * 20
EARLIER = {'official-birth_copy-v3': 32, 'official-nic_amendment-v3': 32, 'official-company_pack-v3': 64}
BASE = {'navigation': 'overview', 'explanation': 'concise', 'disclosure': 'off', 'relationships': 'none', 'recap': 'off', 'segmentation': 'off'}
FILLER = re.compile(r'this example|snapshot|not supplied|no separate fee|another step in the same route|fictional', re.I)


@pytest.fixture
def client(tmp_path):
    entries = workspace_registry()
    options = {'research_enabled': True, 'flavour': FLAVOUR_31, 'demo_accepted': True, 'demo_provisional': True}
    app = create_app(path=tmp_path / 'v2' / 'workspace' / 'api.sqlite3', workspace=True, runtime_class=lambda path, **kw: WorkspaceRuntime(path, procedures=entries, **kw),
                     prepared_content_options={'directory': tmp_path / 'prepared-content' / 'v31', 'demo_fixtures': True, 'flavour': FLAVOUR_31}, guidance_api_options=options)
    with TestClient(app) as c:
        yield c


def preview(client, pid, **change):
    sid = client.post(ROOT + '/guests').json()['session_id']
    r = client.post(ROOT + '/research/previews', json={'request_id': uuid4().hex, 'session_id': sid, 'procedure_id': pid, 'capability_token': TOKEN, 'mode': 'research_preview',
                                                       'configuration': {**BASE, **change}})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize('pid', EARLIER)
def test_graphs_are_unchanged_so_history_and_replay_stay_valid(pid):
    entries = workspace_registry()
    now = ProcedureSource(graph=entries[pid]['graph'], relationships=entries[pid].get('overlay')).graph_fingerprint
    for name in (pid + '.json', 'archive/' + pid + '.demo-accepted-v1.json'):
        content = json.loads((provisional.PROVISIONAL_DIR / name).read_text(encoding='utf-8'))['content']
        assert content['source_graph_fingerprint'] == now                              # the earlier and the improved wording describe the very same graph
    assert json.loads((provisional.PROVISIONAL_DIR / (pid + '.json')).read_text(encoding='utf-8'))['content']['content_version'] == 'demo-accepted-v3-2'
    assert json.loads((provisional.PROVISIONAL_DIR / 'archive' / (pid + '.demo-accepted-v1.json')).read_text(encoding='utf-8'))['content']['content_version'] != 'demo-accepted-v3-2'


@pytest.mark.parametrize('pid,count', EARLIER.items())
def test_strict_feasibility_is_unchanged_and_the_map_is_refused_for_incomplete_parallel_coverage(client, pid, count):
    sid = client.post(ROOT + '/guests').json()['session_id']
    av = client.get(ROOT + '/procedures/' + pid + '/availability', params={'session_id': sid}).json()
    assert av['feasible_count'] == count
    assert all(c['configuration']['relationships'] != 'map' for c in av['candidates'] if c['feasible'])
    assert {r for c in av['candidates'] for r in c['reasons'] if 'map' in r} == {'relationships:incomplete_map_or_accessibility'}


@pytest.mark.parametrize('pid', EARLIER)
def test_concise_and_detailed_are_meaningfully_different_without_filler(client, pid):
    concise, detailed = preview(client, pid), preview(client, pid, explanation='detailed')
    for a, b in zip(concise['document']['actions'], detailed['document']['actions']):
        assert len(b['essential']) > len(a['essential']) and a['essential'] != b['essential']
        assert a['explanation_visible'] and not FILLER.search(a['essential'] + ' ' + a['explanation_visible'] + ' ' + b['essential'] + ' ' + a['heading'])
    on, off = preview(client, pid, disclosure='on'), concise
    for a, b in zip(on['document']['actions'], off['document']['actions']):
        assert a['essential'] == b['essential'] and a['explanation_hidden'] == b['explanation_visible'] and not a['explanation_visible']


def test_nic_shows_its_verified_branches_with_the_fee_on_the_certification_steps_only(client):
    j = preview(client, 'official-nic_amendment-v3', relationships='inline', recap='on')
    doc = j['document']
    assert len(doc['routes']) == 1 and doc['routes'][0]['selection'] == 'XOR'
    sizes = {o['option_id']: len(o['action_ids']) for o in doc['routes'][0]['options']}
    assert sorted(sizes.values()) == [1, 2]
    by = {a['id']: a for a in doc['actions']}
    fee_steps = {i for i, a in by.items() if any(f['fact']['kind'] == 'fee' for f in a['facts'])}
    assert fee_steps == {'action:nic_estate', 'action:nic_gn'}
    assert all(f['role'] == 'pay' and 'adds LKR 120' in f['qualification'] for i in fee_steps for f in by[i]['facts'] if f['fact']['kind'] == 'fee')
    assert not [f for f in doc['facts'] if f['scope'] == 'route']                          # nothing is paid at the route question
    cues = doc['relationship_aid']['inline_by_action']['action:nic_ds']
    assert any(c['text'].startswith('Before this:') for c in cues)
    assert all(a['wording_status'] == 'provisional' for a in doc['actions'])


def test_company_keeps_its_phases_and_birth_has_no_phase_structure(client):
    assert [p['label']['text'] for p in preview(client, 'official-company_pack-v3', segmentation='on')['document']['phases']] == ['Prepare the four document sets', 'Submit for the format check']
    sid = client.post(ROOT + '/guests').json()['session_id']
    refused = client.post(ROOT + '/research/previews', json={'request_id': uuid4().hex, 'session_id': sid, 'procedure_id': 'official-birth_copy-v3', 'capability_token': TOKEN,
                                                             'mode': 'research_preview', 'configuration': {**BASE, 'segmentation': 'on'}})
    assert refused.status_code == 422
