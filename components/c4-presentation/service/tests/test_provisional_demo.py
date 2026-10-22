"""DEMO-ONLY provisional wording for official procedures: automatic checks, honest labels, and strict isolation from standard and LinTS journeys."""
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
TOKEN = 'provisional-test-capability-' + 'x' * 20
OFFICIAL = ('official-birth_copy-v3', 'official-nic_amendment-v3', 'official-company_pack-v3')
BASE = {'navigation': 'overview', 'explanation': 'concise', 'disclosure': 'off', 'relationships': 'none', 'recap': 'off', 'segmentation': 'off'}


@pytest.fixture(scope='module')
def entries():
    return workspace_registry()


def source(entries, pid):
    return ProcedureSource(graph=entries[pid]['graph'], relationships=entries[pid].get('overlay'))


def packet(pid):
    return json.loads((provisional.PROVISIONAL_DIR / (pid + '.json')).read_text(encoding='utf-8'))


def server(entries, demo):
    directory = C4 / 'service' / '.local' / 'prepared-content' / 'v31-tests' / uuid4().hex[:8] / 'v31'
    runtime = WorkspaceRuntime(procedures=entries)
    options = {'research_enabled': True, 'flavour': FLAVOUR_31, **({'demo_provisional': True} if demo else {})}
    client = TestClient(create_app(runtime=runtime, workspace=True, prepared_content_options={'directory': directory, 'demo_fixtures': True, 'flavour': FLAVOUR_31}, guidance_api_options=options))
    return client, runtime, directory


@pytest.fixture
def demo(entries):
    client, runtime, directory = server(entries, True)
    with client:
        yield client
    runtime.close()
    shutil.rmtree(directory.parent, ignore_errors=True)


@pytest.fixture
def strict(entries):
    client, runtime, directory = server(entries, False)
    with client:
        yield client
    runtime.close()
    shutil.rmtree(directory.parent, ignore_errors=True)


def ask(client, pid, config=None, provisional_flag=False, expect=200):
    sid = client.post(ROOT + '/guests').json()['session_id']
    body = {'request_id': uuid4().hex, 'session_id': sid, 'procedure_id': pid, 'capability_token': TOKEN}
    if config:
        body.update(mode='research_preview', configuration=config, allow_provisional=provisional_flag)
    response = client.post(ROOT + ('/research/previews' if config else '/requests'), json=body)
    assert response.status_code == expect, response.text
    return response.json(), sid


@pytest.mark.parametrize('pid', OFFICIAL)
def test_provisional_files_pass_the_automatic_checks_and_carry_no_review_claim(entries, pid):
    p = packet(pid)
    content = GuidanceContent31.model_validate(p['content'])
    report = provisional.check(source(entries, pid), content)
    assert report['passed'] and report['structural'] == 'passed'
    assert content.origin == 'demo_mock' and content.review is None
    assert all(t.status != 'reviewed' for a in content.actions for t in (a.heading, a.concise, a.detailed, a.recap) if t)
    assert 'No human' in p['label'] and 'review' in p['provenance'].lower()


def test_the_checks_catch_an_invented_amount_an_invented_name_a_payment_at_the_wrong_step_and_a_free_claim(entries):
    pid = 'official-company_pack-v3'
    src = source(entries, pid)
    good = packet(pid)['content']

    def with_text(action, field, text):
        c = json.loads(json.dumps(good))
        next(a for a in c['actions'] if a['id'] == action)[field]['text'] = text
        return GuidanceContent31.model_validate(c)

    assert any('LKR 999'.split()[1] in i for i in provisional.grounding_issues(src, with_text('action:company_form', 'detailed', 'Prepare Form 1 and note the LKR 999 charge. It is fuller than the short instruction.')))
    assert any('Zebra' in i for i in provisional.grounding_issues(src, with_text('action:company_articles', 'concise', 'Prepare the Articles with the Zebra Authority.')))
    assert any('payment' in i for i in provisional.contradiction_issues(src, with_text('action:company_form', 'concise', 'Pay the Form 1 charge now at the counter.')))
    assert any('no fee' in i for i in provisional.contradiction_issues(src, with_text('action:company_directors', 'detailed', 'Prepare Form 18 director consent documentation. This step is free of charge for you.')))
    assert provisional.grounding_issues(src, GuidanceContent31.model_validate(good)) == []


def test_without_the_demo_mode_nothing_provisional_is_offered_or_accepted(strict):
    status = strict.get(ROOT + '/status').json()
    assert status['demo_provisional_content'] == []
    refused, _ = ask(strict, 'official-nic_amendment-v3', {**BASE, 'relationships': 'map'}, True, expect=422)
    assert refused['detail']['code'] == 'provisional_demo_disabled'
    sid = strict.post(ROOT + '/guests').json()['session_id']
    assert strict.get(ROOT + '/procedures/official-nic_amendment-v3/availability', params={'session_id': sid, 'provisional': 'true'}).status_code == 422


def test_standard_guidance_and_the_strict_feasible_set_are_unchanged_even_when_the_demo_mode_is_on(demo):
    for pid in OFFICIAL:
        j, sid = ask(demo, pid)
        assert j['preparation']['content_state'] == 'source_fallback' and j['selection']['kind'] == 'standard'
        assert j['availability']['feasible_count'] == 4
        assert all(a['wording_status'] == 'source_fallback' and a['facts'] == [] and a['destination'] is None for a in j['document']['actions'])
        strict_availability = demo.get(ROOT + '/procedures/' + pid + '/availability', params={'session_id': sid}).json()
        assert strict_availability['feasible_count'] == 4 and strict_availability['preparation']['content_state'] == 'source_fallback'


def test_provisional_previews_are_labelled_and_never_claim_a_review(demo):
    j, sid = ask(demo, 'official-nic_amendment-v3', {**BASE, 'disclosure': 'on', 'relationships': 'inline'}, True)
    prep = j['preparation']
    assert prep['content_state'] == 'provisional_demo' and prep['content_origin'] == 'demo_mock' and prep['review_kind'] == 'provisional_demo_automatic_checks_only'
    assert prep['source_review']['independent_government_validation'] is False and 'No human review' in prep['source_review']['reviewer']
    assert j['selection']['kind'] == 'research_preview' and not j['selection']['learning_eligible'] and not j['selection']['policy']
    assert 'provisional wording' in j['selection']['label']
    assert all(a['wording_status'] == 'provisional' for a in j['document']['actions'])
    assert j['availability']['feasible_count'] > 4
    assert demo.get(ROOT + '/status').json()['demo_provisional_content'] == sorted(OFFICIAL + ('official-birth_copy-v4', 'official-nic_amendment-v4', 'official-tin_registration-v1'))


def test_provisional_wording_is_never_stored_in_the_strict_registry(demo, entries):
    api = demo.app.state.guidance_api
    for pid in OFFICIAL:
        assert api.prepared.registry.get(source(entries, pid), 'en') is None
        assert pid in api.provisional


def test_nic_provisional_steps_routes_and_route_fee_are_exact(demo, entries):
    graph = entries['official-nic_amendment-v3']['graph']
    j, _ = ask(demo, 'official-nic_amendment-v3', {**BASE, 'relationships': 'map'}, True)
    doc = j['document']
    assert {a['id'] for a in doc['actions']} == {a.action_id for a in graph.actions} and len(doc['routes']) == 1
    options = {o['option_id']: o['action_ids'] for o in doc['routes'][0]['options']}
    assert sorted(len(v) for v in options.values()) == [1, 2]                      # estate: one step; non-estate: two steps
    assert doc['relationship_aid']['map'] is not None
    assert sorted((e['source_id'], e['target_id']) for e in doc['edges']) == sorted((e.source_id, e.target_id) for e in graph.action_prerequisites)   # no invented dependency
    route_fees = [f for f in doc['facts'] if f['scope'] == 'route']
    assert len(route_fees) == 1 and route_fees[0]['fact']['kind'] == 'fee' and 'LKR 120' in route_fees[0]['qualification']
    assert all(f['fact']['kind'] != 'fee' for a in doc['actions'] for f in a['facts'])   # the fee belongs to the choice of routes, not to a step


def test_company_fee_is_shown_as_a_charge_with_its_qualification_not_as_a_payment(demo):
    j, _ = ask(demo, 'official-company_pack-v3', {**BASE, 'explanation': 'detailed'}, True)
    form = next(a for a in j['document']['actions'] if a['id'] == 'action:company_form')
    fee = next(f for f in form['facts'] if f['fact']['kind'] == 'fee')
    assert fee['role'] == 'charge' and 'Payment is outside this step' in fee['qualification']
    assert all(f['role'] != 'pay' for a in j['document']['actions'] for f in a['facts'])


def test_birth_copy_fee_is_attached_to_the_payment_step_only(demo):
    j, _ = ask(demo, 'official-birth_copy-v3', BASE, True)
    by = {a['id']: a for a in j['document']['actions']}
    assert [f['role'] for f in by['action:birth_pay']['facts'] if f['fact']['kind'] == 'fee'] == ['pay']
    assert not any(f['fact']['kind'] == 'fee' for f in by['action:birth_submit']['facts'])
    assert {f['fact']['name'] for f in by['action:birth_submit']['facts']} == {'Completed application', 'Payment receipt'}


def test_phases_and_recap_wording_exist_only_where_the_structure_supports_them(demo):
    company, _ = ask(demo, 'official-company_pack-v3', {**BASE, 'segmentation': 'on', 'recap': 'on'}, True)
    assert [p['label']['text'] for p in company['document']['phases']] == ['Prepare the four document sets', 'Submit for the format check']
    for pid in ('official-nic_amendment-v3', 'official-birth_copy-v3'):
        refused, _ = ask(demo, pid, {**BASE, 'segmentation': 'on'}, True, expect=422)
        assert refused['detail']['code'] == 'infeasible_configuration'


def test_manual_adjustment_of_a_provisional_preview_stays_provisional_and_never_trains(demo):
    j, sid = ask(demo, 'official-nic_amendment-v3', {**BASE, 'relationships': 'map'}, True)
    child = demo.post(ROOT + '/journeys/' + j['journey_id'] + '/views', headers={'X-C4-Token': TOKEN}, json={'request_id': uuid4().hex, 'parent_view_id': j['view_id'], 'configuration': {**BASE, 'disclosure': 'on'}})
    assert child.status_code == 200, child.text
    body = child.json()
    assert body['selection']['kind'] == 'manual_adjustment' and body['preparation']['content_state'] == 'provisional_demo'
    assert not body['selection']['learning_eligible']


def test_evaluate31_relax_map_changes_only_the_map_rule(entries):
    pid = 'official-nic_amendment-v3'
    content = GuidanceContent31.model_validate(packet(pid)['content'])
    src = source(entries, pid)
    strict = {c.configuration.key for c in evaluate31(src, content, assume_reviewed=True) if c.feasible}
    relaxed = {c.configuration.key for c in evaluate31(src, content, assume_reviewed=True, relax_map=True) if c.feasible}
    assert strict < relaxed and all(k.split(':')[4] == 'map' for k in relaxed - strict)
    for pid2 in ('official-birth_copy-v3', 'official-company_pack-v3'):
        assert evaluate31(source(entries, pid2), None) and sum(c.feasible for c in evaluate31(source(entries, pid2), None)) == 4
