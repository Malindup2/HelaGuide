import copy
import json
import numpy as np
import pytest
from fastapi.testclient import TestClient
from app.v2.api import create_app
from app.v2.catalogue import CATALOGUE, Configuration, Context, evaluate
from app.v2.content import registry, Overlay, validate_overlay, ROOT
from app.v2.features import NAMES, encode, VARIANTS
from app.v2.runtime import Runtime, Conflict

@pytest.fixture(scope="module")
def procedures():
    return registry()

def start(rt, context=None):
    from uuid import uuid4
    return rt.create("synthetic-practice-v2", context or Context(), str(uuid4()))

def display(rt,j,event_id="display-event-1"):
    return rt.event(j["id"],j["token"],{"event_id":event_id,"view_id":j["current_view"],"type":"action_visible","action_id":j["document"]["actions"][0]["id"]})

def test_catalogue_and_capability_canonicalization(procedures):
    assert len(CATALOGUE)==len({c.key for c in CATALOGUE})==96
    p=procedures["synthetic-practice-v2"]
    assert len([e for e in evaluate(p["document"]["capabilities"],Context()) if not e["reasons"]])==96
    for p in procedures.values():
        for e in evaluate(p["document"]["capabilities"],Context(no_map=True)):
            if not e["reasons"]:
                assert e["configuration"]["relationships"]!="map"
    with pytest.raises(ValueError):Context(locks={"recap":"yesterday"})
    with pytest.raises(ValueError):Context(familiarity=0)

def test_features_exact_norm_and_three_way(procedures):
    m=procedures["synthetic-practice-v2"]["measurements"]
    assert len(NAMES)==len(set(NAMES))==515
    for c in CATALOGUE:
        for f in (None,1,5):
            v=encode(m,Context(familiarity=f,confidence=1,preferences=c.model_dump()),c)
            assert len(v)==515 and np.linalg.norm(v)<=1
    c=Configuration(navigation="guided")
    low=encode(m,Context(familiarity=1),c)
    high=encode(m,Context(familiarity=5),c)
    n="familiarity.1*complete_value.dependency_depth*guided"
    assert low[NAMES.index(n)]>0 and high[NAMES.index(n)]==0
    partial=m.model_copy(update={"dependency_depth":m.dependency_depth.model_copy(update={"completeness":"unknown"})})
    assert encode(partial,Context(familiarity=1),c)[NAMES.index(n)]==0
    for variant,size in VARIANTS.items():assert len(encode(m,Context(),c,variant))==size

def test_content_preservation_and_overlay_validation(procedures):
    for p in procedures.values():
        for a in p["graph"].actions:
            rendered=next(x for x in p["document"]["actions"] if x["id"]==a.action_id)
            assert set(rendered["coverage"])==set(a.required_content_ids)
            assert rendered["concise"] and rendered["expanded"]
    p=procedures["synthetic-practice-v2"]
    assert p["measurements"].parallel_group_count.observed==1
    assert p["document"]["joins"][0]["requirement"]["children"][1]["kind"]=="selected_option_of"
    data=json.loads((ROOT/"v2/practice/overlay.json").read_text())
    data["variants"][0]["required_content_ids"]=[]
    with pytest.raises(ValueError):validate_overlay(p["graph"],Overlay.model_validate(data))
    data=json.loads((ROOT/"v2/practice/overlay.json").read_text())
    data["joins"][0]["target"]="action:register_application"
    with pytest.raises(ValueError,match="cyclic"):validate_overlay(p["graph"],Overlay.model_validate(data))

def test_lints_update_manual_attribution_and_recovery(tmp_path,procedures):
    path=tmp_path/"v2"/"simulation.sqlite3"
    rt=Runtime(path,seed=77,procedures=procedures)
    j=start(rt); before=rt.status()
    decision=rt.inspect(j["id"],j["token"])["decision"]
    assert decision["selection_mode"]=="thompson"
    assert max(decision["scores"],key=lambda s:s["sampled"])["configuration"]==decision["configuration"]
    with pytest.raises(ValueError):rt.rate(j["id"],j["token"],j["current_view"],"about_right")
    display(rt,j);display(rt,j)
    receipt=rt.rate(j["id"],j["token"],j["current_view"],"about_right")
    assert receipt["eligible"] and receipt["posterior_revision"]==1
    rt.rate(j["id"],j["token"],j["current_view"],"about_right")
    assert rt.status()["posterior_revision"]==1
    x=np.array(decision["features"])
    assert np.allclose(rt.kernel._precision,np.eye(515)+np.outer(x,x))
    assert np.allclose(rt.kernel._mean,np.linalg.solve(np.eye(515)+np.outer(x,x),x*.5))
    updated=rt.status();assert before["posterior_fingerprint"]!=updated["posterior_fingerprint"]
    config=Configuration(**decision["configuration"])
    config=config.model_copy(update={"recap":"off" if config.recap=="on" else "on"})
    child=rt.adjust(j["id"],j["token"],j["current_view"],config,"adjust-1")
    child["token"]=j["token"];display(rt,child,"display-child")
    assert not rt.rate(j["id"],j["token"],child["current_view"],"about_right")["eligible"]
    assert rt.status()==updated
    rt.close();rt=Runtime(path,seed=77,procedures=procedures)
    assert rt.status()==updated
    assert len(rt.inspect(j["id"],j["token"])["journey"]["views"])==2
    rt.close()
    with pytest.raises(ValueError,match="incompatible"):Runtime(path,mode="participant",seed=77,procedures=procedures)

def test_api_e2e_read_only_inspector(procedures):
    rt=Runtime(procedures=procedures)
    with TestClient(create_app(runtime=rt)) as client:
        j=client.post('/v2/journeys',json={"procedure_id":"synthetic-practice-v2","request_id":"api-test-1"}).json()
        headers={"X-C4-Token":j["token"]};url='/v2/journeys/'+j["id"]
        assert client.get(url,headers={"X-C4-Token":"wrong"}).status_code==403
        assert client.post(url+'/events',headers=headers,json={"event_id":"api-display-1","view_id":j["current_view"],"type":"action_visible","action_id":j["document"]["actions"][0]["id"]}).status_code==200
        before=client.get('/v2/policy').json()
        for _ in range(2):assert client.get(url+'/inspector',headers=headers).status_code==200
        assert client.get('/v2/policy').json()==before
        result=client.post(url+'/ratings',headers=headers,json={"view_id":j["current_view"],"rating":"need_more"})
        assert result.status_code==200 and result.json()["reward"]==0
        assert client.get('/v2/policy').json()["posterior_revision"]==1
    rt.close()

def test_journey_isolation_hard_locks_and_event_conflicts(procedures):
    rt=Runtime(procedures=procedures)
    j=start(rt,Context(locks={"relationships":"none"}))
    assert rt.inspect(j["id"],j["token"])["decision"]["configuration"]["relationships"]=="none"
    display(rt,j)
    with pytest.raises(Conflict):rt.event(j["id"],j["token"],{"event_id":"display-event-1","view_id":j["current_view"],"type":"navigate","action_id":j["document"]["actions"][0]["id"]})
    j2=start(rt);assert j2["seen"]==[]
    with pytest.raises(PermissionError):rt.read(j2["id"],j["token"])
    with pytest.raises(ValueError):rt.adjust(j["id"],j["token"],j["current_view"],Configuration(relationships="map"),"bad-map")
    rt.close()


def test_reviewed_content_integrity_and_structure(tmp_path, procedures):
    from app.v2.preparation import approve, resolve
    entry=procedures["synthetic-practice-v2"]
    artifact={"status":"pending","origin":"human_authored","overlay":entry["overlay"].model_dump(mode="json")}
    path=tmp_path/"review.json"
    path.write_text(json.dumps(artifact))
    with pytest.raises(ValueError,match="unreviewed"):
        resolve(entry["graph"],path)
    approved=approve(entry["graph"],artifact,"test source reviewer")
    path.write_text(json.dumps(approved))
    result=resolve(entry["graph"],path)
    assert result["document"]["joins"]==entry["document"]["joins"]
    assert result["document"]["content_origin"]=="human_authored"
    approved["overlay"]["variants"][0]["concise"]="tampered"
    path.write_text(json.dumps(approved))
    with pytest.raises(ValueError,match="changed"):
        resolve(entry["graph"],path)


def test_invalid_activity_does_not_reward(procedures):
    rt=Runtime(procedures=procedures)
    j=start(rt);display(rt,j)
    before=rt.status()
    with pytest.raises(ValueError,match="optional block"):
        rt.event(j["id"],j["token"],{"event_id":"bad-detail","view_id":j["current_view"],"type":"detail_open","action_id":j["document"]["actions"][0]["id"],"value":"invented"})
    assert rt.status()==before
    rt.close()


def test_concurrent_runtime_fails_without_lost_update(tmp_path,procedures):
    path=tmp_path/"v2"/"concurrent.sqlite3"
    first=Runtime(path,procedures=procedures)
    second=Runtime(path,procedures=procedures)
    j=start(first)
    with pytest.raises(Conflict,match="concurrent"):
        start(second)
    second.close();first.close()
    recovered=Runtime(path,procedures=procedures)
    assert recovered.read(j["id"],j["token"])["id"]==j["id"]
    recovered.close()


def test_synthetic_reproducibility(tmp_path):
    from app.v2.simulation import run
    first=run(tmp_path/"v2"/"first",seed=91,train=2,evaluation=2)
    second=run(tmp_path/"v2"/"second",seed=91,train=2,evaluation=2)
    assert first["schedule_hash"]==second["schedule_hash"]
    for variant in first["results"]:
        a,b=first["results"][variant],second["results"][variant]
        assert a["trials"]==b["trials"]
        assert a["posterior"]["posterior_fingerprint"]==b["posterior"]["posterior_fingerprint"]
        assert a["posterior"]["accepted_feedback_count"]==2
        assert a["reload_verified"] and b["reload_verified"]


def test_offline_provider_preparation_keeps_review_pending(procedures):
    from app.v2.preparation import prepare
    from app.models.explanations import ProviderIdentity, ProviderReply, ProviderCall
    entry=procedures["synthetic-practice-v2"]
    class Provider:
        identity=ProviderIdentity(name="offline-test",requested_model="fixture",sdk_version="test")
        def complete(self,**kwargs):
            assert "Do not invent" in kwargs["instructions"]
            return ProviderReply(text=json.dumps({"variants":[v.model_dump(mode="json") for v in entry["overlay"].variants]}),call=ProviderCall(response_id="offline",returned_model="fixture"))
    artifact=prepare(entry["graph"],Provider(),entry["overlay"])
    assert artifact["status"]=="pending" and "digest" not in artifact
    assert artifact["overlay"]["joins"]==entry["document"]["joins"]
    assert entry["measurements"].measurement_version=="c4-structural-v2.1"


def test_control_opportunity_is_not_display_or_reward(procedures):
    rt=Runtime(procedures=procedures)
    j=start(rt);before=rt.status()
    key=f"{j['current_view']}:relationships"
    j=rt.event(j["id"],j["token"],{"event_id":"control-opportunity","view_id":j["current_view"],"type":"opportunity_visible","opportunity_id":key})
    assert j["opportunities"][key]["visible"]
    assert not j["views"][j["current_view"]]["displayed"]
    assert rt.status()==before
    rt.close()
