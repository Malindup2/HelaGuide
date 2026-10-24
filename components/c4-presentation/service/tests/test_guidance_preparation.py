"""Controlled content integration only: no training or real provider calls."""
import copy
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from app.guidance.catalogue import Configuration
from app.guidance.content import GuidanceContent
from app.guidance.demo import FIXTURES, install_fictional_content
from app.guidance.registry import ContentRegistry
from app.preparation.content_service import ContentPreparation, PreparationSettings
from app.models.explanations import ProviderIdentity, ProviderReply, ProviderCall
from app.host.application import create_app
from app.host.identity import WorkspaceRuntime
from app.procedures.registration import workspace_registry

PID = "synthetic-practice-v2"

@pytest.fixture(scope="module")
def entries():
    return workspace_registry()

@pytest.fixture
def runtime(entries):
    return SimpleNamespace(lock=threading.RLock(), procedures=dict(entries), state={})


def packet(pid=PID):
    return json.loads((FIXTURES / (pid + ".json")).read_text(encoding="utf-8"))


def service(tmp_path, runtime, *, dynamic=False, provider=None):
    return ContentPreparation(runtime, tmp_path / "prepared-content", settings=PreparationSettings(
        mode="dynamic" if dynamic else "demo", llm_enabled=True, on_miss=True), provider_factory=provider)


class Provider:
    calls = 0
    identity = ProviderIdentity(name="offline-contract-test", requested_model="authored-fixture", sdk_version="test")
    def complete(self, **kwargs):
        type(self).calls += 1
        request = json.loads(kwargs["payload"])
        draft = packet()["draft"]
        draft.update(origin="provider_generated", procedure_id=request["graph"]["plan_id"],
                     language=request["language"], source_graph_fingerprint=request["source_graph_fingerprint"],
                     relationship_fingerprint=request["relationship_fingerprint"])
        assert "verified_relationships" in request
        return ProviderReply(text=json.dumps(draft), call=ProviderCall(response_id="offline", returned_model="authored-fixture"))
    def close(self):
        pass


def publish_draft(s, identifier):
    src = s.source(PID)
    original = s.registry.inspect(identifier)["content"]
    data = packet()["content"]
    data["origin"] = original.origin
    data["language"] = original.language
    provisional = GuidanceContent.model_validate({**data, "review": None})
    data["review"]["artifact_digest"] = provisional.fingerprint
    reviewed = GuidanceContent.model_validate(data)
    result = s.registry.review(src, identifier, reviewed, kind="internal_fictional_author")
    assert s.registry.get(src, original.language) is None
    return s.registry.publish(src, result)


@pytest.mark.parametrize("pid,expected", [("synthetic-linear-v1",48),("synthetic-conditional-v1",96),("synthetic-parallel-v1",96),(PID,96)])
def test_demo_fixtures_follow_real_review_publication_and_capabilities(tmp_path,runtime,pid,expected):
    s=service(tmp_path,runtime,provider=lambda:pytest.fail("demo must never call a provider"))
    assert len(install_fictional_content(s))==4
    response=s.request(pid)
    assert response["content_state"]=="published" and not response["generation_enabled"]
    assert response["review_kind"]=="internal_fictional_author"
    assert sum(c["feasible"] for c in response["capabilities"])==expected
    assert install_fictional_content(s)==[] and s.processor.jobs()==[]
    artifact=s.registry.inspect(response["artifact_id"])
    assert "AI-assisted" in artifact["content"].review.reviewer
    assert "external" in artifact["content"].review.scope_note.lower()
    for c in response["capabilities"]:
        if not c["feasible"]:continue
        rendered=s.request(pid,configuration=Configuration(**c["configuration"]))["document"]
        assert rendered["facts"]==response["document"]["facts"]
        assert [a["essential"] for a in rendered["actions"]]==[a["essential"] for a in response["document"]["actions"]]
    if expected==96:
        rich=s.request(pid,configuration=Configuration(navigation="guided",explanation="detailed",disclosure="on",relationships="map",recap="on",segmentation="on"))["document"]
        assert rich["phases"] and all(a["recap"] and a["explanation_hidden"] for a in rich["actions"])
        assert rich["map_labels"]=={a["id"]:a["heading"] for a in rich["actions"]}
        assert all(f["scope"]=="stage" for f in rich["facts"])


def test_cache_hit_restart_does_not_enqueue_or_invoke_provider(tmp_path,runtime):
    s=service(tmp_path,runtime);install_fictional_content(s);original=s.request(PID)
    restored=ContentPreparation(runtime,s.registry.directory,settings=PreparationSettings("dynamic",True,True),provider_factory=lambda:pytest.fail("cache hit must not create provider"))
    restored.start()
    try:
        after=restored.request(PID)
        assert after["artifact_id"]==original["artifact_id"] and after["job_id"] is None
        assert restored.processor.jobs()==[]
    finally:restored.close()


def test_demo_miss_is_complete_fallback_and_never_generates(tmp_path,runtime):
    s=service(tmp_path,runtime,provider=lambda:pytest.fail("demo generation forbidden"))
    result=s.request("official-nic_amendment-v3",configuration=Configuration(explanation="detailed"))
    assert result["content_state"]=="source_fallback" and result["job_id"]
    assert not result["requested_configuration_feasible"] and not s.processor.process_once()
    src=s.source("official-nic_amendment-v3");passages={c.content_id:c.text for c in src.graph.content}
    for action,rendered in zip(src.graph.actions,result["document"]["actions"]):
        assert all(passages[cid] in rendered["essential"] for cid in action.required_content_ids)
    assert not any(c["feasible"] and c["configuration"]["relationships"]=="map" for c in result["capabilities"])


def test_concurrent_misses_create_one_durable_job_and_one_draft(tmp_path,runtime):
    Provider.calls=0;s=service(tmp_path,runtime,dynamic=True,provider=Provider)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(lambda _:s.request(PID),range(16)))
    assert len({r["job_id"] for r in results})==1 and all(r["job_id"] for r in results)
    assert len(s.processor.jobs())==1
    assert s.processor.process_once() and Provider.calls==1
    assert not s.processor.process_once() and Provider.calls==1
    draft=s.processor.draft(results[0]["job_id"])
    assert draft["provisional"] and draft["status"]=="draft"
    assert s.request(PID)["content_state"]=="source_fallback" and s.request(PID)["preparation_state"]=="draft"
    with pytest.raises(ValueError):s.registry.publish(s.source(PID),draft["artifact_id"])
    published=publish_draft(s,draft["artifact_id"])
    s.processor.scan()
    assert s.request(PID)["artifact_id"]==published and s.processor.jobs()[0]["status"]=="published"
    assert not s.processor.process_once() and Provider.calls==1
    with pytest.raises(ValueError):s.registry.draft(s.source(PID),packet_content())


def packet_content():
    return GuidanceContent.model_validate(packet()["content"])


def test_async_worker_does_not_block_fallback_and_never_auto_publishes(tmp_path,runtime):
    entered=threading.Event();release=threading.Event()
    class Slow(Provider):
        def complete(self,**kwargs):
            entered.set();assert release.wait(5)
            return super().complete(**kwargs)
    s=service(tmp_path,runtime,dynamic=True,provider=Slow);s.start()
    try:
        response=s.request(PID)
        assert response["content_state"]=="source_fallback" and entered.wait(3)
        assert s.registry.get(s.source(PID)) is None
        release.set()
        for _ in range(100):
            if s.processor.jobs()[0]["status"]=="pending_review":break
            time.sleep(.02)
        assert s.processor.jobs()[0]["status"]=="pending_review"
        assert s.request(PID)["content_state"]=="source_fallback"
    finally:release.set();s.close()


def test_failure_persists_no_silent_retry_and_fallback_survives(tmp_path,runtime):
    class Failing(Provider):
        calls=0
        def complete(self,**kwargs):
            type(self).calls+=1
            raise RuntimeError("DO-NOT-PERSIST-SECRET")
    s=service(tmp_path,runtime,dynamic=True,provider=Failing);s.request(PID)
    assert s.processor.process_once() and Failing.calls==1
    assert s.request(PID)["preparation_state"]=="failed"
    reopened=service(tmp_path,runtime,dynamic=True,provider=Failing)
    assert not reopened.processor.process_once() and Failing.calls==1
    assert "DO-NOT-PERSIST" not in json.dumps(reopened.processor.jobs())
    assert reopened.request(PID)["document"]["actions"]


@pytest.mark.parametrize("damage",["review","coverage","evidence","graph","fee"])
def test_generated_invalid_or_self_reviewed_content_never_published(tmp_path,runtime,damage):
    class Invalid(Provider):
        def complete(self,**kwargs):
            result=super().complete(**kwargs);data=json.loads(result.text)
            if damage=="review":data["actions"][0]["heading"]["status"]="reviewed"
            if damage=="coverage":data["claims"][0]["end"]-=1;data["claims"][0]["quote"]=data["claims"][0]["quote"][:-1]
            if damage=="evidence":data["claims"][0]["evidence_ids"]=["invented"]
            if damage=="graph":data["source_graph_fingerprint"]="wrong"
            if damage=="fee":data["attachments"]=[{"id":"bad","fact_id":"invented","scope":"stage","stage_id":"invented"}]
            return result.model_copy(update={"text":json.dumps(data)})
    s=service(tmp_path,runtime,dynamic=True,provider=Invalid);s.request(PID)
    assert s.processor.process_once()
    assert s.processor.jobs()[0]["status"]=="failed" and s.registry.get(s.source(PID)) is None
    assert s.request(PID)["content_state"]=="source_fallback"


def test_language_and_relationship_fingerprint_miss(tmp_path,runtime):
    s=service(tmp_path,runtime);install_fictional_content(s)
    assert s.request(PID,language="si")["content_state"]=="source_fallback"
    assert s.request(PID)["content_state"]=="published"
    changed=dict(runtime.procedures[PID]);changed["overlay"]=None;runtime.procedures[PID]=changed
    assert s.request(PID)["content_state"]=="source_fallback"


def test_queue_failure_does_not_break_source_fallback(tmp_path,runtime,monkeypatch):
    s=service(tmp_path,runtime)
    def fail(*args):raise OSError("unavailable")
    monkeypatch.setattr(s,"enqueue",fail)
    result=s.request(PID)
    assert result["document"]["actions"] and result["error_code"]=="preparation_queue_unavailable"


def test_publication_tamper_rejected_and_not_served(tmp_path,runtime):
    s=service(tmp_path,runtime);install_fictional_content(s);result=s.request(PID)
    with s.registry.connect() as db:
        row=db.execute("SELECT body FROM artifacts WHERE id=?",(result["artifact_id"],)).fetchone()
        data=json.loads(row[0]);data["actions"][0]["heading"]["text"]="INVENTED"
        db.execute("UPDATE artifacts SET body=? WHERE id=?",(json.dumps(data),result["artifact_id"]))
    response=s.request(PID)
    assert response["content_state"]=="source_fallback" and "INVENTED" not in json.dumps(response)


def test_existing_app_opt_in_routes_and_guest_preflight_do_not_change_policy(tmp_path,entries):
    r=WorkspaceRuntime(tmp_path/"v2"/"workspace"/"isolated.sqlite3",procedures=entries)
    before=r.status();rng=copy.deepcopy(r.state["rng"])
    options={"directory":tmp_path/"prepared-content","settings":PreparationSettings(),"demo_fixtures":True}
    with TestClient(create_app(runtime=r,workspace=True,prepared_content_options=options)) as client:
        response=client.post("/workspace/content/guidance",json={"procedure_id":PID})
        assert response.status_code==200 and response.json()["content_state"]=="published"
        guest=client.post("/dev/v1/sessions").json()
        result=client.post('/workspace/sessions/'+guest['session_id']+'/guidance',json={"procedure_id":PID,"request_id":str(uuid4()),"expected_revision":0})
        assert result.status_code==200 and result.json()["prepared_content"]["content_state"]=="published"
        assert result.json()["routing"]=="standard"
        assert r.status()==before and r.state["rng"]==rng
    r.close()


def test_existing_app_content_routes_are_disabled_by_default(entries):
    r=WorkspaceRuntime(procedures=entries)
    with TestClient(create_app(runtime=r,workspace=True)) as client:
        assert client.post("/workspace/content/guidance",json={"procedure_id":PID}).status_code==404
    r.close()


@pytest.mark.parametrize('mode,llm,on_miss,enabled', [('demo',True,True,False),('dynamic',False,True,False),('dynamic',True,False,False),('dynamic',True,True,True)])
def test_explicit_environment_gates(monkeypatch,mode,llm,on_miss,enabled):
    monkeypatch.setenv('C4_PREPARED_CONTENT_MODE',mode)
    monkeypatch.setenv('C4_LLM_ENABLED',str(llm).lower())
    monkeypatch.setenv('C4_PREPARATION_ON_MISS',str(on_miss).lower())
    monkeypatch.setenv('C4_DEV_LLM_ENABLED','true')
    assert PreparationSettings.from_environment().generation_enabled==enabled


def test_two_processors_cannot_generate_same_job_twice(tmp_path,runtime):
    Provider.calls=0
    a=service(tmp_path,runtime,dynamic=True,provider=Provider)
    b=service(tmp_path,runtime,dynamic=True,provider=Provider)
    a.request(PID)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda x:x.processor.process_once(),[a,b]))
    assert Provider.calls==1 and a.processor.jobs()[0]['status']=='pending_review'


def test_changed_graph_job_abstains_from_generation(tmp_path,runtime):
    Provider.calls=0;s=service(tmp_path,runtime,dynamic=True,provider=Provider);s.request(PID)
    runtime.procedures.pop(PID)
    assert not s.processor.process_once() and Provider.calls==0
    assert s.processor.jobs()[0]['status']=='stale'


def test_dynamic_registration_api_to_worker_review_cli_publication(tmp_path,entries,monkeypatch,capsys):
    from tests.test_preparation_bridge import dynamic_packet
    from app.preparation.review_cli import main
    r=WorkspaceRuntime(procedures=entries);before=r.status();Provider.calls=0
    directory=tmp_path/'prepared-content'
    options={'directory':directory,'settings':PreparationSettings('dynamic',True,True),'provider_factory':Provider}
    with TestClient(create_app(runtime=r,workspace=True,prepared_content_options=options)) as client:
        registration=dynamic_packet();pid=registration.plan['plan_id']
        assert client.post('/workspace/procedures',json=registration.model_dump(mode='json')).status_code==200
        response=client.post('/workspace/content/guidance',json={'procedure_id':pid}).json()
        assert response['content_state']=='source_fallback'
        for _ in range(100):
            jobs=client.get('/workspace/content/jobs').json()
            if jobs and jobs[0]['status']=='pending_review':break
            time.sleep(.02)
        assert jobs[0]['status']=='pending_review' and Provider.calls==1
        preview=client.get('/workspace/content/jobs/'+response['job_id']+'/draft').json()
        assert preview['provisional'] and 'NOT published' in preview['label']
        draft=preview['artifact'];prepared=client.app.state.prepared_content
        data=packet()['content'];original=draft['content']
        for key in ('procedure_id','origin','language','source_graph_fingerprint','relationship_fingerprint'):
            data[key]=original[key]
        data['review']['artifact_digest']=GuidanceContent.model_validate({**data,'review':None}).fingerprint
        reviewed=tmp_path/'reviewed.json';reviewed.write_text(json.dumps(data),encoding='utf-8')
        job=prepared.processor.directory/(response['job_id']+'.json')
        base=['--directory',str(directory),'--source-job',str(job)]
        monkeypatch.setattr('sys.argv',['editor','review',*base,'--artifact',draft['artifact_id'],'--reviewed-content',str(reviewed),'--reviewer',data['review']['reviewer'],'--kind','internal_fictional_author','--confirm-source-review'])
        main();review_id=capsys.readouterr().out.strip()
        assert prepared.registry.inspect(review_id)['state']=='reviewed'
        assert client.post('/workspace/content/guidance',json={'procedure_id':pid}).json()['content_state']=='source_fallback'
        monkeypatch.setattr('sys.argv',['editor','publish',*base,'--artifact',review_id]);main();capsys.readouterr()
        published=client.post('/workspace/content/guidance',json={'procedure_id':pid}).json()
        assert published['content_state']=='published' and published['artifact_id']==review_id
        assert r.status()==before
    r.close()



def test_cannot_enable_legacy_generation_alongside_revised_handler(entries,tmp_path):
    with pytest.raises(ValueError,match='disable legacy generation'):
        create_app(workspace=True,preparation_options={'enabled':True},prepared_content_options={'directory':tmp_path/'prepared-content'})
