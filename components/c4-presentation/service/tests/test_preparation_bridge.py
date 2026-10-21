import copy
import pytest
from app.v2.registration import workspace_registry, finalize

@pytest.mark.parametrize("category", ["actions", "conditions", "prerequisites", "branch_groups", "service_dependencies"])
@pytest.mark.parametrize("value", ["partial", "unknown", None])
def test_incomplete_structure_cannot_offer_guided_or_full_map(category, value):
    entry = copy.deepcopy(registered_entries()["synthetic-practice-v2"])
    if value is None:
        entry["document"]["completeness"].pop(category)
    else:
        entry["document"]["completeness"][category] = value
    doc = finalize(entry)["document"]
    assert doc["capabilities"]["navigation"]["states"] == ["overview"]
    assert "map" not in doc["capabilities"]["relationships"]["states"]
    assert "inline" in doc["capabilities"]["relationships"]["states"]
    assert doc["actions"][0]["concise"]

def test_unknown_parallel_coverage_disables_full_map_but_preserves_guided():
    entry = copy.deepcopy(registered_entries()["synthetic-practice-v2"])
    entry["document"]["completeness"]["parallel_groups"] = "unknown"
    doc = finalize(entry)["document"]
    assert "map" not in doc["capabilities"]["relationships"]["states"]
    assert "guided" in doc["capabilities"]["navigation"]["states"]

import json
import sys
import time
from functools import lru_cache
from fastapi.testclient import TestClient
from app.v2.api import create_app
from app.v2.identity import WorkspaceRuntime
from app.v2.content import Overlay
from app.v2.registration import ROOT, RegistrationPacket, register, queue_preparation
from app.v2.preparation import approve, main, resolve_artifact
from app.v2.preparation_jobs import PreparationProcessor
from app.models.explanations import ProviderIdentity, ProviderReply, ProviderCall

@lru_cache
def registered_entries():
    return workspace_registry()

def dynamic_packet():
    folder=ROOT/'v2'/'practice'
    plan=json.loads((folder/'plan.json').read_text());plan['plan_id']='dynamic-preparation-test'
    enrichment=json.loads((folder/'enrichment.json').read_text());enrichment['plan_id']=plan['plan_id']
    packet=RegistrationPacket(plan=plan,enrichment=enrichment)
    graph=register(packet)['graph']
    from app.core.scaffolds import graph_fingerprint
    overlay=registered_entries()['synthetic-practice-v2']['overlay'].model_copy(update={'graph_fingerprint':graph_fingerprint(graph),'variants':[]})
    return packet.model_copy(update={'relationships':overlay})

class Provider:
    calls=0
    identity=ProviderIdentity(name='offline-test',requested_model='fixture',sdk_version='test')
    def complete(self,**kwargs):
        type(self).calls+=1
        payload=json.loads(kwargs['payload'])
        assert payload['verified_relationships']['joins']
        variants=registered_entries()['synthetic-practice-v2']['overlay'].model_dump(mode='json')['variants']
        variants[0]['title']='Register the reviewed practice application'
        return ProviderReply(text=json.dumps({'variants':variants}),call=ProviderCall(response_id='offline',returned_model='fixture'))
    def close(self): pass


def test_disabled_worker_persists_job_without_provider_or_policy_write(tmp_path):
    path=tmp_path/'v2'/'workspace'/'disabled.sqlite3';r=WorkspaceRuntime(path,procedures={})
    entry=register(dynamic_packet());r.register_procedure(dynamic_packet())
    directory=path.parent/'preparation';queue_preparation(entry,directory)
    worker=PreparationProcessor(r,directory,enabled=False,provider_factory=lambda:pytest.fail('disabled provider called'))
    before=r.status();assert worker.process_once() is False
    assert len(worker.jobs())==1 and worker.jobs()[0]['status']=='queued'
    assert 'expanded' not in r.procedures[entry['document']['id']]['document']['capabilities']['explanation']['states']
    reopened=PreparationProcessor(r,directory,enabled=False)
    assert reopened.jobs()==worker.jobs() and r.status()==before
    r.close()


def test_async_dynamic_registration_review_cli_publish_and_restart(tmp_path,monkeypatch):
    path=tmp_path/'v2'/'workspace'/'dynamic.sqlite3';r=WorkspaceRuntime(path,procedures={})
    Provider.calls=0
    options={'enabled':True,'provider_factory':Provider,'interval':0.01}
    with TestClient(create_app(runtime=r,workspace=True,preparation_options=options)) as client:
        before=r.status()
        result=client.post('/workspace/procedures',json=dynamic_packet().model_dump(mode='json'))
        assert result.status_code==200 and result.json()['missing']
        for _ in range(100):
            jobs=client.get('/workspace/preparation/jobs').json()
            if jobs and jobs[0]['status']=='pending_review':break
            time.sleep(.02)
        assert jobs[0]['status']=='pending_review' and Provider.calls==1
        key=jobs[0]['id'];artifact=client.get(f'/workspace/preparation/jobs/{key}/draft').json()
        assert artifact['status']=='pending' and artifact['overlay']['reviewer']=='PENDING REVIEW'
        assert r.status()==before
        assert r.procedures['dynamic-preparation-test']['document']['capabilities']['explanation']['states']==['concise']
        assert client.post('/workspace/procedures/dynamic-preparation-test/wording',json={'artifact':artifact}).status_code==422
        # CLI consumes the queued graph, not registry()[dynamic id]. No live provider.
        job=next((path.parent/'preparation').glob('*.json'))
        source=path.parent/'draft.json';source.write_text(json.dumps(artifact))
        output=path.parent/'reviewed.json'
        monkeypatch.setattr(sys,'argv',['preparation','review','--job',str(job),'--input',str(source),'--output',str(output),'--reviewer','test source reviewer','--confirm-source-check'])
        main();reviewed=json.loads(output.read_text())
        response=client.post('/workspace/procedures/dynamic-preparation-test/wording',json={'artifact':reviewed})
        assert response.status_code==200 and response.json()['status']=='prepared'
        assert client.get('/workspace/preparation/jobs').json()[0]['status']=='published'
        assert r.status()==before
        assert Provider.calls==1
    expected=r.procedures['dynamic-preparation-test']['document'];r.close()
    restored=WorkspaceRuntime(path,procedures={})
    assert restored.procedures['dynamic-preparation-test']['document']==expected
    sid=restored.create_session()['session_id']
    j=restored.guidance(sid,'dynamic-preparation-test','after-preparation-restart',restored.settings(sid)['settings_revision'])
    assert j['document']['actions'][0]['title']=='Register the reviewed practice application'
    assert j['document']['capabilities']['explanation']['states']==['concise','expanded']
    restored.close()


def test_failure_no_silent_retry_and_stale_jobs(tmp_path):
    path=tmp_path/'v2'/'workspace'/'failure.sqlite3';r=WorkspaceRuntime(path,procedures={})
    entry=register(dynamic_packet());r.register_procedure(dynamic_packet());directory=path.parent/'preparation'
    queue_preparation(entry,directory)
    class Bad(Provider):
        def complete(self,**kwargs): raise RuntimeError('credential-must-not-be-persisted')
    worker=PreparationProcessor(r,directory,enabled=True,provider_factory=Bad)
    before=r.status();assert worker.process_once()
    job=worker.jobs()[0];assert job['status']=='failed'
    assert 'credential' not in json.dumps(worker.jobs())
    assert not worker.process_once()
    worker.retry(job['id']);worker.provider_factory=Provider
    assert worker.process_once() and worker.jobs()[0]['status']=='pending_review'
    assert r.status()==before
    # An absent/changed current procedure cannot send an old queued graph.
    r.procedures={}
    stale_dir=path.parent/'stale';queue_preparation(entry,stale_dir)
    stale=PreparationProcessor(r,stale_dir,enabled=True,provider_factory=lambda:pytest.fail('stale source sent'))
    assert not stale.process_once() and stale.jobs()[0]['status']=='stale'
    r.close()


def test_draft_source_binding_and_mock_origin_are_not_relabelled():
    entry=registered_entries()['synthetic-practice-v2']
    artifact={'status':'pending','source_fingerprint':'wrong','origin':'provider_generated','overlay':entry['overlay'].model_dump(mode='json')}
    with pytest.raises(ValueError,match='fingerprint'):approve(entry['graph'],artifact,'reviewer')
    artifact.pop('source_fingerprint');artifact['origin']='demo_mock'
    with pytest.raises(ValueError,match='mock'):approve(entry['graph'],artifact,'reviewer')
    artifact['origin']='human_authored'
    with pytest.raises(ValueError,match='reviewer'):approve(entry['graph'],artifact,'pending source check')


def test_worker_shutdown_recovers_jobs_without_regeneration(tmp_path):
    r=WorkspaceRuntime(procedures={});packet=dynamic_packet();r.register_procedure(packet)
    directory=tmp_path/'v2'/'jobs';queue_preparation(r.procedures[packet.plan['plan_id']],directory)
    worker=PreparationProcessor(r,directory,enabled=True,provider_factory=Provider,interval=.01)
    worker.start()
    for _ in range(100):
        if worker.jobs()[0]['status']=='pending_review':break
        time.sleep(.02)
    worker.close();assert not worker.thread.is_alive()
    reopened=PreparationProcessor(r,directory,enabled=True,provider_factory=lambda:pytest.fail('pending draft regenerated'))
    assert not reopened.process_once()
    assert reopened.draft(reopened.jobs()[0]['id'])['status']=='pending'
    r.close()



def test_two_workers_cannot_duplicate_paid_call_or_retry_in_flight(tmp_path):
    import threading
    r=WorkspaceRuntime(procedures={});packet=dynamic_packet();r.register_procedure(packet)
    directory=tmp_path/'v2'/'jobs';queue_preparation(r.procedures[packet.plan['plan_id']],directory)
    entered=threading.Event();release=threading.Event()
    class Blocking(Provider):
        calls=0
        def complete(self,**kwargs):
            entered.set();assert release.wait(5)
            return super().complete(**kwargs)
    one=PreparationProcessor(r,directory,enabled=True,provider_factory=Blocking)
    two=PreparationProcessor(r,directory,enabled=True,provider_factory=lambda:pytest.fail('duplicate provider call'))
    one.start()
    try:
        assert entered.wait(3)
        key=one.jobs()[0]['id']
        with pytest.raises(OSError):two.retry(key)
        assert not two.process_once()
    finally:
        release.set();one.close()
    assert Blocking.calls==1 and one.jobs()[0]['status']=='pending_review'
    # Simulate a dead process's claim; it remains inert until explicit retry.
    with two.connect() as db:db.execute("UPDATE preparation_jobs SET status='processing',draft=NULL WHERE id=?",(key,))
    assert not two.process_once()
    two.retry(key);two.provider_factory=Provider
    assert two.process_once() and two.jobs()[0]['status']=='pending_review'
    r.close()



def test_manual_template_keeps_verified_dynamic_relationships(tmp_path,monkeypatch):
    entry=register(dynamic_packet());directory=tmp_path/'v2'/'jobs'
    job=queue_preparation(entry,directory);out=directory/'template.json'
    monkeypatch.setattr(sys,'argv',['preparation','template','--job',str(job),'--output',str(out)])
    main();template=json.loads(out.read_text())
    assert template['status']=='pending' and template['overlay']['variants']==[]
    assert template['overlay']['joins']==entry['overlay'].model_dump(mode='json')['joins']
    assert template['source_fingerprint']==entry['document']['graph_fingerprint']
