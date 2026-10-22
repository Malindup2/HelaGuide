"""Which fact goes to which step (content 3.1): prepared content -> API -> card. Stage and service facts are never attached to steps."""
import copy
import json
import shutil
from pathlib import Path
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from app.guidance import policy
from app.guidance.catalogue import Configuration
from app.guidance.content_v31 import GuidanceContent31, evaluate31, validate_content31
from app.guidance.flavours import FLAVOUR_31
from app.guidance.sources import ProcedureSource
from app.guidance.v31_pipeline import PROFILE_31, compose31, manifest31
from app.v2.api import create_app
from app.v2.identity import WorkspaceRuntime
from app.v2.registration import workspace_registry

C4 = Path(__file__).resolve().parents[2]
ROOT = '/workspace/guidance'
TOKEN = 'attribution-test-capability-' + 'x' * 20
FIXTURES = C4 / 'research' / 'data' / 'guidance' / 'fictional-v31'
FORM, COPY = 'svc:demo_submission:document:form', 'svc:demo_submission:document:copy'
# procedure -> action -> (documents attached at that action, destination). Everything else must be empty.
EXPECTED = {
    'synthetic-practice-v2': {'action:submit_application': ({FORM, COPY}, 'Fictional Submission Desk'), 'action:register_application': (set(), 'Fictional Registration Desk'), 'action:obtain_copy': (set(), 'Fictional Records Desk')},
    'synthetic-parallel-v1': {'action:submit_application': ({FORM, COPY}, None)},
    'synthetic-linear-v1': {'action:collect_pack': ({'svc:demo_pack:document:token'}, None)},
    'synthetic-conditional-v1': {'action:counter_collection': ({'svc:demo_collection:document:reference'}, 'Fictional counter'), 'action:locker_collection': ({'svc:demo_collection:document:reference'}, 'Fictional locker')},
    'official-birth_copy-v3': {}, 'official-nic_amendment-v3': {}, 'official-company_pack-v3': {},
}
BASE = {'navigation': 'overview', 'explanation': 'concise', 'disclosure': 'off', 'relationships': 'none', 'recap': 'off', 'segmentation': 'off'}


@pytest.fixture(scope='module')
def entries():
    return workspace_registry()


@pytest.fixture
def api(entries):
    directory = C4 / 'service' / '.local' / 'prepared-content' / 'v31-tests' / uuid4().hex[:8] / 'v31'
    runtime = WorkspaceRuntime(procedures=entries)
    with TestClient(create_app(runtime=runtime, workspace=True, prepared_content_options={'directory': directory, 'demo_fixtures': True, 'flavour': FLAVOUR_31},
                               guidance_api_options={'research_enabled': True, 'flavour': FLAVOUR_31})) as client:
        yield client, entries
    runtime.close()
    shutil.rmtree(directory.parent, ignore_errors=True)


def ask(client, pid, config=None):
    sid = client.post(ROOT + '/guests').json()['session_id']
    body = {'request_id': uuid4().hex, 'session_id': sid, 'procedure_id': pid, 'capability_token': TOKEN}
    if config:
        body.update(mode='research_preview', configuration=config)
    response = client.post(ROOT + ('/research/previews' if config else '/requests'), json=body)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize('pid', list(EXPECTED))
def test_each_action_receives_exactly_its_documented_facts(api, pid):
    client, entries = api
    j = ask(client, pid)
    graph = entries[pid]['graph']
    stage_of = {a.action_id: a.service_id for a in graph.actions}
    owned = {s.service_id: {s.fee_fact_id, *s.document_fact_ids} for s in graph.stages}
    for action in j['document']['actions']:
        documents, destination = EXPECTED[pid].get(action['id'], (set(), None))
        assert {f['fact_id'] for f in action['facts']} == documents
        assert action['destination'] == destination
        for f in action['facts']:
            assert f['scope'] == 'action' and f['action_id'] == action['id'] and f['fact']['kind'] == 'document'
            assert f['fact_id'] in owned[stage_of[action['id']]]          # the Plan assigns this document to the action's own stage
        assert action['actor'] is None


@pytest.mark.parametrize('pid', list(EXPECTED))
def test_stage_fees_stay_stage_level_and_appear_once(api, pid):
    client, entries = api
    j = ask(client, pid)
    doc = j['document']
    assert all(f['fact']['kind'] != 'fee' for a in doc['actions'] for f in a['facts'])           # negative: no fee on any step
    fees = doc['requirements']['fees']
    assert all(f['scope'] == 'stage' for f in fees)
    assert len({f['fact_id'] for f in fees}) == len(fees) == len(entries[pid]['graph'].stages)  # one entry per stage fee, never repeated
    assert doc['requirements']['total'] is None


@pytest.mark.parametrize('pid', list(EXPECTED))
def test_a_fact_shown_at_a_step_is_not_repeated_in_the_whole_service_list(api, pid):
    client, entries = api
    doc = ask(client, pid)['document']
    attached = {f['fact_id'] for a in doc['actions'] for f in a['facts']}
    listed_stage = {f['fact_id'] for f in doc['requirements']['documents'] if f['scope'] == 'stage'}
    assert not attached & listed_stage
    assert {f.fact_id for f in entries[pid]['graph'].facts if f.kind == 'document'} == attached | listed_stage


def test_step_facts_do_not_depend_on_the_explanation_or_disclosure_choice(api):
    client, _ = api
    seen = set()
    for explanation in ('concise', 'detailed'):
        for disclosure in ('off', 'on'):
            doc = ask(client, 'synthetic-practice-v2', {**BASE, 'explanation': explanation, 'disclosure': disclosure})['document']
            seen.add(json.dumps({a['id']: ([f['fact_id'] for f in a['facts']], a['destination']) for a in doc['actions']}, sort_keys=True))
    assert len(seen) == 1


def test_official_procedures_never_get_action_level_facts_without_a_source_fidelity_review():
    for pid in ('official-birth_copy-v3', 'official-nic_amendment-v3', 'official-company_pack-v3'):
        assert not (FIXTURES / (pid + '.json')).exists()


def source(entries, pid):
    entry = entries[pid]
    return ProcedureSource(graph=entry['graph'], relationships=entry.get('overlay'))


def fixture(pid, part='content'):
    return json.loads((FIXTURES / (pid + '.json')).read_text(encoding='utf-8'))[part]


def test_draft_attachments_and_destinations_are_never_rendered(entries):
    pid = 'synthetic-practice-v2'
    plan = compose31(source(entries, pid), GuidanceContent31.model_validate(fixture(pid, 'draft')), Configuration())
    assert all(a['facts'] == [] and a['destination'] is None for a in plan['actions'])


def test_validator_rejects_a_document_attached_to_another_stage_and_a_fee_of_another_stage(entries):
    pid = 'synthetic-practice-v2'
    src = source(entries, pid)
    draft = fixture(pid, 'draft')
    validate_content31(src, GuidanceContent31.model_validate(draft))   # the unmodified draft is valid, so the failures below are caused by the change
    wrong_stage = copy.deepcopy(draft)
    wrong_stage['attachments'][0]['action_id'] = 'action:prepare_form'   # the form belongs to the submission stage, not the preparation stage
    with pytest.raises(ValueError, match='action fact contradicts source stage ownership'):
        validate_content31(src, GuidanceContent31.model_validate(wrong_stage))
    other_fee = copy.deepcopy(draft)
    other_fee['attachments'][0]['fact_id'] = 'svc:demo_preparation:fee'   # another stage's fee at the submission step
    with pytest.raises(ValueError, match='action fact contradicts source stage ownership'):
        validate_content31(src, GuidanceContent31.model_validate(other_fee))


def test_a_stage_fact_cannot_be_made_visible_at_a_step(entries):
    pid = 'synthetic-practice-v2'
    draft = fixture(pid, 'draft')
    assert all(a['scope'] == 'action' for a in draft['attachments'])
    stage_attachment = copy.deepcopy(draft)
    stage_attachment['attachments'][0].update(scope='stage', stage_id='svc:demo_submission', action_id=None)
    with pytest.raises(ValueError, match='stage/service/route fees cannot become action payments'):
        validate_content31(source(entries, pid), GuidanceContent31.model_validate(stage_attachment))


def test_tampering_with_reviewed_content_is_caught_by_the_review_digest(entries):
    pid = 'synthetic-practice-v2'
    tampered = fixture(pid)
    tampered['attachments'][0]['fact_id'] = 'svc:demo_submission:fee'
    with pytest.raises(ValueError, match='review digest does not match'):
        validate_content31(source(entries, pid), GuidanceContent31.model_validate(tampered))


def test_content_changes_do_not_change_feasibility_features_or_policy_compatibility(entries):
    counts = {'synthetic-practice-v2': 96, 'synthetic-parallel-v1': 96, 'synthetic-conditional-v1': 96, 'synthetic-linear-v1': 48}
    for pid, expected in counts.items():
        content = GuidanceContent31.model_validate(fixture(pid))
        assert sum(c.feasible for c in evaluate31(source(entries, pid), content)) == expected
    assert manifest31() == PROFILE_31.manifest()                       # versions are unchanged by prepared-content wording and facts
    checkpoints = sorted((C4 / 'service' / '.local' / 'pp1-learning' / 'v31-study-20261022-a').glob('seed-23-x0.25-525-n5000.npz'))
    if checkpoints:
        model = policy.Model.restore(checkpoints[0].read_bytes(), PROFILE_31.manifest(exploration=0.25), PROFILE_31)
        assert model.revision == 5000
