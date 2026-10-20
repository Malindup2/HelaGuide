"""Action fact attribution and honest, immutable demo preparation."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.official_procedures import load_official_procedures
from app.core.prepared_wording import prepare_wording_packet, wording_key, validate_wording_artifact
from app.core.wording_service import PreparedWordingStore, resolve_wording
from app.core.wording_views import WordingViews
from app.dev_main import create_app
from app.models.explanations import HumanReview
from tests.test_explanations import FakeProvider

DEMO = Path(__file__).resolve().parents[2] / 'research/data/prepared-demo'

def direct_facts(graph, action):
    ids = next(a.required_content_ids for a in graph.actions if a.action_id == 'action:' + action)
    return {f for c in graph.content if c.content_id in ids and c.text != graph.disclaimer for f in c.fact_ids}

def test_facts_are_bound_to_actions_not_inherited_from_service():
    birth, nic, company = load_official_procedures()[0]
    assert direct_facts(birth, 'birth_pay') == {'svc:birth_copy:fee'}
    assert direct_facts(birth, 'birth_submit') == {'svc:birth_copy:document:0', 'svc:birth_copy:document:1'}
    assert 'svc:nic_amendment:fee' in direct_facts(nic, 'nic_gn')
    assert 'svc:nic_amendment:fee' not in direct_facts(nic, 'nic_ds')
    assert direct_facts(company, 'company_directors') == {'svc:company_pack:document:2'}
    assert not company.branch_groups
    assert len(company.action_prerequisites) == 4
    assert nic.branch_groups[0].selection == 'XOR'
    assert sorted(len(o.action_ids) for o in nic.branch_groups[0].options) == [1, 2]

@pytest.mark.parametrize('graph', load_official_procedures()[0])
def test_stored_mock_has_three_distinct_prepared_versions_and_no_review(graph):
    store = PreparedWordingStore(DEMO)
    explanations = []
    for style in ('concise', 'plain', 'extra_plain'):
        packet = prepare_wording_packet(graph, writing_style=style)
        artifact = store.read(wording_key(packet))
        assert artifact is not None
        validate_wording_artifact(artifact)
        assert artifact.origin == 'demo_mock' and artifact.review is None
        assert artifact.provider is None and not artifact.generation_calls
        assert len(artifact.draft.items) == len(packet.targets)
        restricted = resolve_wording(graph, store, writing_style=style)
        assert restricted.artifact_digest is None
        resolved = resolve_wording(graph, store, writing_style=style, allow_demo_mock=True)
        assert resolved.artifact_digest
        assert all(i.origin == 'demo_mock' for i in resolved.items)
        explanations.append(tuple(i.text for i in resolved.items if i.slot_id.startswith('action_explanation/')))
        assert all(len(i.text) <= 120 for i in resolved.items if i.slot_id.startswith('action_heading/'))
    assert len(set(explanations)) == 3
    changed = graph.model_copy(update={'plan_id': graph.plan_id + '-changed'})
    assert resolve_wording(changed, store, allow_demo_mock=True).artifact_digest is None

def test_mock_cannot_be_relabelled_as_expert_reviewed():
    graph = load_official_procedures()[0][0]
    artifact = PreparedWordingStore(DEMO).read(wording_key(prepare_wording_packet(graph)))
    data = artifact.model_dump(mode='json')
    data['review'] = {'artifact_digest': '0'*64, 'reviewer_reference': 'pretend', 'reviewed_at': artifact.created_at.isoformat()}
    with pytest.raises(ValidationError, match='cannot claim human review'):
        type(artifact).model_validate_json(__import__('json').dumps(data))

def test_mock_snapshot_survives_restart_without_rewriting_learning(tmp_path):
    config = dict(provider=FakeProvider(failure='offline_test'), include_official_examples=True,
                  database_path=tmp_path/'state.sqlite3', demo_wording_directory=DEMO,
                  wording_views_directory=tmp_path/'wording')
    with TestClient(create_app(**config)) as client:
        procedure = next(p for p in client.get('/dev/v1/procedures').json() if p['plan_id']=='official-birth_copy-v3')
        session = client.post('/dev/v1/sessions').json()
        base = f"/dev/v1/sessions/{session['session_id']}"
        response = client.post(base+'/presentations', json={'procedure_id':procedure['procedure_id'], 'expected_revision':session['revision']})
        assert response.status_code == 201, response.text
        saved=response.json()
        before=client.get('/dev/v1/policy').json()
        assert saved['wording']['artifact_digest']
        assert all(i['origin']=='demo_mock' for i in saved['wording']['items'])
    # No current demo registry at restore time: historical artifact is embedded.
    config['demo_wording_directory']=None
    app=create_app(**config)
    with TestClient(app) as client:
        spec=app.state.runtime.presentations[saved['spec']['exposure_id']]
        assert app.state.runtime.wording_views.read(spec).model_dump(mode='json') == saved['wording']
        trace=client.get(base+f"/presentations/{spec.exposure_id}/pipeline-trace").json()
        assert trace['content']['wording_status']=='demo_mock_snapshot'
        after=client.get('/dev/v1/policy').json()
        for field in ('posterior_fingerprint','posterior_revision','accepted_feedback_count'):
            assert after[field]==before[field]
