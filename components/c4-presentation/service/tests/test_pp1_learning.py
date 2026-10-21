"""PP1 genuine model, bounded encoder, isolated training and API attribution."""
import copy
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import numpy as np
import pytest
from fastapi.testclient import TestClient
from app.guidance import features
from app.guidance.catalogue import CATALOGUE, Configuration
from app.guidance.experiment import dataset, run
from app.guidance.policy import Model, PolicyStore
from app.guidance.replay import replay
from app.v2.api import create_app
from app.v2.identity import WorkspaceRuntime
from app.v2.registration import workspace_registry

ROOT='/workspace/guidance';PID='synthetic-practice-v2';TOKEN='pp1-test-capability-'+('x'*40)

@pytest.fixture(scope='module')
def data():return dataset()

@pytest.mark.parametrize('variant',["416","451","516","525"])
def test_approved_schema_bounds_and_prefixes(data,variant):
    assert len(features.CONTEXT)==52 and len(features.PREFERENCES)==13
    assert len(features.PAIRS)==7 and len(features.TRIPLES)==13 and len(features.SCAFFOLD_PAIRS)==9
    m=data[PID]['measurements']
    # All 96 legal actions, 36 familiarity/confidence combinations incl unknown,
    # saturated complete values and the maximum six preference indicators.
    saturated=m.model_copy(update={n:getattr(m,n).model_copy(update={'observed':10**12,'completeness':'complete'}) for n in features.FEATURE_NAMES})
    for f in [1,2,3,4,5,None]:
        for n in [1,2,3,4,5,None]:
            ctx={'familiarity':f,'confidence':n,'preferences':{d:s[-1] for d,s in __import__('app.guidance.catalogue',fromlist=['DIMENSIONS']).DIMENSIONS.items()}}
            for c in CATALOGUE:
                vector=features.encode(saturated,ctx,c,variant)
                assert vector.shape==(int(variant),) and np.linalg.norm(vector)<=1+1e-12
                assert np.array_equal(vector,features.encode(saturated,ctx,c)[:int(variant)])


def test_reference_unknown_preferences_and_completeness(data):
    m=data[PID]['measurements'];c=CATALOGUE[-1]
    five=features.encode(m,{'familiarity':5,'confidence':5},c)
    unknown=features.encode(m,{},c)
    assert not np.array_equal(five,unknown)
    pref=features.encode(m,{'familiarity':5,'confidence':5,'preferences':{'segmentation':'on'}},c)
    assert not np.array_equal(pref,five)
    incomplete=m.model_copy(update={n:getattr(m,n).model_copy(update={'completeness':'unknown'}) for n in features.FEATURE_NAMES})
    assert not features.encode(incomplete,{},c)[416:516].any()
    invalid=m.model_copy(update={'step_count':m.step_count.model_copy(update={'scale':999})})
    with pytest.raises(ValueError,match='scale'):features.encode(invalid,{},c)
    with pytest.raises(ValueError,match='rating'):features.encode(m,{'confidence':0},c)


def test_gaussian_update_sampling_checkpoint(data,tmp_path):
    model=Model();x=features.encode(data[PID]['measurements'],{'familiarity':1},CATALOGUE[-1])
    matrix=np.array([x,x/2])
    assert np.array_equal(model.score(matrix,17)[1],model.score(matrix,17)[1])
    prior=model.kernel._precision.copy();model.update(x,1)
    assert model.revision==1 and np.allclose(model.kernel._precision,prior+np.outer(x,x))
    expected=np.linalg.solve(model.kernel._precision,model.kernel._b)
    assert np.allclose(model.kernel._mean,expected)
    blob=model.state();restored=Model.restore(blob,model.manifest)
    assert restored.state()==blob and np.array_equal(restored.score(matrix,23)[1],model.score(matrix,23)[1])
    with pytest.raises(ValueError):Model.restore(blob,Model('416').manifest)
    with pytest.raises(ValueError):model.update(x,2)
    path=tmp_path/'pp1-learning'/'check.npz';model.save(path)
    with pytest.raises(FileExistsError):model.save(path)


@pytest.fixture
def active(tmp_path):
    r=WorkspaceRuntime(procedures=workspace_registry())
    options={'directory':tmp_path/'prepared-content','demo_fixtures':True}
    policy={'directory':tmp_path/'pp1-learning'/'interactive','seed':3}
    with TestClient(create_app(runtime=r,workspace=True,prepared_content_options=options,guidance_api_options={'research_enabled':True,'policy_options':policy})) as client:
        yield client,r,client.app.state.guidance_api,policy
    r.close()


def profile(client):
    service=next(p['service_id'] for p in client.get(ROOT+'/procedures').json() if p['procedure_id']==PID)
    result=client.post(ROOT+'/profiles',json={'profile_id':'profile:'+uuid4().hex,'display_name':'PP1 synthetic test profile','personalization_enabled':True,
        'initial_context':{'navigation_capability':1,'familiarity':[{'service_id':service,'score':1}]}})
    assert result.status_code==200,result.text
    return result.json()['session']['session_id']


def start(client,sid,**extra):
    return client.post(ROOT+'/requests',json={'request_id':uuid4().hex,'session_id':sid,'procedure_id':PID,'capability_token':TOKEN,'mode':'personalized',**extra})

def event(client,j):
    return client.post(ROOT+'/journeys/'+j['journey_id']+'/events',headers={'X-C4-Token':TOKEN},json={'event_id':uuid4().hex,'view_id':j['view_id'],'type':'view_displayed','action_ids':[j['document']['actions'][0]['id']]})

def rating(client,j,r='fits',identifier=None):
    return client.post(ROOT+'/journeys/'+j['journey_id']+'/ratings',headers={'X-C4-Token':TOKEN},json={'event_id':identifier or uuid4().hex,'view_id':j['view_id'],'rating':r})


def test_genuine_api_selection_feedback_duplicate_restart(active):
    client,r,api,options=active;old=r.status();sid=profile(client)
    response=start(client,sid);assert response.status_code==200,response.text
    j=response.json();assert j['selection']['kind']=='shared_gaussian_lints' and j['selection']['learning_eligible']
    assert rating(client,j).status_code==409
    assert event(client,j).status_code==200
    before=api.policy.status();identifier=uuid4().hex
    receipt=rating(client,j,identifier=identifier);assert receipt.status_code==200,receipt.text
    assert receipt.json()['policy_updated'] and receipt.json()['reward']==1
    assert rating(client,j,identifier=identifier).json()==receipt.json()
    assert rating(client,j,r='does_not_fit').status_code==409
    after=api.policy.status();assert after['posterior_revision']==before['posterior_revision']+1
    assert after['posterior_fingerprint']!=before['posterior_fingerprint'] and after['accepted_feedback_count']==1
    assert PolicyStore(**options).status()==after
    record=client.get(ROOT+'/journeys/'+j['journey_id']+'/inspector',headers={'X-C4-Token':TOKEN}).json()
    assert len(record['features']['selected'])==525 and record['posterior_updates']==1
    scores=record['sampled_scores'];assert max(scores,key=lambda s:s['sampled_score'])['configuration']==j['selection']['configuration']
    assert r.status()==old  # historical host 515 posterior untouched


def test_manual_preview_guest_off_and_hard_constraints(active):
    client,r,api,_=active;sid=profile(client)
    ctx=client.get(ROOT+'/context/'+sid,params={'procedure_id':PID}).json()
    patch={'request_id':uuid4().hex,'expected_revision':ctx['revision'],'preferences':{'segmentation':'on'},'accessibility':{'no_map':True,'no_guided':True,'no_disclosure':True}}
    assert client.patch(ROOT+'/context/'+sid,json=patch).status_code==200
    j=start(client,sid).json();c=j['selection']['configuration']
    assert c['relationships']!='map' and c['navigation']=='overview' and c['disclosure']=='off'
    event(client,j);before=api.policy.status()
    child=client.post(ROOT+'/journeys/'+j['journey_id']+'/views',headers={'X-C4-Token':TOKEN},json={'request_id':uuid4().hex,'parent_view_id':j['view_id'],'configuration':c})
    assert child.status_code==200,child.text
    assert not rating(client,child.json()).json()['policy_updated']
    assert api.policy.status()==before
    guest=client.post(ROOT+'/guests').json()['session_id'];g=start(client,guest).json()
    assert g['selection']['kind']=='standard' and rating(client,g).status_code==403
    assert api.policy.status()==before
    preview=client.post(ROOT+'/research/previews',json={'request_id':uuid4().hex,'session_id':sid,'procedure_id':PID,'capability_token':TOKEN,'configuration':c,'mode':'research_preview'}).json()
    assert not rating(client,preview).json()['policy_updated']
    assert api.policy.status()==before


def test_transaction_rollback_keeps_posterior_and_receipt_atomic(active,monkeypatch):
    client,r,api,_=active;sid=profile(client);j=start(client,sid).json();event(client,j);before=api.policy.status()
    original=api.store.save
    def fail(*args):raise RuntimeError('injected after posterior update')
    monkeypatch.setattr(api.store,'save',fail)
    with pytest.raises(RuntimeError):rating(client,j)
    monkeypatch.setattr(api.store,'save',original)
    assert api.policy.status()==before
    assert rating(client,j).json()['policy_updated']


def test_isolation_manifest_refuses_existing_state(tmp_path):
    path=tmp_path/'pp1-learning'/'a';store=PolicyStore(path,seed=1)
    before=store.status()
    with pytest.raises(ValueError):PolicyStore(path,seed=2)
    with pytest.raises(ValueError):PolicyStore(path,seed=1,mode='participant')
    with pytest.raises(ValueError):PolicyStore(tmp_path/'v2')
    assert store.status()==before


def test_reproducible_training_frozen_evaluation_and_replay(tmp_path):
    a=tmp_path/'pp1-learning'/'run-a';b=tmp_path/'pp1-learning'/'run-b'
    first=run(a,seeds=(7,9),train=2,evaluation=7,checkpoints=[1])
    second=run(b,seeds=(7,9),train=2,evaluation=7,checkpoints=[1])
    assert first==second
    for entry in first['runs']:
        assert replay(a,entry['run'])['exact_state']
        assert (a/entry['trace']).read_bytes()==(b/entry['trace']).read_bytes()
    assert all(r['evaluation']['summary']['violations']==0 for r in first['evaluations'])
    assert {r['episode'] for r in first['evaluations']}=={0,1,2}
    with pytest.raises(ValueError):run(a,train=1)


def test_zero_reward_concurrent_duplicate_and_personalization_off(active):
    client,r,api,_=active;sid=profile(client);j=start(client,sid).json();event(client,j)
    identifier=uuid4().hex
    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts=list(pool.map(lambda _:rating(client,j,'does_not_fit',identifier),range(2)))
    assert all(response.status_code==200 for response in receipts)
    assert receipts[0].json()==receipts[1].json()
    assert receipts[0].json()['reward']==0 and api.policy.status()['posterior_revision']==1
    p=next(p for p in client.get(ROOT+'/profiles').json() if p['session']['session_id']==sid)
    result=client.patch(ROOT+'/profiles/'+p['profile']['profile_id']+'/personalization',json={'request_id':'event:'+uuid4().hex,'expected_revision':p['profile']['revision'],'enabled':False})
    assert result.status_code==200,result.text
    before=api.policy.status();standard=start(client,sid).json()
    assert standard['selection']['kind']=='standard' and rating(client,standard).status_code==403
    assert api.policy.status()==before


def test_research_report_and_trace_gates(active,tmp_path):
    client,r,api,_=active
    assert client.get(ROOT+'/research/learning').status_code==404
    folder=tmp_path/'pp1-learning'/'reports';folder.mkdir(parents=True)
    report={'runs':[{'run':'declared-run','trace':'trace.jsonl'}],'label':'SYNTHETIC'}
    (folder/'report.json').write_text(json.dumps(report),encoding='utf-8')
    (folder/'trace.jsonl').write_text(json.dumps({'episode':1,'reward':0})+'\n',encoding='utf-8')
    (folder/'learning.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"/>',encoding='utf-8')
    api.experiment_directory=folder
    assert client.get(ROOT+'/research/learning').json()==report
    assert client.get(ROOT+'/research/traces/declared-run').json()['observations']==[{'episode':1,'reward':0}]
    assert client.get(ROOT+'/research/traces/declared-run?limit=101').status_code==422
    assert client.get(ROOT+'/research/traces/undeclared').status_code==404
    assert client.get(ROOT+'/research/learning/learning.svg').status_code==200
    api.research_enabled=False
    assert client.get(ROOT+'/research/learning').status_code==404
