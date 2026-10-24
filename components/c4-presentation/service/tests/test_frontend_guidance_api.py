"""Revised frontend API integration; no model training or live providers."""
import copy
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from app.host.application import create_app
from app.host.identity import WorkspaceRuntime
from app.procedures.registration import workspace_registry

ROOT='/workspace/guidance'
PID='synthetic-practice-v2'
RICH={'navigation':'guided','explanation':'detailed','disclosure':'on','relationships':'map','recap':'on','segmentation':'on'}
TOKEN='test-only-capability-not-a-real-user-secret-'+('x'*16)

@pytest.fixture(scope='module')
def entries():return workspace_registry()

@pytest.fixture
def running(tmp_path,entries):
    runtime=WorkspaceRuntime(procedures=entries)
    options={'directory':tmp_path/'prepared-content','demo_fixtures':True}
    with TestClient(create_app(runtime=runtime,workspace=True,prepared_content_options=options,guidance_api_options={'research_enabled':True})) as client:
        yield client,runtime
    runtime.close()


def guest(client):
    response=client.post(ROOT+'/guests');assert response.status_code==200,response.text
    return response.json()['session_id']


def request(client,sid,pid=PID,config=None,**changes):
    body={'request_id':str(uuid4()),'session_id':sid,'procedure_id':pid,'capability_token':TOKEN,**changes}
    url=ROOT+'/requests'
    if config is not None:
        url=ROOT+'/research/previews';body.update(mode='research_preview',configuration=config)
    return client.post(url,json=body)


def event(client,j,type,**data):
    return client.post(ROOT+'/journeys/'+j['journey_id']+'/events',headers={'X-C4-Token':TOKEN},json={'event_id':str(uuid4()),'view_id':j['view_id'],'type':type,**data})


def read(client,j):return client.get(ROOT+'/journeys/'+j['journey_id'],headers={'X-C4-Token':TOKEN})


@pytest.mark.parametrize('pid',['official-birth_copy-v3','official-nic_amendment-v3','official-company_pack-v3','synthetic-linear-v1','synthetic-conditional-v1','synthetic-parallel-v1',PID])
def test_guest_complete_source_grounded_guidance(running,pid):
    client,r=running;sid=guest(client);before=r.status();rng=copy.deepcopy(r.state['rng'])
    response=request(client,sid,pid);assert response.status_code==200,response.text
    j=response.json();doc=j['document'];graph=r.procedures[pid]['graph']
    passages={c.content_id:c.text for c in graph.content}
    assert j['selection']['kind']=='standard' and j['selection']['policy'] is None
    assert not any(j['controls'][k] for k in ('feedback','configuration_adjustment'))
    assert all(a['recap'] is None for a in doc['actions'])
    for original,rendered in zip(graph.actions,doc['actions']):
        assert all(passages[c] in rendered['essential'] for c in original.required_content_ids)
        assert rendered['condition_ids']==list(original.applicability.condition_ids)
    assert len(doc['facts'])==len(graph.facts) and all(f['scope']=='stage' for f in doc['facts'])
    assert doc['source_limit']==graph.disclaimer and doc['requirements']['total'] is None
    assert r.status()==before and r.state['rng']==rng
    assert read(client,j).status_code==200


def test_all_feasible_combinations_render_without_fabricating_policy(running):
    client,r=running;sid=guest(client);before=r.status()
    for pid,count in [(PID,96),('synthetic-conditional-v1',96),('synthetic-parallel-v1',96),('synthetic-linear-v1',48),('official-birth_copy-v3',4),('official-nic_amendment-v3',4),('official-company_pack-v3',4)]:
        availability=client.get(ROOT+'/procedures/'+pid+'/availability',params={'session_id':sid}).json()
        assert availability['nominal_count']==96 and availability['feasible_count']==count
        for candidate in availability['candidates']:
            if pid.startswith('official-') and not candidate['feasible']:continue
            response=request(client,sid,pid,candidate['configuration'])
            if not candidate['feasible']:
                assert response.status_code==422 and response.json()['detail']['reasons']
                continue
            assert response.status_code==200,response.text
            j=response.json();assert j['selection']['kind']=='research_preview'
            assert j['selection']['configuration']==candidate['configuration'] and j['selection']['policy'] is None
            assert j['interaction']['recap']['items']==[]
    assert r.status()==before and not r.state['decisions']


def test_unavailable_official_variants_are_rejected_not_silently_replaced(running):
    client,r=running;sid=guest(client)
    for dimension,value in [('explanation','detailed'),('relationships','map'),('recap','on'),('segmentation','on'),('disclosure','on')]:
        config={'navigation':'overview','explanation':'concise','disclosure':'off','relationships':'none','recap':'off','segmentation':'off',dimension:value}
        response=request(client,sid,'official-nic_amendment-v3',config)
        assert response.status_code==422 and response.json()['detail']['code']=='infeasible_configuration'
    assert request(client,sid,'official-nic_amendment-v3').json()['preparation']['content_state']=='source_fallback'


def test_personalized_path_cannot_reuse_v2_policy(running):
    client,r=running;sid=guest(client);before=r.status();rng=copy.deepcopy(r.state['rng'])
    result=request(client,sid,mode='personalized')
    assert result.status_code==503 and result.json()['detail']['code']=='revised_policy_unavailable'
    assert r.status()==before and r.state['rng']==rng and not r.state['decisions']
    status=client.get(ROOT+'/status').json()
    assert status['policy'] is None and not status['personalized_selection_available']
    assert status['history_adjustment']=='deferred_to_PP2'


def test_profile_reuse_two_procedures_and_revised_preferences(running):
    client,r=running;before=r.status()
    body={'profile_id':'profile:'+uuid4().hex,'display_name':'Research example','personalization_enabled':True,
          'initial_context':{'navigation_capability':2,'familiarity':[{'service_id':'svc:birth_copy','score':1},{'service_id':'svc:nic_amendment','score':5}]}}
    p=client.post(ROOT+'/profiles',json=body);assert p.status_code==200,p.text
    sid=p.json()['session']['session_id']
    one=client.get(ROOT+'/context/'+sid,params={'procedure_id':'official-birth_copy-v3'}).json()
    two=client.get(ROOT+'/context/'+sid,params={'procedure_id':'official-nic_amendment-v3'}).json()
    assert one['familiarity']==1 and two['familiarity']==5 and one['confidence']==two['confidence']==2
    patch={'request_id':str(uuid4()),'expected_revision':one['revision'],'preferences':{'segmentation':'on','explanation':'detailed'},'accessibility':{'no_map':True}}
    assert client.patch(ROOT+'/context/'+sid,json=patch).status_code==200
    context=client.get(ROOT+'/context/'+sid,params={'procedure_id':PID}).json()
    assert context['preferences']==patch['preferences'] and context['constraints']['no_map']
    assert request(client,sid,config=RICH).status_code==422
    assert client.get(ROOT+'/profiles').status_code==200
    assert r.status()==before


def test_accessibility_cannot_be_relaxed_and_conflicting_locks_fail(running):
    client,r=running;sid=guest(client)
    ctx=client.get(ROOT+'/context/'+sid,params={'procedure_id':PID}).json()
    patch={'request_id':str(uuid4()),'expected_revision':ctx['revision'],'accessibility':{'no_map':True,'no_guided':True,'no_disclosure':True}}
    assert client.patch(ROOT+'/context/'+sid,json=patch).status_code==200
    for override in ({},{'constraints':{'no_map':False,'no_guided':False,'no_disclosure':False}}):
        assert request(client,sid,config=RICH,context=override).status_code==422
    ctx=client.get(ROOT+'/context/'+sid,params={'procedure_id':PID}).json()
    patch={'request_id':str(uuid4()),'expected_revision':ctx['revision'],'locks':{'navigation':'guided'}}
    client.patch(ROOT+'/context/'+sid,json=patch)
    result=request(client,sid)
    assert result.status_code==409 and result.json()['detail']['code']=='no_feasible_configuration'


def test_actual_visits_gate_guided_recap_and_opening_details_is_not_reading(running):
    client,r=running;sid=guest(client);j=request(client,sid,config=RICH).json()
    assert j['interaction']['recap']['items']==[]
    register='action:register_application';form='action:prepare_form';submit='action:submit_application'
    assert event(client,j,'view_displayed',action_ids=[register]).status_code==200
    assert event(client,j,'explanation_open',action_id=register).status_code==200
    assert event(client,j,'navigate',action_id=submit).status_code==200
    assert read(client,j).json()['interaction']['recap']['items']==[]
    assert event(client,j,'step_open',action_id=register).status_code==200
    assert event(client,j,'navigate',action_id=form).status_code==200
    assert event(client,j,'navigate',action_id=submit).status_code==200
    items=read(client,j).json()['interaction']['recap']['items']
    assert {x['action_id'] for x in items}=={register,form}
    assert all(x['viewed_not_completed'] and x['text'] for x in items)
    assert all(x['action_id']!='action:prepare_copy' for x in items)


def test_overview_recap_requires_viewport_and_raw_visibility_is_not_auto_reading(running):
    client,r=running;sid=guest(client);config={**RICH,'navigation':'overview'};j=request(client,sid,config=config).json()
    register='action:register_application';submit='action:submit_application'
    event(client,j,'step_visible',action_id=register,visible_ratio=1.0,dwell_ms=5000,instrumentation_version='unapproved-client-value')
    event(client,j,'navigate',action_id=submit);event(client,j,'viewport_changed',action_ids=[submit])
    assert read(client,j).json()['interaction']['recap']['items']==[]
    event(client,j,'step_open',action_id=register);event(client,j,'navigate',action_id=submit)
    assert read(client,j).json()['interaction']['recap']['items']
    event(client,j,'viewport_changed',action_ids=[register,submit])
    assert read(client,j).json()['interaction']['recap']['items']==[]


def test_nic_route_choice_local_numbering_and_active_route_changes(running):
    client,r=running;sid=guest(client)
    config={'navigation':'guided','explanation':'concise','disclosure':'off','relationships':'inline','recap':'off','segmentation':'off'}
    j=request(client,sid,'official-nic_amendment-v3',config).json()
    nav=j['document']['navigation'];assert nav['active_action_id'] is None and nav['unresolved_route_ids']
    branch=j['document']['routes'][0];first,second=branch['options']
    assert event(client,j,'route_focus',branch_id=branch['branch_id'],option_ids=[first['option_id'],second['option_id']]).status_code==422
    assert event(client,j,'route_focus',branch_id=branch['branch_id'],option_ids=[second['option_id']]).status_code==200
    current=read(client,j).json();assert set(current['document']['navigation']['browsing_action_ids'])==set(second['action_ids'])
    assert all(x['route_layer'] in (1,2) for x in current['document']['navigation']['entries'] if x['available_for_navigation'])
    assert event(client,j,'route_focus',branch_id=branch['branch_id'],option_ids=[first['option_id']]).status_code==200
    assert set(read(client,j).json()['document']['navigation']['browsing_action_ids'])==set(first['action_ids'])


def test_manual_child_and_feedback_are_never_learning(running):
    client,r=running;sid=guest(client);j=request(client,sid,config=RICH).json();before=r.status()
    result=client.post(ROOT+'/journeys/'+j['journey_id']+'/views',headers={'X-C4-Token':TOKEN},json={'request_id':str(uuid4()),'parent_view_id':j['view_id'],'configuration':{**RICH,'navigation':'overview'}})
    assert result.status_code==200,result.text
    child=result.json();assert child['parent_view_id']==j['view_id'] and child['selection']['kind']=='manual_adjustment'
    rating={'event_id':str(uuid4()),'view_id':child['view_id'],'rating':'fits'}
    response=client.post(ROOT+'/journeys/'+j['journey_id']+'/ratings',headers={'X-C4-Token':TOKEN},json=rating)
    assert response.status_code==200 and response.json()['reward'] is None and not response.json()['policy_updated']
    assert client.post(ROOT+'/journeys/'+j['journey_id']+'/ratings',headers={'X-C4-Token':TOKEN},json=rating).json()==response.json()
    standard=request(client,sid).json()
    assert client.post(ROOT+'/journeys/'+standard['journey_id']+'/ratings',headers={'X-C4-Token':TOKEN},json={**rating,'view_id':standard['view_id']}).status_code==403
    assert r.status()==before


def test_events_idempotent_scoped_and_inspector_factual(running):
    client,r=running;sid=guest(client);j=request(client,sid,config=RICH).json()
    path=ROOT+'/journeys/'+j['journey_id'];headers={'X-C4-Token':TOKEN}
    body={'event_id':str(uuid4()),'view_id':j['view_id'],'type':'step_open','action_id':'action:register_application'}
    a=client.post(path+'/events',headers=headers,json=body);assert a.status_code==200
    assert client.post(path+'/events',headers=headers,json=body).json()==a.json()
    assert client.post(path+'/events',headers=headers,json={**body,'action_id':'action:submit_application'}).status_code==409
    assert client.post(path+'/events',headers=headers,json={**body,'event_id':str(uuid4()),'features':[1,2]}).status_code==422
    assert client.get(path,headers={'X-C4-Token':'wrong'}).status_code==403
    trace=client.get(path+'/inspector',headers=headers).json()
    assert len(trace['events'])==1 and trace['features'] is None and trace['sampled_scores'] is None and trace['policy'] is None
    assert trace['posterior_updates']==0 and trace['scoring_status']=='not_run'
    assert trace['effective_context']['session_id']!=sid



def test_four_depth_disclosure_combinations_preserve_essentials(running):
    client,r=running;sid=guest(client);docs=[]
    for depth in ('concise','detailed'):
        for disclosure in ('off','on'):
            docs.append(request(client,sid,config={**RICH,'explanation':depth,'disclosure':disclosure}).json()['document'])
    for doc in docs:
        assert [a['essential'] for a in doc['actions']]==[a['essential'] for a in docs[0]['actions']]
        assert doc['facts']==docs[0]['facts'] and doc['requirements']['total'] is None
    assert docs[0]['actions'][0]['explanation_visible']!=docs[2]['actions'][0]['explanation_visible']
    assert docs[1]['actions'][0]['explanation_hidden'] and docs[3]['actions'][0]['explanation_hidden']


def test_parallel_and_join_cues_are_source_derived(running):
    client,r=running;sid=guest(client);doc=request(client,sid,config=RICH).json()['document']
    assert doc['joins']==[x.model_dump(mode='json') for x in r.procedures[PID]['overlay'].joins]
    assert doc['joins'][0]['requirement']['kind']=='all_of' and doc['parallel_areas']
    assert doc['relationship_aid']['map']['text_equivalent']
    aid=request(client,sid,config={**RICH,'relationships':'inline'}).json()['document']['relationship_aid']
    assert not any(c['kind']=='parallel_area' for c in aid['inline_by_action']['action:register_application'])
    assert any(c['kind']=='parallel_area' for c in aid['inline_by_action']['action:prepare_form'])


def test_recap_excludes_other_route_after_choice_changes(running):
    client,r=running;sid=guest(client);j=request(client,sid,config=RICH).json()
    branch=j['document']['routes'][0];first,second=branch['options']
    event(client,j,'route_focus',branch_id=branch['branch_id'],option_ids=[first['option_id']])
    assert event(client,j,'step_open',action_id=first['action_ids'][0]).status_code==200
    event(client,j,'route_focus',branch_id=branch['branch_id'],option_ids=[second['option_id']])
    event(client,j,'navigate',action_id='action:submit_application')
    assert not {x['action_id'] for x in read(client,j).json()['interaction']['recap']['items']} & set(first['action_ids'])


def test_idempotency_and_unknown_requests(running):
    client,r=running;sid=guest(client);rid=str(uuid4())
    one=request(client,sid,request_id=rid);two=request(client,sid,request_id=rid)
    assert one.status_code==200 and one.json()==two.json()
    assert request(client,sid,'synthetic-linear-v1',request_id=rid).status_code==409
    assert request(client,sid,'missing-procedure').status_code==404
    assert request(client,'missing-session').status_code==404
    assert request(client,sid,config={**RICH,'summary':'on'}).status_code==422


def test_hard_constraint_changes_retire_existing_view(running):
    client,r=running;sid=guest(client);j=request(client,sid,config=RICH).json()
    ctx=client.get(ROOT+'/context/'+sid,params={'procedure_id':PID}).json()
    patch={'request_id':str(uuid4()),'expected_revision':ctx['revision'],'accessibility':{'no_map':True}}
    assert client.patch(ROOT+'/context/'+sid,json=patch).status_code==200
    response=read(client,j)
    assert response.status_code==409 and response.json()['detail']['code']=='hard_requirements_changed'
    assert event(client,j,'map_expand').status_code==409


def test_legacy_locks_require_explicit_review(running):
    client,r=running
    p=client.post(ROOT+'/profiles',json={'profile_id':'profile:'+uuid4().hex,'display_name':'Legacy requirement',
        'initial_context':{'locks':{'progressive_disclosure':True}}})
    assert p.status_code==200,p.text
    sid=p.json()['session']['session_id']
    ctx=client.get(ROOT+'/context/'+sid,params={'procedure_id':PID}).json()
    assert ctx['legacy']['hard_requirements_unresolved'] and request(client,sid).status_code==409
    patch={'request_id':str(uuid4()),'expected_revision':ctx['revision'],'locks':{'disclosure':'off'},'legacy_lock_fingerprint':ctx['legacy']['lock_fingerprint']}
    assert client.patch(ROOT+'/context/'+sid,json=patch).status_code==200
    assert request(client,sid).status_code==200



def test_profile_context_updates_are_reused(running):
    client,r=running;sid=guest(client);ctx=client.get(ROOT+'/context/'+sid,params={'procedure_id':PID}).json()
    response=client.patch(ROOT+'/profile-context/'+sid,json={'request_id':str(uuid4()),'expected_identity_revision':ctx['revision']['identity'],
        'confidence':1,'familiarity':[{'service_id':'svc:demo_submission','score':5}]})
    assert response.status_code==200,response.text
    one=request(client,sid).json();two=request(client,sid).json()
    assert one['effective_context']['confidence']==two['effective_context']['confidence']==1
    assert one['effective_context']['familiarity']==two['effective_context']['familiarity']==5


def test_opt_in_research_gate_and_openapi(tmp_path,entries):
    r=WorkspaceRuntime(procedures=entries)
    with TestClient(create_app(runtime=r,workspace=True)) as client:
        assert client.get(ROOT+'/status').status_code==404
    with TestClient(create_app(runtime=r,workspace=True,prepared_content_options={'directory':tmp_path/'prepared-content','demo_fixtures':True},guidance_api_options={})) as client:
        sid=guest(client);assert request(client,sid,config=RICH).status_code==403
        j=request(client,sid).json()
        assert client.get(ROOT+'/journeys/'+j['journey_id']+'/inspector',headers={'X-C4-Token':TOKEN}).status_code==403
        schema=client.get('/openapi.json').json()
        assert 'GuidanceResponse' in schema['components']['schemas'] and 'PreviewGuidance' in schema['components']['schemas']
    r.close()


def test_explicit_test_visibility_policy_can_qualify_viewed_content(tmp_path,entries):
    r=WorkspaceRuntime(procedures=entries)
    policy={'version':'test-only-visibility','min_visible_ratio':.5,'min_dwell_ms':10}
    with TestClient(create_app(runtime=r,workspace=True,prepared_content_options={'directory':tmp_path/'prepared-content','demo_fixtures':True},guidance_api_options={'research_enabled':True,'visibility_policy':policy})) as client:
        sid=guest(client);j=request(client,sid,config=RICH).json();before=r.status()
        assert event(client,j,'step_visible',action_id='action:register_application',visible_ratio=.75,dwell_ms=11,instrumentation_version=policy['version']).status_code==200
        event(client,j,'navigate',action_id='action:submit_application')
        items=read(client,j).json()['interaction']['recap']['items']
        assert len(items)==1 and items[0]['evidence']['kind']=='step_visible' and items[0]['viewed_not_completed']
        assert r.status()==before
    r.close()


def test_journey_events_restore_after_backend_restart(tmp_path,entries):
    path=tmp_path/'v2'/'workspace'/'api.sqlite3'
    options={'directory':tmp_path/'prepared-content','demo_fixtures':True}
    kwargs={'path':path,'workspace':True,'runtime_class':lambda path,**kw: WorkspaceRuntime(path,procedures=entries,**kw),'prepared_content_options':options,'guidance_api_options':{'research_enabled':True}}
    with TestClient(create_app(**kwargs)) as client:
        sid=guest(client);j=request(client,sid,config=RICH).json()
        event(client,j,'step_open',action_id='action:register_application')
        before=client.app.state.runtime.status();frozen=read(client,j).json()
    with TestClient(create_app(**kwargs)) as client:
        assert read(client,j).json()==frozen
        assert client.app.state.runtime.status()==before
        trace=client.get(ROOT+'/journeys/'+j['journey_id']+'/inspector',headers={'X-C4-Token':TOKEN}).json()
        assert len(trace['events'])==1 and trace['policy'] is None



def test_standard_constraints_do_not_turn_soft_preferences_into_rules(running):
    client,r=running;sid=guest(client);ctx=client.get(ROOT+'/context/'+sid,params={'procedure_id':PID}).json()
    patch={'request_id':str(uuid4()),'expected_revision':ctx['revision'],'preferences':{'segmentation':'on','explanation':'detailed'}}
    client.patch(ROOT+'/context/'+sid,json=patch)
    j=request(client,sid).json()
    assert j['selection']['configuration']['segmentation']=='off' and j['selection']['configuration']['explanation']=='concise'
    ctx=client.get(ROOT+'/context/'+sid,params={'procedure_id':PID}).json()
    client.patch(ROOT+'/context/'+sid,json={'request_id':str(uuid4()),'expected_revision':ctx['revision'],'locks':{'relationships':'inline'}})
    j=request(client,sid).json()
    assert j['selection']['kind']=='constraint_standard' and j['selection']['configuration']['relationships']=='inline' and j['selection']['policy'] is None


def test_telemetry_opportunity_is_not_visibility_or_reward(running):
    client,r=running;sid=guest(client);j=request(client,sid,config=RICH).json()
    assert event(client,j,'explanation_open',action_id='action:register_application').status_code==200
    trace=client.get(ROOT+'/journeys/'+j['journey_id']+'/inspector',headers={'X-C4-Token':TOKEN}).json()
    e=trace['events'][0]
    assert e['opportunity']['available_not_proof_of_visibility']
    assert not e['opportunity']['essential_display_acknowledged_before_event'] and not e['qualifies_for_recap']
    assert e['reward'] is None and not e['policy_updated']


def test_journey_checksum_blocks_stored_document_tampering(running):
    client,r=running;sid=guest(client);j=request(client,sid).json()
    with client.app.state.guidance_api.store.transaction() as db:
        db.execute('UPDATE journeys SET body=? WHERE id=?',('{"invented":"fake model scores"}',j['journey_id']))
    assert read(client,j).status_code==422



def test_availability_get_does_not_enqueue_or_trigger_preparation(running):
    client,r=running;sid=guest(client);processor=client.app.state.prepared_content.processor
    assert processor.jobs()==[]
    response=client.get(ROOT+'/procedures/official-nic_amendment-v3/availability',params={'session_id':sid})
    assert response.status_code==200 and response.json()['preparation']['content_state']=='source_fallback'
    assert processor.jobs()==[]
    assert request(client,sid,'official-nic_amendment-v3').status_code==200
    assert len(processor.jobs())==1



def test_unavailable_personalized_request_never_schedules_generation(running):
    client,r=running;sid=guest(client);processor=client.app.state.prepared_content.processor
    assert processor.jobs()==[]
    response=request(client,sid,'official-nic_amendment-v3',mode='personalized')
    assert response.status_code==503 and processor.jobs()==[]
