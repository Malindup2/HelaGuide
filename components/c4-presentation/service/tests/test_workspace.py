import copy
import json
from uuid import uuid4
import numpy as np
import pytest
from fastapi.testclient import TestClient
from app.models.demo_profiles import CreateDemoProfileRequest, PersonalizationRequest
from app.v2.api import create_app
from app.v2.catalogue import Configuration, Context, evaluate
from app.v2.identity import WorkspaceRuntime, SettingsPatch
from app.v2.registration import workspace_registry, queue_preparation
from app.v2.features import NAMES, encode
from app.v2.runtime import Conflict, Runtime

@pytest.fixture(scope="module")
def entries():
    return workspace_registry()

def profile(r):
    return r.create_profile(CreateDemoProfileRequest(profile_id="profile:"+uuid4().hex, display_name="PP1", personalization_enabled=True,
        initial_context={"navigation_capability":2,"preferences":{"presentation_mode":"GUIDED"},
        "familiarity":[{"service_id":"svc:nic_amendment","score":1},{"service_id":"svc:birth_copy","score":5}]}))

def start(r,p,pid="synthetic-practice-v2"):
    sid=p["session"]["session_id"]
    return r.guidance(sid,pid,str(uuid4()),r.settings(sid)["settings_revision"])

def display(r,j):
    return r.event(j["id"], j["token"], {"event_id":str(uuid4()),"view_id":j["current_view"],"type":"action_visible","action_id":j["document"]["actions"][0]["id"]})

def test_saved_profile_context_and_feature_inputs(entries):
    r=WorkspaceRuntime(procedures=entries);p=profile(r);sid=p["session"]["session_id"]
    c,t=r.resolve(sid,"official-nic_amendment-v3")
    other,_=r.resolve(sid,"official-birth_copy-v3")
    assert c.familiarity==1 and other.familiarity==5 and c.confidence==2
    assert c.preferences["navigation"]=="guided" and t["sources"]["familiarity"]=="saved_service_report"
    override,_=r.resolve(sid,"synthetic-practice-v2",{"preferences":{"explanation":"expanded"}})
    assert override.preferences=={"navigation":"guided","explanation":"expanded"}
    with pytest.raises(ValueError):r.resolve(sid,"synthetic-practice-v2",{"locks":"invalid"})
    j=start(r,p);d=r.inspect(j["id"],j["token"])["decision"]
    assert len(d["features"])==515
    assert d["features"]==encode(entries["synthetic-practice-v2"]["measurements"],Context(**d["context"]),Configuration(**d["configuration"])).tolist()
    assert d["effective_context"]["session_id"]==sid
    preference=[i for i,n in enumerate(NAMES) if n.startswith("preference.navigation.guided*")]
    assert any(d["features"][i]>0 for i in preference)
    r.close()

def test_preferences_accessibility_revision_and_idempotency(entries):
    r=WorkspaceRuntime(procedures=entries);p=profile(r);sid=p["session"]["session_id"]
    revision=r.settings(sid)["settings_revision"]
    patch=SettingsPatch(request_id=str(uuid4()),expected_revision=revision,preferences={"explanation":"expanded"},locks={"recap":"on"},context={"accessibility":{"allow_relationship_visuals":False}})
    a=r.update_settings(sid,patch); b=r.update_settings(sid,patch)
    assert a==b and a["settings_revision"]>revision
    with pytest.raises(Conflict):r.update_settings(sid,SettingsPatch(request_id=str(uuid4()),expected_revision=revision))
    c,_=r.resolve(sid,"synthetic-practice-v2")
    good=[e["configuration"] for e in evaluate(entries["synthetic-practice-v2"]["document"]["capabilities"],c) if not e["reasons"]]
    assert good and all(x["recap"]=="on" and x["relationships"]!="map" for x in good)
    with pytest.raises(ValueError):r.resolve(sid,"synthetic-practice-v2",{"locks":{"recap":"off"}})
    r.close()

def test_standard_guest_and_disabled_profile_never_train(entries):
    r=WorkspaceRuntime(procedures=entries);s=r.create_session();before=r.status();rng=copy.deepcopy(r.state["rng"])
    j=r.guidance(s["session_id"],"synthetic-practice-v2",str(uuid4()),0)
    assert r.state["decisions"][j["decision_id"]]["features"]==[] and r.state["decisions"][j["decision_id"]]["scores"]==[]
    assert j["routing"]=="standard" and j["views"][j["root_view"]]["configuration"]==Configuration().model_dump()
    display(r,j); receipt=r.rate(j["id"],j["token"],j["root_view"],"about_right")
    assert receipt["reward"] is None and not receipt["eligible"] and r.status()==before and r.state["rng"]==rng
    r.close()

def test_end_to_end_learning_manual_and_restart(entries,tmp_path):
    path=tmp_path/"v2"/"workspace"/"state.sqlite3"
    r=WorkspaceRuntime(path,procedures=entries);p=profile(r)
    j=start(r,p);display(r,j);original=r.status()
    receipt=r.rate(j["id"],j["token"],j["root_view"],"about_right")
    assert receipt["eligible"] and r.status()["posterior_revision"]==1
    assert r.status()["posterior_fingerprint"]!=original["posterior_fingerprint"]
    assert r.rate(j["id"],j["token"],j["root_view"],"about_right")==receipt
    manual=start(r,p);config=Configuration(**manual["available_configurations"][0]);r.adjust(manual["id"],manual["token"],manual["current_view"],config,str(uuid4()))
    token=manual["token"]
    manual={**r.read(manual["id"],token),"token":token}
    display(r,manual)
    assert not r.rate(manual["id"],token,manual["current_view"],"about_right")["eligible"]
    assert r.status()["posterior_revision"]==1
    before=r.status();saved_settings=r.settings(p["session"]["session_id"]);r.close()
    r=WorkspaceRuntime(path,procedures=entries)
    assert r.status()==before and r.settings(p["session"]["session_id"])==saved_settings
    assert r.read(j["id"],j["token"])["views"][j["root_view"]]["rating"]["eligible"]
    r.close()
    with pytest.raises(ValueError,match="non-V2"):Runtime(path,procedures=entries)

def test_disabled_consent_revokes_existing_learning(entries):
    r=WorkspaceRuntime(procedures=entries);p=profile(r);j=start(r,p);display(r,j)
    r.personalization(p["profile"]["profile_id"],PersonalizationRequest(request_id="event:"+uuid4().hex,expected_revision=0,enabled=False))
    assert not r.rate(j["id"],j["token"],j["root_view"],"about_right")["eligible"]
    r.close()

def test_registration_wording_source_and_preparation(entries,tmp_path):
    nic=entries["official-nic_amendment-v3"]
    assert all("nic_" not in a["title"] for a in nic["document"]["actions"])
    assert any("Grama" in a["title"] for a in nic["document"]["actions"])
    assert all("120" in a["concise"] for a in nic["document"]["actions"] if "estate" in a["id"] or a["id"].endswith("nic_gn"))
    for entry in entries.values():
        assert entry["document"]["structure_fingerprint"]==entry["canonical"]["fingerprint"]
        for a in entry["document"]["actions"]:
            assert a["coverage"]
            assert a["recap"] != a["title"]
    path=queue_preparation(nic,tmp_path/"v2"/"jobs")
    assert path==queue_preparation(nic,tmp_path/"v2"/"jobs")
    assert json.loads(path.read_text())["live_generation_enabled"] is False

def test_workspace_api_existing_profile_contract_and_policy(entries):
    r=WorkspaceRuntime(procedures=entries)
    with TestClient(create_app(runtime=r,workspace=True)) as client:
        assert client.get("/health").json()["status"]=="ok"
        assert len(client.get("/dev/v1/procedures").json())==10
        p=profile(r);sid=p["session"]["session_id"]
        assert client.get("/dev/v1/demo-profiles").json()[0]["profile_id"]==p["profile"]["profile_id"]
        response=client.post(f"/workspace/sessions/{sid}/guidance",json={"procedure_id":"synthetic-practice-v2","request_id":str(uuid4()),"expected_revision":r.settings(sid)["settings_revision"]})
        assert response.status_code==200
        j=response.json();headers={"X-C4-Token":j["token"]}
        before=r.status()
        trace=client.get(f"/v2/journeys/{j['id']}/inspector",headers=headers).json()
        assert trace["decision"]["effective_context"]["profile_id"]==p["profile"]["profile_id"] and r.status()==before
        assert client.post("/v2/journeys",json={"procedure_id":"synthetic-practice-v2","request_id":str(uuid4())}).status_code==422
    r.close()


def test_native_only_revision_and_guidance_response_retry(entries):
    r=WorkspaceRuntime(procedures=entries);p=profile(r);sid=p["session"]["session_id"]
    before=r.settings(sid)["settings_revision"]
    patch=SettingsPatch(request_id=str(uuid4()),expected_revision=before,preferences={"explanation":"expanded"},locks={})
    after=r.update_settings(sid,patch)
    assert after["settings_revision"]>before
    token="synthetic-test-capability-"+uuid4().hex
    request=str(uuid4())
    j=r.guidance(sid,"synthetic-practice-v2",request,after["settings_revision"],capability_token=token)
    rng=copy.deepcopy(r.state["rng"])
    retried=r.guidance(sid,"synthetic-practice-v2",request,0,capability_token=token)
    assert retried["id"]==j["id"] and r.state["rng"]==rng and len(r.state["decisions"])==1
    r.close()


def test_explicit_v2_copy_does_not_write_source(entries,tmp_path):
    from app.v2.transfer import read_source,copy_policy
    import hashlib
    source=tmp_path/"v2"/"original.sqlite3"
    r=Runtime(source,procedures=entries)
    j=r.create("synthetic-practice-v2",Context(),str(uuid4()));display(r,j);r.rate(j["id"],j["token"],j["root_view"],"about_right")
    expected=r.status();r.close()
    before=hashlib.sha256(source.read_bytes()).hexdigest()
    kind,state=read_source(source)
    target=WorkspaceRuntime(tmp_path/"v2"/"workspace"/"copy.sqlite3",procedures=entries)
    assert kind=="v2" and copy_policy(target,state)==expected
    assert target.status()==expected
    target.close()
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before


def test_profile_copy_preserves_semantic_review_and_no_coefficients(entries):
    from types import SimpleNamespace
    from app.v2.transfer import copy_profiles
    from app.models.demo_profiles import DemoProfile
    source=WorkspaceRuntime(procedures=entries);p=profile(source);sid=p["session"]["session_id"]
    from app.models.user_context import ContextUpdate
    source.contexts.update_context(sid,ContextUpdate(preferences={"progressive_disclosure":True,"previous_context_recap":True,"relationship_visual":"BRANCH_MAP"}),expected_revision=source.session(sid).revision)
    snapshot=SimpleNamespace(sessions=source.contexts.export_state(),profiles=tuple(source.profiles.values()),policy=SimpleNamespace(config=SimpleNamespace(feedback_mode="simulation")))
    target=WorkspaceRuntime(procedures=entries);report=copy_profiles(target,snapshot)
    copied=target.profiles[p["profile"]["profile_id"]]
    settings=target.settings(copied.session_id)
    assert not copied.personalization_enabled and settings["preferences"]["disclosure"]=="collapsed"
    assert "preferences.previous_context_recap" in report[0]["needs_review"]
    assert "recap" not in settings["preferences"] and "relationships" not in settings["preferences"]
    assert target.status()["posterior_revision"]==0
    participant=WorkspaceRuntime(mode="participant",procedures=entries)
    with pytest.raises(ValueError,match="cross"):copy_profiles(participant,snapshot)
    participant.close();source.close();target.close()


def test_registration_packet_and_recovery(entries,tmp_path):
    from app.v2.registration import ROOT,RegistrationPacket
    folder=ROOT/"v2"/"practice"
    plan=json.loads((folder/"plan.json").read_text())
    enrichment=json.loads((folder/"enrichment.json").read_text())
    # A dedicated runtime initially lacking the practice input registers it once.
    r=WorkspaceRuntime(tmp_path/"v2"/"workspace"/"registered.sqlite3",procedures={k:v for k,v in entries.items() if k!="synthetic-practice-v2"})
    packet=RegistrationPacket(plan=plan,enrichment=enrichment,relationships=json.loads((folder/"overlay.json").read_text()))
    status=r.register_procedure(packet)
    assert status["status"]=="prepared" and r.register_procedure(packet)==status
    before=r.procedures["synthetic-practice-v2"]["document"]["structure_fingerprint"]
    path=tmp_path/"v2"/"workspace"/"registered.sqlite3";r.close()
    r=WorkspaceRuntime(path,procedures={k:v for k,v in entries.items() if k!="synthetic-practice-v2"})
    assert r.procedures["synthetic-practice-v2"]["document"]["structure_fingerprint"]==before
    pending=packet.model_copy(update={"relationships":packet.relationships.model_copy(update={"reviewer":"PENDING REVIEW"})})
    with pytest.raises(ValueError,match="pending"):r.register_procedure(pending)
    r.close()


def test_reviewed_publication_freezes_views_and_survives_restart(entries,tmp_path):
    from app.v2.preparation import approve
    path=tmp_path/"v2"/"workspace"/"wording.sqlite3"
    r=WorkspaceRuntime(path,procedures=entries);p=profile(r);j=start(r,p)
    old_document=copy.deepcopy(j["document"]);before=r.status()
    packet={"status":"pending","origin":"human_authored","overlay":entries["synthetic-practice-v2"]["overlay"].model_dump(mode="json")}
    packet["overlay"]["variants"][0]["title"]="Register with the fictional Registration Desk"
    with pytest.raises(ValueError,match="unreviewed"):r.publish_wording("synthetic-practice-v2",packet)
    approved=approve(entries["synthetic-practice-v2"]["graph"],packet,"test source reviewer")
    assert r.publish_wording("synthetic-practice-v2",approved)["status"]=="prepared"
    assert r.status()==before
    assert r.read(j["id"],j["token"])["document"]==old_document
    future=start(r,p)
    assert future["document"]["actions"][0]["title"]=="Register with the fictional Registration Desk"
    assert future["document"]["content_fingerprint"]!=old_document["content_fingerprint"]
    invalid=copy.deepcopy(packet);invalid["overlay"]["joins"]=[]
    bad=approve(entries["synthetic-practice-v2"]["graph"],invalid,"test source reviewer")
    with pytest.raises(ValueError,match="relationships"):r.publish_wording("synthetic-practice-v2",bad)
    expected=r.procedures["synthetic-practice-v2"]["document"]["content_fingerprint"];r.close()
    r=WorkspaceRuntime(path,procedures=entries)
    assert r.procedures["synthetic-practice-v2"]["document"]["content_fingerprint"]==expected
    assert r.read(j["id"],j["token"])["document"]==old_document
    r.close()


def test_map_size_events_have_real_view_scope_and_no_reward(entries):
    r=WorkspaceRuntime(procedures=entries);p=profile(r);j=start(r,p);token=j["token"]
    config=next(c for c in j["available_configurations"] if c["relationships"]=="map")
    r.adjust(j["id"],token,j["current_view"],Configuration(**config),str(uuid4()))
    current=r.read(j["id"],token);before=r.status()
    event={"event_id":str(uuid4()),"view_id":current["current_view"],"type":"map_expand"}
    first=r.event(j["id"],token,event);retry=r.event(j["id"],token,event)
    assert first==retry and r.status()==before and first["events"][-1]["reward"] is None
    r.close()


def test_changed_hard_requirements_retire_old_views_and_learning(entries):
    r=WorkspaceRuntime(procedures=entries);p=profile(r);sid=p["session"]["session_id"];j=start(r,p);display(r,j)
    before=r.status()
    revision=r.settings(sid)["settings_revision"]
    r.update_settings(sid,SettingsPatch(request_id=str(uuid4()),expected_revision=revision,locks={"relationships":"none"}))
    assert r.read(j["id"],j["token"])["constraints_revoked"]
    receipt=r.rate(j["id"],j["token"],j["root_view"],"about_right")
    assert not receipt["eligible"] and receipt["exclusion_reason"]=="constraints_changed" and r.status()==before
    fresh=start(r,p)
    assert fresh["views"][fresh["current_view"]]["configuration"]["relationships"]=="none"
    assert not fresh.get("constraints_revoked")
    with pytest.raises(ValueError,match="legacy"):
        r.update_settings(sid,SettingsPatch(request_id=str(uuid4()),expected_revision=r.settings(sid)["settings_revision"],context={"locks":{"presentation_mode":"GUIDED"}}))
    r.close()


def test_selected_option_join_cannot_turn_joint_requirements_into_alternatives(entries):
    from app.v2.content import validate_overlay
    from app.core.scaffolds import graph_fingerprint
    entry=entries["synthetic-practice-v2"]
    graph=entry["graph"].model_copy(update={"branch_groups":tuple(b.model_copy(update={"selection":"AND"}) for b in entry["graph"].branch_groups)})
    overlay=entry["overlay"].model_copy(update={"graph_fingerprint":graph_fingerprint(graph)})
    with pytest.raises(ValueError,match="XOR"):validate_overlay(graph,overlay)
