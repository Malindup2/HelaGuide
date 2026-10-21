"""Phase-one contracts only. Review records below are TEST declarations,
not publication or human review of the registered government examples.
"""
import copy
import json
from datetime import datetime, timezone
from pathlib import Path
import pytest
from app.core.procedure_input import load_procedure_input
from app.core.procedure_graph import build_procedure_graph
from app.guidance.sources import ProcedureSource
from app.guidance.content import GuidanceContent, validate_content
from app.guidance.catalogue import CATALOGUE, Configuration, Constraints
from app.guidance.feasibility import evaluate
from app.guidance.composition import compose
from app.guidance.decision import BaseScore, HistoryAdjustment, SelectionRecord
from app.v2.content import Overlay

ROOT=Path(__file__).resolve().parents[2]/'research'/'data'

def source(name='practice'):
    folder=ROOT/'v2'/'practice' if name=='practice' else ROOT/'official'/name
    graph=build_procedure_graph(load_procedure_input(folder/'plan.json',folder/'enrichment.json'))
    overlay=Overlay.model_validate_json((folder/'overlay.json').read_text()) if name=='practice' else None
    return ProcedureSource(graph=graph,relationships=overlay)


def fallback(src):
    g=src.graph;passages={c.content_id:c for c in g.content};claims=[];actions=[]
    for a in g.actions:
        ids=[]
        for i,cid in enumerate(a.required_content_ids):
            c=passages[cid];key=a.action_id+':claim:'+str(i);ids.append(key)
            claims.append({'id':key,'source_id':cid,'start':0,'end':len(c.text),'quote':c.text,'action_ids':[a.action_id],'required':True,'evidence_ids':list(c.evidence_ids)})
        raw='\n\n'.join(passages[c].text for c in a.required_content_ids)
        actions.append({'id':a.action_id,'heading':{'text':passages[a.required_content_ids[0]].text,'status':'source_fallback'},
            'essential':{'text':raw,'status':'source_fallback','claim_ids':ids},'visible_condition_ids':list(a.applicability.condition_ids)})
    return {'procedure_id':g.plan_id,'source_graph_fingerprint':src.graph_fingerprint,'relationship_fingerprint':src.relationship_fingerprint,
        'content_version':'test-only-1','origin':'source_preserving','source_limit':g.disclaimer,'claims':claims,'actions':actions}


def reviewed_payload(src):
    data=fallback(src);data['origin']='fictional_authored'
    for i,a in enumerate(data['actions']):
        evidence=data['claims'][0]['evidence_ids']
        a['heading']={'text':'Perform the fictional task '+str(i+1),'status':'reviewed','evidence_ids':evidence}
        a['heading_actionable']=True
        # Required passages are unchanged. Additional TEST wording requires an explicit review record.
        a['concise']={'status':'reviewed'}
        a['detailed']={'status':'reviewed','remainder':{'text':'TEST source-grounded clarification for action '+str(i+1),'status':'reviewed','evidence_ids':evidence},'remainder_role':'clarification','adds_information':True}
        a['recap']={'text':'Reminder of the fictional earlier task '+str(i+1),'status':'reviewed','evidence_ids':evidence}
    return seal(data,src)


def seal(data,src):
    data=copy.deepcopy(data);data.pop('review',None)
    checks=[];evidence=[e.evidence_id for e in src.graph.evidence]
    def check(target,field=None,claim_ids=(),evidence_ids=()):
        checks.append({'target':target,'claim_ids':list(field.get('claim_ids',[])) if field else list(claim_ids),
            'evidence_ids':list(dict.fromkeys((field.get('evidence_ids',[]) if field else list(evidence_ids))+evidence)),
            'result':'matched','note':'TEST fixture declaration only; no official approval'})
    for a in data['actions']:
        prefix='actions.'+a['id']
        for name in ('heading','essential','recap','actor','destination'):
            if (a.get(name) or {}).get('status')=='reviewed':check(prefix+'.'+name,a[name])
        for depth in ('concise','detailed'):
            exp=a.get(depth)
            if exp and exp.get('status')=='reviewed':check(prefix+'.'+depth)
            if exp and (exp.get('remainder') or {}).get('status')=='reviewed':check(prefix+'.'+depth+'.remainder',exp['remainder'])
    for f in data.get('attachments',[]):
        if f.get('status')=='reviewed':check('attachments.'+f['id'],claim_ids=f.get('claim_ids',[]),evidence_ids=f.get('evidence_ids',[]))
        if (f.get('qualification') or {}).get('status')=='reviewed':check('attachments.'+f['id']+'.qualification',f['qualification'])
    for p in data.get('phases',[]):
        if p['label'].get('status')=='reviewed':
            check('phases.'+p['id']+'.label',p['label']);check('phases.'+p['id'],evidence_ids=p['evidence_ids'])
    if data.get('phase_order'):check('phase_order',evidence_ids=data['phase_order_evidence_ids'])
    content=GuidanceContent.model_validate(data)
    data['review']={'status':'reviewed','reviewer':'internal TEST fixture reviewer','reviewed_at':datetime(2026,10,21,tzinfo=timezone.utc).isoformat(),
        'scope_note':'Synthetic contract test only','artifact_digest':content.fingerprint,'checks':checks}
    return data


def groups(data,src):
    data=copy.deepcopy(data);g=src.graph
    # Stage-based candidates become phases only through test review declarations.
    data['phases']=[{'id':'phase-'+str(i),'label':{'text':'Preparation area '+str(i+1),'status':'reviewed','evidence_ids':[g.evidence[0].evidence_id]},
        'action_ids':[a.action_id for a in g.actions if a.service_id==stage.service_id],'basis':'stage','why_grouped':'Shared fictional preparation purpose',
        'adds_orientation':True,'evidence_ids':[g.evidence[0].evidence_id]} for i,stage in enumerate(g.stages)]
    return seal(data,src)

@pytest.mark.parametrize('name',['birth_copy','nic_amendment','company_pack','practice'])
def test_exact_existing_sources_fallback_preserves_required_passages_and_scope(name):
    src=source(name);content=GuidanceContent.model_validate(fallback(src));validate_content(src,content)
    plan=compose(src,content,Configuration())
    assert plan['source_limit']==src.graph.disclaimer
    for a,rendered in zip(src.graph.actions,plan['actions']):
        assert all(c.text in rendered['essential'] for c in src.graph.content if c.content_id in a.required_content_ids)
        assert rendered['facts']==[]  # Mentions never become action payments.
    assert all(f['scope']=='stage' for f in plan['facts'])
    assert set(f['fact_id'] for f in plan['facts'])=={f.fact_id for f in src.graph.facts}
    if name!='practice':
        assert all(c.configuration.relationships!='map' for c in evaluate(src,content) if c.feasible)


def test_revised_catalogue_has_new_keys_and_rejects_old_values():
    assert len(CATALOGUE)==len({c.key for c in CATALOGUE})==96
    with pytest.raises(ValueError):Configuration(summary='on')
    with pytest.raises(ValueError):Configuration(explanation='expanded')
    with pytest.raises(ValueError):Configuration(disclosure='collapsed')


def test_pending_generated_words_do_not_reach_render_plan():
    src=source();data=fallback(src)
    data['origin']='provider_generated';data['actions'][0]['heading']={'text':'PENDING INVENTED HEADING','status':'draft'}
    data['actions'][0]['essential']['text']='PENDING INVENTED ESSENTIAL';data['actions'][0]['essential']['status']='draft'
    content=GuidanceContent.model_validate(data);plan=compose(src,content,Configuration())
    assert 'PENDING INVENTED' not in json.dumps(plan)
    for c in evaluate(src,content):
        if c.feasible:assert c.configuration.explanation=='concise' and c.configuration.disclosure=='off' and c.configuration.recap=='off' and c.configuration.segmentation=='off'


def test_depth_disclosure_combination_is_not_independent_boolean_capability():
    src=source();data=reviewed_payload(src);content=GuidanceContent.model_validate(data)
    valid=[c for c in evaluate(src,content) if c.feasible]
    assert any(c.configuration.explanation=='detailed' and c.configuration.disclosure=='on' for c in valid)
    assert not any(c.configuration.explanation=='concise' and c.configuration.disclosure=='on' for c in valid)
    assert any(c.configuration.explanation=='concise' and c.configuration.disclosure=='off' for c in valid)
    assert any(c.configuration.explanation=='detailed' and c.configuration.disclosure=='off' for c in valid)
    config=Configuration(explanation='detailed',disclosure='on')
    hidden=compose(src,content,config);visible=compose(src,content,config.model_copy(update={'disclosure':'off'}))
    for a,b in zip(hidden['actions'],visible['actions']):
        assert a['essential']==b['essential'] and a['conditions']==b['conditions'] and a['facts']==b['facts']
        assert a['explanation_hidden']==b['explanation_visible']


def test_one_safe_concise_remainder_enables_disclosure_without_count_threshold():
    src=source();data=reviewed_payload(src);a=data['actions'][0];evidence=[src.graph.evidence[0].evidence_id]
    a['concise']={'status':'reviewed','remainder':{'text':'TEST concise clarification','status':'reviewed','evidence_ids':evidence},'remainder_role':'clarification','adds_information':True}
    content=GuidanceContent.model_validate(seal(data,src));candidate=next(c for c in evaluate(src,content) if c.configuration==Configuration(disclosure='on'))
    assert candidate.feasible and candidate.disclosable_action_ids==(a['id'],)
    assert all(not r['explanation_hidden'] for r in compose(src,content,candidate.configuration)['actions'][1:])

@pytest.mark.parametrize('mutation',['gap','quote','required_remainder','condition','review_missing','tampered','mock','wrong_version','detailed_same','recap_label','actionable'])
def test_rejects_unsafe_content_and_false_review(mutation):
    src=source();data=reviewed_payload(src)
    if mutation=='gap':data['claims'][0]['start']=1;data['claims'][0]['quote']=data['claims'][0]['quote'][1:]
    if mutation=='quote':data['claims'][0]['quote']='not the source'
    if mutation=='required_remainder':data['actions'][0]['detailed']['remainder']['claim_ids']=[data['claims'][0]['id']]
    if mutation=='condition':next(a for a in data['actions'] if a['visible_condition_ids'])['visible_condition_ids']=[]
    if mutation=='review_missing':data.pop('review')
    if mutation=='tampered':data['actions'][0]['heading']['text']='Changed after review'
    if mutation=='mock':data['origin']='demo_mock'
    if mutation=='wrong_version':data['relationship_fingerprint']='wrong'
    if mutation=='detailed_same':data['actions'][0]['detailed']['remainder']=None;data['actions'][0]['detailed']['remainder_role']=None
    if mutation=='recap_label':data['actions'][0]['recap']['text']=data['actions'][0]['heading']['text']
    if mutation=='actionable':data['actions'][0]['heading_actionable']=False
    if mutation not in ('tampered','review_missing'):data=seal(data,src)
    with pytest.raises(ValueError):validate_content(src,GuidanceContent.model_validate(data))


def test_all_96_combinations_and_hard_constraints_with_reviewed_phase_fixture():
    src=source();data=groups(reviewed_payload(src),src)
    for a in data['actions']:
        a['concise']={'status':'reviewed','remainder':{'text':'TEST concise clarification '+a['id'],'status':'reviewed','evidence_ids':[src.graph.evidence[0].evidence_id]},'remainder_role':'clarification','adds_information':True}
    content=GuidanceContent.model_validate(seal(data,src));assert all(c.feasible for c in evaluate(src,content))
    constraints=Constraints(no_guided=True,no_map=True,no_disclosure=True,locks={'segmentation':'on'})
    valid=[c.configuration for c in evaluate(src,content,constraints) if c.feasible]
    assert valid and all(c.navigation=='overview' and c.relationships!='map' and c.disclosure=='off' and c.segmentation=='on' for c in valid)
    conflict=Constraints(no_guided=True,locks={'navigation':'guided'})
    assert not any(c.feasible for c in evaluate(src,content,conflict))

@pytest.mark.parametrize('mutation',['duplicate','missing','empty','trivial','unreviewed','backwards','unsupported_order','split_branch'])
def test_phase_integrity_meaning_and_order(mutation):
    src=source();data=groups(reviewed_payload(src),src)
    if mutation=='duplicate':data['phases'][0]['action_ids'].append(data['phases'][1]['action_ids'][0])
    if mutation=='missing':data['phases'][0]['action_ids']=[]
    if mutation=='empty':data['phases']=data['phases'][:1]
    if mutation=='trivial':data['phases'][0]['label']['text']=data['actions'][0]['heading']['text']
    if mutation=='unreviewed':data['phases'][0]['adds_orientation']=False
    if mutation in ('backwards','unsupported_order'):
        data['phase_order']=[p['id'] for p in data['phases']];data['phase_order_basis']='stage_edges';data['phase_order_evidence_ids']=[src.graph.evidence[0].evidence_id]
        if mutation=='backwards':data['phase_order'].reverse()
        else:data['phases'][0]['action_ids'],data['phases'][1]['action_ids']=data['phases'][1]['action_ids'],data['phases'][0]['action_ids']
    if mutation=='split_branch':
        branch=src.graph.branch_groups[0];aid=branch.options[0].action_ids[0]
        group=next(p for p in data['phases'] if aid in p['action_ids']);group['action_ids'].remove(aid);data['phases'][0]['action_ids'].append(aid)
    with pytest.raises(ValueError):validate_content(src,GuidanceContent.model_validate(seal(data,src)))


def test_reviewed_phase_order_and_plain_unordered_groups():
    src=source();data=groups(reviewed_payload(src),src);content=GuidanceContent.model_validate(data)
    assert compose(src,content,Configuration(segmentation='on'))['phase_order']==[]
    data['phase_order']=[p['id'] for p in data['phases']];data['phase_order_basis']='stage_edges';data['phase_order_evidence_ids']=[src.graph.evidence[0].evidence_id]
    validate_content(src,GuidanceContent.model_validate(seal(data,src)))


def test_selection_interface_exact_abstention_bound_and_feasible_set():
    ids=[c.key for c in CATALOGUE[:2]];base=(BaseScore(candidate_id=ids[0],sampled_score=.6),BaseScore(candidate_id=ids[1],sampled_score=.59))
    abstain=HistoryAdjustment(history_schema='unapproved-interface',cutoff_timestamp='2026-10-21T00:00:00Z',abstained=True,reasons=('not_implemented',))
    record=SelectionRecord(encoder_schema='unapproved',feasible_candidate_ids=tuple(ids),base_scores=base,base_winner=ids[0],history=abstain,selected_candidate=ids[0])
    assert record.selected_candidate==record.base_winner
    with pytest.raises(ValueError):
        HistoryAdjustment(**{**abstain.model_dump(),'adjustments':{ids[1]:.01}})
    # Test supplied arithmetic only. This chooses no production bound or estimator.
    active=HistoryAdjustment(history_schema='test-only',cutoff_timestamp='2026-10-21T00:00:00Z',abstained=False,reasons=(),evidence_ids=('test-evidence',),bound=.02,adjustments={ids[1]:.02},gates=tuple({'name':name,'outcome':'passed','reason':'TEST declaration only'} for name in ('relevance','consistency','uncertainty')))
    SelectionRecord(encoder_schema='test-only',feasible_candidate_ids=tuple(ids),base_scores=base,base_winner=ids[0],history=active,selected_candidate=ids[1])
    for changes in ({'adjustments':{'infeasible':.01}},{'adjustments':{ids[1]:.03}}):
        with pytest.raises(ValueError):
            h=HistoryAdjustment(**{**active.model_dump(),**changes});SelectionRecord(**{**record.model_dump(),'history':h})


@pytest.mark.parametrize('scope',['action','route','stage','service'])
def test_explicit_fee_attribution_preserves_source_value_and_scope(scope):
    src=source();data=reviewed_payload(src);g=src.graph
    stage=g.stages[0];aid=next(a.action_id for a in g.actions if a.service_id==stage.service_id)
    evidence=[g.evidence[0].evidence_id]
    attachment={'id':'test-fee','fact_id':stage.fee_fact_id,'scope':scope,'status':'reviewed','evidence_ids':evidence}
    if scope=='action':
        attachment['action_id']=aid
        next(a for a in data['actions'] if a['id']==aid)['visible_attachment_ids']=['test-fee']
    if scope=='stage':attachment['stage_id']=stage.service_id
    if scope=='service':attachment['service_id']=g.requested_service_id
    if scope=='route':
        branch=g.branch_groups[0];option=branch.options[0]
        attachment.update(branch_id=branch.group_id,option_ids=[option.option_id],condition_ids=list(option.condition_ids))
    data['attachments']=[attachment]
    content=GuidanceContent.model_validate(seal(data,src));plan=compose(src,content,Configuration())
    rendered=next(f for f in plan['facts'] if f['id']=='test-fee')
    assert rendered['scope']==scope and rendered['fact']==next(f.model_dump(mode='json') for f in g.facts if f.fact_id==stage.fee_fact_id)
    assert len([f for f in plan['facts'] if f['fact_id']==stage.fee_fact_id])==1
    assert sum(bool(a['facts']) for a in plan['actions'])==(1 if scope=='action' else 0)
    assert 'total' not in plan
    if scope=='route':assert rendered['conditions']


@pytest.mark.parametrize('mutation',['pending_action_scope','wrong_stage','wrong_action','route_condition','service_target','mixed_targets','instruction_in_fee'])
def test_fee_scopes_cannot_be_inferred_or_silently_changed(mutation):
    src=source();data=reviewed_payload(src);g=src.graph;s=g.stages[0]
    a=next(a for a in g.actions if a.service_id==s.service_id)
    f={'id':'fee','fact_id':s.fee_fact_id,'scope':'stage','stage_id':s.service_id,'status':'reviewed','evidence_ids':[g.evidence[0].evidence_id]}
    if mutation=='pending_action_scope':f.update(scope='action',action_id=a.action_id,status='source_fallback');f.pop('stage_id')
    if mutation=='wrong_stage':f['stage_id']=g.stages[-1].service_id
    if mutation=='wrong_action':f.update(scope='action',action_id=next(a.action_id for a in g.actions if a.service_id!=s.service_id));f.pop('stage_id')
    if mutation=='route_condition':
        b=g.branch_groups[0];f.update(scope='route',branch_id=b.group_id,option_ids=[b.options[0].option_id]);f.pop('stage_id')
    if mutation=='service_target':f.update(scope='service',service_id='wrong');f.pop('stage_id')
    if mutation=='mixed_targets':f['action_id']=a.action_id
    if mutation=='instruction_in_fee':f['claim_ids']=[data['claims'][0]['id']]
    data['attachments']=[f]
    with pytest.raises(ValueError):validate_content(src,GuidanceContent.model_validate(seal(data,src)))


def test_draft_destination_cannot_count_as_visible_required_coverage():
    src=source();data=reviewed_payload(src);action=data['actions'][0];claim=next(c for c in data['claims'] if action['id'] in c['action_ids'])
    action['essential']={'text':'TEST incomplete essential','status':'reviewed','evidence_ids':claim['evidence_ids']}
    action['destination']={'text':'PENDING destination','status':'draft','claim_ids':[claim['id']]}
    with pytest.raises(ValueError):validate_content(src,GuidanceContent.model_validate(seal(data,src)))


def test_named_statement_review_and_source_fingerprint_are_mandatory():
    src=source();data=reviewed_payload(src)
    data['review']['checks']=[c for c in data['review']['checks'] if c['target']!='actions.'+data['actions'][0]['id']+'.heading']
    with pytest.raises(ValueError):validate_content(src,GuidanceContent.model_validate(data))
    data=reviewed_payload(src);data['source_graph_fingerprint']='stale'
    with pytest.raises(ValueError):validate_content(src,GuidanceContent.model_validate(seal(data,src)))


def test_four_depth_disclosure_combinations_keep_every_essential_fact():
    src=source();data=reviewed_payload(src)
    for a in data['actions']:
        a['concise']={'status':'reviewed','remainder':{'text':'TEST concise extra '+a['id'],'status':'reviewed','evidence_ids':[src.graph.evidence[0].evidence_id]},'remainder_role':'clarification','adds_information':True}
    content=GuidanceContent.model_validate(seal(data,src));plans=[compose(src,content,Configuration(explanation=d,disclosure=v)) for d in ('concise','detailed') for v in ('off','on')]
    for plan in plans:
        assert plan['facts']==plans[0]['facts']
        assert [(a['essential'],a['conditions'],a['destination']) for a in plan['actions']]==[(a['essential'],a['conditions'],a['destination']) for a in plans[0]['actions']]
    assert plans[0]['actions'][0]['explanation_visible']!=plans[2]['actions'][0]['explanation_visible']
    assert plans[1]['actions'][0]['explanation_hidden'] and plans[3]['actions'][0]['explanation_hidden']


@pytest.mark.parametrize('gate_state',['missing','failed','not_assessed','duplicate'])
def test_history_interface_rejects_active_adjustment_without_passed_gates(gate_state):
    gates=[{'name':name,'outcome':'passed','reason':'TEST declaration only'} for name in ('relevance','consistency','uncertainty')]
    if gate_state=='missing':gates.pop()
    elif gate_state=='duplicate':gates.append(gates[0])
    else:gates[0]['outcome']=gate_state
    with pytest.raises(ValueError):
        HistoryAdjustment(history_schema='test-only',cutoff_timestamp='2026-10-21T00:00:00Z',abstained=False,reasons=(),evidence_ids=('test-only',),bound=.02,adjustments={},gates=gates)
