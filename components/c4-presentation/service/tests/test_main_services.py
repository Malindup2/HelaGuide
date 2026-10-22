"""The three main demonstration services (birth certificate copy v4, NIC amendment v4, TIN registration): source-attached planner graphs,
structurally different, rendered through the existing guidance pipeline, selected by the unchanged trained-compatible policy."""
import json
import shutil
from pathlib import Path
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from app.guidance import provisional
from app.guidance.content_v31 import GuidanceContent31, evaluate31
from app.guidance.flavours import FLAVOUR_31
from app.guidance.sources import ProcedureSource
from app.v2.api import create_app
from app.v2.identity import WorkspaceRuntime
from app.v2.registration import workspace_registry

C4 = Path(__file__).resolve().parents[2]
ROOT = '/workspace/guidance'
TOKEN = 'main-services-test-capability-' + 'x' * 20
MAIN = ('official-birth_copy-v4', 'official-nic_amendment-v4', 'official-tin_registration-v1')
EARLIER = ('official-birth_copy-v3', 'official-nic_amendment-v3', 'official-company_pack-v3')


@pytest.fixture(scope='module')
def entries():
    return workspace_registry()


def source(entries, pid):
    return ProcedureSource(graph=entries[pid]['graph'], relationships=entries[pid].get('overlay'))


def test_the_three_services_have_different_real_structures(entries):
    shape = {}
    for pid in MAIN:
        g = entries[pid]['graph']
        shape[pid] = {'actions': len(g.actions), 'edges': len(g.action_prerequisites), 'branches': [len(b.options) for b in g.branch_groups], 'selection': {b.selection for b in g.branch_groups},
                      'stages': len(g.stages), 'parallel': len(g.parallel_groups), 'completeness': entries[pid]['document']['completeness']['parallel_groups']}
    birth, nic, tin = (shape[p] for p in MAIN)
    assert birth['branches'] == [2] and nic['branches'] == [2] and tin['branches'] == [3]            # fee condition, certifying route, applicant category
    assert (birth['actions'], birth['edges']) == (6, 5) and (nic['actions'], nic['edges']) == (7, 5) and (tin['actions'], tin['edges']) == (6, 3)
    assert all(s['parallel'] == 0 and s['completeness'] == 'unknown' and s['selection'] == {'XOR'} and s['stages'] == 1 for s in shape.values())   # nothing invented to enable a map


def test_every_fact_is_attached_to_the_action_the_source_text_gives_it(entries):
    nic = entries['official-nic_amendment-v4']['graph']
    for pid in MAIN:
        content = GuidanceContent31.model_validate(json.loads((provisional.PROVISIONAL_DIR / (pid + '.json')).read_text(encoding='utf-8'))['content'])
        report = provisional.check(source(entries, pid), content)
        assert report['passed'] and report['structural'] == 'passed' and content.origin == 'demo_mock' and content.review is None
        by_action = {a.id: [x for x in content.attachments if x.action_id == a.id] for a in content.actions}
        for a in content.actions:
            assert all(x.scope == 'action' for x in by_action[a.id])
    fees = {x.action_id for x in GuidanceContent31.model_validate(json.loads((provisional.PROVISIONAL_DIR / 'official-nic_amendment-v4.json').read_text(encoding='utf-8'))['content']).attachments if x.fact_id.endswith(':fee')}
    assert fees == {'action:estate_certify', 'action:gn_certify'}              # paid through the certifying officer, never at the countersignature or the route question
    assert len(nic.facts) == 12


def test_conditional_documents_stay_with_their_applicant_category(entries):
    content = GuidanceContent31.model_validate(json.loads((provisional.PROVISIONAL_DIR / 'official-tin_registration-v1.json').read_text(encoding='utf-8'))['content'])
    docs = {a.id: {x.fact_id for x in content.attachments if x.action_id == a.id} for a in content.actions}
    sets = [docs['action:individual_docs'], docs['action:partnership_docs'], docs['action:company_docs']]
    assert not (sets[0] & sets[1]) and not (sets[0] & sets[2]) and not (sets[1] & sets[2])
    conditional = {x.fact_id: x.qualification.text for x in content.attachments if x.qualification and x.action_id == 'action:company_docs'}
    assert len(conditional) == 3 and all(t.startswith('Only') for t in conditional.values())


@pytest.mark.parametrize('pid', MAIN)
def test_feasible_set_before_and_after_demo_acceptance_and_structural_limits(entries, pid):
    src = source(entries, pid)
    content = GuidanceContent31.model_validate(json.loads((provisional.PROVISIONAL_DIR / (pid + '.json')).read_text(encoding='utf-8'))['content'])
    assert sum(c.feasible for c in evaluate31(src, None)) == 4
    ok = [c.configuration for c in evaluate31(src, content, assume_reviewed=True) if c.feasible]
    assert len(ok) == 64
    assert {c.relationships for c in ok} == {'none', 'inline'}                # parallel coverage unknown: no map
    assert {c.segmentation for c in ok} == {'off', 'on'}                      # phases are supported by the verified prerequisites
    assert {c.explanation for c in ok} == {'concise', 'detailed'} and {c.disclosure for c in ok} == {'off', 'on'}


def build(tmp, accepted=True):
    entries = workspace_registry()
    options = {'research_enabled': True, 'flavour': FLAVOUR_31, 'demo_accepted': accepted, 'demo_provisional': accepted,
               'policy_options': {'directory': C4 / 'service' / '.local' / 'pp1-learning' / 'v31-tests' / ('main-' + uuid4().hex[:8]), 'seed': 8}}
    return {'path': tmp / 'v2' / 'workspace' / 'api.sqlite3', 'workspace': True, 'runtime_class': lambda path, **kw: WorkspaceRuntime(path, procedures=entries, **kw),
            'prepared_content_options': {'directory': tmp / 'prepared-content' / 'v31', 'demo_fixtures': True, 'flavour': FLAVOUR_31}, 'guidance_api_options': options}


def profile(client, pid, fam, conf):
    service = next(p['service_id'] for p in client.get(ROOT + '/procedures').json() if p['procedure_id'] == pid)
    r = client.post(ROOT + '/profiles', json={'profile_id': 'profile:' + uuid4().hex, 'display_name': 'main services test', 'personalization_enabled': True,
                                              'initial_context': {'navigation_capability': conf, 'familiarity': [{'service_id': service, 'score': fam}]}})
    assert r.status_code == 200, r.text
    return r.json()['session']['session_id']


def test_clean_and_repeat_startup_and_genuine_policy_selection_from_the_expanded_set(tmp_path):
    kwargs = build(tmp_path)
    seen = {}
    with TestClient(create_app(**kwargs)) as client:                         # clean registry
        for pid in MAIN:
            sid = profile(client, pid, 2, 2)
            j = client.post(ROOT + '/requests', json={'request_id': uuid4().hex, 'session_id': sid, 'procedure_id': pid, 'capability_token': TOKEN, 'mode': 'personalized'}).json()
            assert j['selection']['kind'] == 'shared_gaussian_lints' and j['selection']['scoring_status'] == 'executed' and j['selection']['learning_eligible']
            assert j['preparation']['content_state'] == 'demo_accepted' and j['availability']['feasible_count'] == 64
            ins = client.get(ROOT + '/journeys/' + j['journey_id'] + '/inspector', headers={'X-C4-Token': TOKEN}).json()
            assert len(ins['sampled_scores']) == 64 and len(ins['features']['names']) == 525
            seen[pid] = j['selection']['configuration']
        guest = client.post(ROOT + '/guests').json()['session_id']
        g = client.post(ROOT + '/requests', json={'request_id': uuid4().hex, 'session_id': guest, 'procedure_id': MAIN[1], 'capability_token': TOKEN, 'mode': 'standard'}).json()
        assert g['selection']['kind'] == 'standard' and not g['selection']['learning_eligible'] and g['selection']['policy'] is None
    with TestClient(create_app(**kwargs)) as client:                         # repeat startup against the same registry
        status = client.get(ROOT + '/status').json()
        assert set(MAIN) <= set(status['demo_accepted_content'])
        assert len(client.get(ROOT + '/procedures').json()) >= 9


def test_the_earlier_versions_are_still_registered_and_unchanged(entries):
    assert set(EARLIER) <= set(entries)
    for pid in EARLIER:
        assert entries[pid]['graph'].plan_id == pid
