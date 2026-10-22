"""Prepared guidance with opt-in PP1 selection and atomic attributed rewards."""
import copy
import hashlib
import hmac
import json
from datetime import datetime, timezone
from uuid import uuid4
from app.guidance.catalogue import CATALOGUE, Configuration, Constraints
from app.guidance.flavours import FLAVOUR_30
from app.guidance.frontend_contracts import GuidanceResponse, RequestContext, Selection
from app.guidance.frontend_presentation import render, navigation, interaction_projection, eligible_ids
from app.guidance.journey_store import JourneyStore
from app.guidance.sources import ProcedureSource, digest
from app.v2.measurements import measurements


def now():return datetime.now(timezone.utc).isoformat()
def doc_fingerprint(content):return content.fingerprint if content else None
def token_hash(value):return hashlib.sha256(value.encode()).hexdigest()

class ApiFailure(Exception):
    def __init__(self,status,code,message,**details):
        self.status=status;self.detail={'code':code,'message':message,**details}
        super().__init__(message)

class GuidanceAPI:
    def __init__(self,prepared,*,research_enabled=False,visibility_policy=None,policy_options=None,experiment_directory=None,flavour=None):
        self.prepared=prepared;self.runtime=prepared.runtime;self.research_enabled=research_enabled
        self.flavour=flavour or FLAVOUR_30
        if self.flavour is not getattr(prepared,'flavour',FLAVOUR_30):raise ValueError('guidance API and prepared content must use the same content schema')
        self.store=JourneyStore(prepared.registry.directory/'frontend-api')
        self.policy = None
        self.experiment_directory = experiment_directory
        if policy_options is not None:
            if not self.flavour.supports_policy:raise ValueError('no PP1 policy is compatible with content schema '+self.flavour.content_schema+'; a fresh policy with a matching manifest must be trained first')
            from app.guidance.policy import PolicyStore
            self.policy = PolicyStore(**policy_options,profile=self.flavour.policy_profile)
        self.visibility_policy=visibility_policy
        if visibility_policy is not None:
            if set(visibility_policy)!={'version','min_visible_ratio','min_dwell_ms'} or not visibility_policy['version'] or not 0<visibility_policy['min_visible_ratio']<=1 or visibility_policy['min_dwell_ms']<=0:
                raise ValueError('explicit positive versioned visibility instrumentation policy required')

    def source(self,pid):
        if pid not in self.runtime.procedures:raise ApiFailure(404,'unknown_procedure','Select a registered procedure.')
        return self.prepared.source(pid)

    def _saved(self,sid):
        try:return self.runtime.settings(sid)
        except ValueError:raise ApiFailure(404,'unknown_session','Create or select a workspace session first.')

    def context(self,sid,pid,overrides=None,db=None):
        if db is None:
            with self.store.transaction() as connection:return self.context(sid,pid,overrides,connection)
        source=self.source(pid);saved=self._saved(sid);native=self.store.settings(db,sid)
        session=self.runtime.session(sid);access=session.settings.accessibility
        raw_locks={'native_or_mapped':saved['locks'],'unresolved_legacy':{k:v for k,v in saved['legacy_review'].items() if k.startswith('locks.')}}
        has_old_locks=any(raw_locks.values());fingerprint=digest(raw_locks) if has_old_locks else None
        unresolved=has_old_locks and native.get('legacy_lock_ack')!=fingerprint
        request=overrides or RequestContext();locks=dict(native['locks'])
        for key,value in request.constraints.locks.items():
            if key in locks and locks[key]!=value:raise ApiFailure(409,'saved_lock_conflict','A request cannot relax or replace a saved hard lock.',dimension=key)
            locks[key]=value
        extra=native['accessibility']
        constraints=Constraints(locks=locks,no_guided=not access.allow_guided_navigation or extra.get('no_guided',False) or request.constraints.no_guided,
            no_map=not access.allow_relationship_visuals or extra.get('no_map',False) or request.constraints.no_map,
            no_disclosure=not access.allow_collapsed_content or extra.get('no_disclosure',False) or request.constraints.no_disclosure)
        profile=next((p for p in self.runtime.profiles.values() if p.session_id==sid),None)
        service_id=source.graph.requested_service_id
        return {'schema_version':'c4-effective-guidance-context-1.0','session_id':sid,'profile_id':profile.profile_id if profile else None,
            'personalization_enabled':bool(profile and profile.personalization_enabled), 'service_id':service_id,
            'familiarity':request.familiarity if 'familiarity' in request.model_fields_set else session.settings.familiarity_for(service_id),
            'confidence':request.confidence if 'confidence' in request.model_fields_set else session.settings.navigation_capability,
            'preferences':request.preferences if request.preferences is not None else native['preferences'],
            'constraints':constraints.model_dump(),'revision':{'identity':saved['settings_revision'],'revised':native['revision']},
            'sources':{'familiarity':'request_override' if 'familiarity' in request.model_fields_set else 'saved_service_report',
                       'confidence':'request_override' if 'confidence' in request.model_fields_set else 'saved_navigation_default',
                       'preferences':'explicit_revised_settings_or_request','accessibility':'saved_requirements_union_request'},
            'legacy':{'preferences_not_imported':saved['preferences'],'pending_preference_review':saved['legacy_review'],
                      'hard_requirements_unresolved':unresolved,'lock_fingerprint':fingerprint,'raw_locks':raw_locks},
            'scoring_use':'Familiarity, confidence and confirmed revised preferences enter the PP1 encoder; constraints filter candidates. Identity/history are not features.'}

    def patch_context(self,sid,patch):
        self._saved(sid)
        with self.store.transaction() as db:
            saved=self.runtime.settings(sid);native=self.store.settings(db,sid)
            signature=digest(patch.model_dump(mode='json'))
            previous=db.execute('SELECT signature FROM settings_requests WHERE session_id=? AND request_id=?',(sid,patch.request_id)).fetchone()
            if previous:
                if previous[0]!=signature:raise ApiFailure(409,'request_id_reused','Context request ID was reused with different data.')
                return {'schema_version':'c4-settings-3.0','revision':{'identity':saved['settings_revision'],'revised':native['revision']},'settings':native,'duplicate':True}
            if patch.expected_revision.model_dump()!={'identity':saved['settings_revision'],'revised':native['revision']}:
                raise ApiFailure(409,'context_revision_changed','Reload settings before editing.')
            raw={'native_or_mapped':saved['locks'],'unresolved_legacy':{k:v for k,v in saved['legacy_review'].items() if k.startswith('locks.')}}
            if patch.legacy_lock_fingerprint is not None:
                if patch.locks is None or patch.legacy_lock_fingerprint!=digest(raw):raise ApiFailure(422,'legacy_lock_review_mismatch','Review the exact old requirements and explicitly supply revised locks.')
                native['legacy_lock_ack']=patch.legacy_lock_fingerprint
            for name in ('preferences','locks'):
                if getattr(patch,name) is not None:native[name]=getattr(patch,name)
            if patch.accessibility is not None:native['accessibility']=patch.accessibility.model_dump(exclude={'locks'})
            native['revision']+=1
            db.execute('INSERT INTO settings VALUES (?,?) ON CONFLICT(session_id) DO UPDATE SET body=excluded.body',(sid,json.dumps(native)))
            db.execute('INSERT INTO settings_requests VALUES (?,?,?)',(sid,patch.request_id,signature))
            return {'schema_version':'c4-settings-3.0','revision':{'identity':saved['settings_revision'],'revised':native['revision']},'settings':native,'duplicate':False}

    def availability(self,pid,sid,language='en',overrides=None,*,enqueue_on_miss=False):
        context=self.context(sid,pid,overrides)
        source,artifact,metadata=self.prepared.resolve(pid,language=language,enqueue_on_miss=enqueue_on_miss)
        content=artifact['content'] if artifact else None
        results=self.flavour.evaluate(source,content,Constraints(**context['constraints']))
        blocked=context['legacy']['hard_requirements_unresolved']
        candidates=[{'id':self.flavour.config_key(c.configuration),'configuration':c.configuration.model_dump(),'feasible':c.feasible and not blocked,
                     'reasons':list(c.reasons)+(['context:unresolved_legacy_hard_requirements'] if blocked else []),
                     'disclosable_action_ids':list(c.disclosable_action_ids)} for c in results]
        result={'action_schema':self.flavour.action_schema,'nominal_count':96,'feasible_count':sum(c['feasible'] for c in candidates),
                'candidates':candidates,'context':context,'preparation':metadata}
        if self.flavour.feasibility_fingerprint:result['feasibility_fingerprint']=self.flavour.feasibility_fingerprint(results)
        return result,source,content

    def _hard_hash(self,context):
        return digest({'constraints':context['constraints'],'legacy':context['legacy']['hard_requirements_unresolved'],'old_lock_fingerprint':context['legacy']['lock_fingerprint']})

    def _check_context(self,journey,db):
        current=self.context(journey['session_id'],journey['procedure_id'],RequestContext.model_validate(journey['overrides']),db)
        if self._hard_hash(current)!=journey['hard_context_hash']:
            raise ApiFailure(409,'hard_requirements_changed','Request fresh guidance after reviewing changed accessibility or hard requirements.')

    def _authorize(self,db,jid,token):
        row=db.execute('SELECT token_hash FROM journeys WHERE id=?',(jid,)).fetchone()
        if row is None:raise ApiFailure(404,'unknown_journey','Unknown revised guidance journey.')
        if not hmac.compare_digest(row[0],token_hash(token or '')):raise ApiFailure(403,'invalid_capability','The journey capability does not match.')
        journey=self.store.get(db,jid);self._check_context(journey,db)
        return journey

    def _snapshot_source(self,journey):return ProcedureSource.model_validate_json(json.dumps(journey['source']))

    def _response(self,journey):
        view=journey['views'][journey['current_view_id']];source=self._snapshot_source(journey)
        state=interaction_projection(source,view,journey['interaction'])
        doc=copy.deepcopy(view['document']);doc['navigation']=state['navigation']
        result={'schema_version':'c4-guidance-api-1.0','journey_id':journey['id'],'view_id':view['id'],'parent_view_id':view['parent_view_id'],
                'session_id':journey['session_id'],'procedure_id':journey['procedure_id'],'procedure_title':journey['title'],
                'created_at':journey['created_at'],'selection':view['selection'],'preparation':journey['preparation'],
                'effective_context':journey['context'],'availability':journey['availability'],'document':doc,'interaction':state,
                'controls':{'configuration_adjustment':journey['origin'] in ('research_preview','shared_gaussian_lints'),
                            'feedback':journey['origin'] in ('research_preview','shared_gaussian_lints'),'research_inspection':self.research_enabled}}
        return GuidanceResponse.model_validate_json(json.dumps(result))

    def start(self,body,*,preview=False):
        if preview and not self.research_enabled:raise ApiFailure(403,'research_preview_disabled','Enable the explicit research preview setting.')
        signature_body=body.model_dump(mode='json',exclude={'capability_token'})
        signature_body['context']=body.context.model_dump(mode='json',exclude_unset=True)
        signature=digest({'request':signature_body,'token_hash':token_hash(body.capability_token)})
        with self.store.transaction() as db:
            row=db.execute('SELECT id,signature FROM journeys WHERE session_id=? AND request_id=?',(body.session_id,body.request_id)).fetchone()
            if row:
                if row[1]!=signature:raise ApiFailure(409,'request_id_reused','Guidance request ID was reused with different data.')
                return self._response(self._authorize(db,row[0],body.capability_token))
        initial=self.context(body.session_id,body.procedure_id,body.context)
        if body.expected_context_revision and body.expected_context_revision.model_dump()!=initial['revision']:
            raise ApiFailure(409,'context_revision_changed','Refresh the profile context before requesting guidance.')
        if not preview and body.mode=='personalized' and self.policy is None:
            raise ApiFailure(503,'revised_policy_unavailable','The compatible PP1 model is not enabled in this runtime. '+('A fresh policy trained for content schema '+self.flavour.content_schema+' is required; the 3.0 posterior is never reused.' if not self.flavour.supports_policy else 'Set an explicit isolated PP1 policy directory and enable C4_PP1_POLICY_ENABLED. The 515-feature V2 policy is never reused.'),action_schema=self.flavour.action_schema,encoder_status='approved_pp1_policy_disabled',pp2_history='deferred')
        availability,source,content=self.availability(body.procedure_id,body.session_id,body.language,body.context,enqueue_on_miss=True)
        context=availability.pop('context');metadata=availability.pop('preparation')
        if body.expected_context_revision and body.expected_context_revision.model_dump()!=context['revision']:
            raise ApiFailure(409,'context_revision_changed','Refresh the profile context before requesting guidance.')
        if context['legacy']['hard_requirements_unresolved']:raise ApiFailure(409,'legacy_hard_requirements_unresolved','Review changed-meaning hard requirements or use a separate guest session.')
        feasible=[c for c in availability['candidates'] if c['feasible']]
        if not feasible:raise ApiFailure(409,'no_feasible_configuration','No configuration satisfies the content and hard requirements.',candidates=availability['candidates'])
        learned = not preview and body.mode=='personalized' and context['personalization_enabled']
        with self.store.transaction() as db:
            row=db.execute('SELECT id,signature FROM journeys WHERE session_id=? AND request_id=?',(body.session_id,body.request_id)).fetchone()
            if row:
                if row[1]!=signature:raise ApiFailure(409,'request_id_reused','Request ID was reused.')
                return self._response(self._authorize(db,row[0],body.capability_token))
            decision=None
            if preview:
                chosen=next(c for c in availability['candidates'] if c['configuration']==body.configuration.model_dump())
                if not chosen['feasible']:raise ApiFailure(422,'infeasible_configuration','The requested research preview is unavailable.',reasons=chosen['reasons'],configuration=chosen['configuration'])
                config=body.configuration;kind='research_preview';label='Research preview - not a learned selection'
            elif learned:
                config,decision=self.policy.select(db,measurements(source.graph,source.relationships),context,[Configuration(**c['configuration']) for c in feasible])
                if self.flavour.feasibility_fingerprint:decision.update(content_schema=self.flavour.content_schema,action_schema=self.flavour.action_schema,feasibility_fingerprint=availability['feasibility_fingerprint'],content_fingerprint=doc_fingerprint(content))
                kind='shared_gaussian_lints';label='Personalized guidance - Shared Gaussian LinTS'
            else:
                config=Configuration(**feasible[0]['configuration']);kind='standard' if config==Configuration() else 'constraint_standard';label='Standard guidance'
            selection=Selection(kind=kind,configuration=config,action_schema=self.flavour.action_schema,label=label,
                scoring_status='executed' if learned else 'not_run',policy=decision['policy'] if learned else None,
                learning_eligible=learned,explanation='Maximum sampled score among feasible configurations; scores are not probabilities.' if learned else
                ('Explicit researcher choice; no scoring or model update.' if preview else 'Fixed baseline within hard constraints; not a learned recommendation.')).model_dump(mode='json')
            doc,reminders=render(source,content,config,Constraints(**context['constraints']),compose_fn=self.flavour.compose)
            jid='guidance:'+uuid4().hex;vid='view:'+uuid4().hex
            interaction={'routes':{},'visited':{},'active_action_id':None,'viewport':None,'map_visible':config.relationships=='map',
                         'explanation_open':[],'displayed_views':[],'sequence':0}
            interaction['active_action_id']=navigation(source,doc,interaction)['active_action_id']
            journey={'id':jid,'session_id':body.session_id,'procedure_id':body.procedure_id,'title':next(s.name for s in source.graph.stages if s.service_id==source.graph.requested_service_id),
                     'origin':kind,'created_at':now(),'context':context,'hard_context_hash':self._hard_hash(context),
                     'overrides':body.context.model_dump(mode='json',exclude_unset=True),'preparation':metadata,'availability':availability,
                     'source':source.model_dump(mode='json'),'content':content.model_dump(mode='json') if content else None,
                     'decision':decision,'ever_adjusted':False,
                     'current_view_id':vid,'views':{vid:{'id':vid,'parent_view_id':None,'created_at':now(),'selection':selection,'document':doc,'reminders':reminders}},'interaction':interaction}
            self._check_context(journey,db)
            db.execute('INSERT INTO journeys VALUES (?,?,?,?,?,?,?)',(jid,body.session_id,body.request_id,signature,token_hash(body.capability_token),json.dumps(journey),digest(journey)))
            return self._response(journey)

    def read(self,jid,token):
        with self.store.transaction() as db:return self._response(self._authorize(db,jid,token))

    def _operation(self,db,journey,event_id,payload):
        signature=digest(payload)
        row=db.execute('SELECT signature,receipt FROM operations WHERE journey_id=? AND event_id=?',(journey['id'],event_id)).fetchone()
        if row:
            if row[0]!=signature:raise ApiFailure(409,'event_id_reused','Event ID was reused with different content.')
            return signature,json.loads(row[1])
        return signature,None

    def _record(self,db,j,identifier,signature,record,learning=None):
        j['interaction']['sequence']+=1
        record={**record,'event_id':identifier,'sequence':j['interaction']['sequence'],'server_timestamp':now(),
                'procedure_id':j['procedure_id'],'source_graph_fingerprint':j['preparation'].get('source_graph_fingerprint',self._snapshot_source(j).graph_fingerprint),
                'evidence_origin':'client_reported_interaction_not_completion','reward':None,'policy_updated':False,**(learning or {})}
        receipt={'event_id':identifier,'sequence':record['sequence'],'server_timestamp':record['server_timestamp'],
                 'reward':None,'policy_updated':False,'learning_eligible':False,**{k:v for k,v in (learning or {}).items() if k in ('reward','policy_updated','learning_eligible')}}
        db.execute('INSERT INTO operations VALUES (?,?,?,?,?)',(j['id'],identifier,signature,json.dumps(record),json.dumps(receipt)))
        self.store.save(db,j)
        return receipt

    def _view(self,j,vid):
        if vid!=j['current_view_id']:raise ApiFailure(409,'inactive_view','Use the current view identity.')
        return j['views'][vid]

    def event(self,jid,token,event):
        with self.store.transaction() as db:
            j=self._authorize(db,jid,token);signature,receipt=self._operation(db,j,event.event_id,{'kind':'interaction',**event.model_dump(mode='json')})
            if receipt:return receipt
            view=self._view(j,event.view_id);source=self._snapshot_source(j);g=source.graph;state=j['interaction'];config=Configuration(**view['selection']['configuration'])
            actions={a.action_id for a in g.actions}
            if event.action_id is not None and event.action_id not in actions or not set(event.action_ids)<=actions or len(event.action_ids)!=len(set(event.action_ids)):
                raise ApiFailure(422,'unknown_action','Event action references must belong to this frozen procedure.')
            allowed_fields={'navigate':{'action_id'},'step_open':{'action_id'},'step_visible':{'action_id','visible_ratio','dwell_ms','instrumentation_version'},
                'view_displayed':{'action_ids'},'viewport_changed':{'action_ids'},'route_focus':{'branch_id','option_ids'},
                'explanation_open':{'action_id'},'explanation_close':{'action_id'},'source_open':{'source_id'}}
            extra=event.model_fields_set-{'event_id','view_id','type','client_timestamp'}
            if not extra<=allowed_fields.get(event.type,set()):raise ApiFailure(422,'event_scope_mismatch','Unexpected fields for this event type.')
            before=interaction_projection(source,view,state)
            opportunity={'available_not_proof_of_visibility':True,'configuration':config.model_dump(),
                         'essential_display_acknowledged_before_event':event.view_id in state['displayed_views'],
                         'disclosable_action_ids':[a['id'] for a in view['document']['actions'] if a['disclosure_available']],
                         'recap_action_ids_before_event':[a['action_id'] for a in before['recap']['items']]}
            outcome={'qualifies_for_recap':False,'opportunity':opportunity}
            if event.type in ('navigate','step_open','step_visible','explanation_open','explanation_close') and event.action_id is None:
                raise ApiFailure(422,'action_required','This event needs an action ID.')
            if event.type in ('navigate','step_open'):
                if event.action_id not in eligible_ids(g,state['routes'],require_choice=True):raise ApiFailure(422,'route_choice_required','Choose the applicable route before visiting its actions.')
                state['active_action_id']=event.action_id;outcome['qualifies_for_recap']=True
            if event.type=='step_visible':
                if event.visible_ratio is None or event.dwell_ms is None or event.instrumentation_version is None:
                    raise ApiFailure(422,'visibility_measurements_required','Record ratio, continuous dwell and instrumentation version.')
                policy=self.visibility_policy
                outcome['qualifies_for_recap']=bool(policy and event.instrumentation_version==policy['version'] and event.visible_ratio>=policy['min_visible_ratio'] and event.dwell_ms>=policy['min_dwell_ms'] and event.action_id in eligible_ids(g,state['routes'],require_choice=True))
                outcome['visibility_policy']=policy
                outcome['reason']='qualifying_visibility' if outcome['qualifies_for_recap'] else 'unapproved_or_unmet_visibility_policy'
            if outcome['qualifies_for_recap']:
                state['visited'][event.action_id]={'event_id':event.event_id,'kind':event.type,'view_id':event.view_id,'sequence':state['sequence']+1}
            if event.type=='view_displayed':
                if not event.action_ids:raise ApiFailure(422,'displayed_actions_required','Record the actual displayed essential layers.')
                if event.view_id not in state['displayed_views']:state['displayed_views'].append(event.view_id)
            if event.type=='viewport_changed':state['viewport']=event.action_ids
            if event.type=='route_focus':
                branch=next((b for b in g.branch_groups if b.group_id==event.branch_id),None)
                if branch is None or not set(event.option_ids)<={o.option_id for o in branch.options} or len(set(event.option_ids))!=len(event.option_ids):raise ApiFailure(422,'invalid_route','Route choices must match this procedure.')
                if branch.selection=='XOR' and len(event.option_ids)>1:raise ApiFailure(422,'xor_route_conflict','Choose at most one alternative.')
                if branch.selection=='AND' and set(event.option_ids)!={o.option_id for o in branch.options}:raise ApiFailure(422,'all_routes_required','This source requires all branch options.')
                if event.option_ids:state['routes'][event.branch_id]=event.option_ids
                else:state['routes'].pop(event.branch_id,None)
                state['active_action_id']=navigation(source,view['document'],state)['active_action_id']
            if event.type.startswith('explanation_'):
                if config.disclosure!='on' or not next(a for a in view['document']['actions'] if a['id']==event.action_id)['disclosure_available']:raise ApiFailure(422,'explanation_control_unavailable','No disclosable remainder is available here.')
                if event.type=='explanation_open' and event.action_id not in state['explanation_open']:state['explanation_open'].append(event.action_id)
                if event.type=='explanation_close' and event.action_id in state['explanation_open']:state['explanation_open'].remove(event.action_id)
            if event.type.startswith('map_'):
                if config.relationships!='map':raise ApiFailure(422,'map_control_unavailable','This view does not include a process map.')
                if event.type in ('map_show','map_hide'):state['map_visible']=event.type=='map_show'
            if event.type.startswith('recap_') and config.recap!='on':raise ApiFailure(422,'recap_control_unavailable','Recap is off in this view.')
            if event.type=='source_open' and event.source_id not in {e.evidence_id for e in g.evidence}:raise ApiFailure(422,'unknown_source','Unknown source reference.')
            return self._record(db,j,event.event_id,signature,{'type':event.type,'view_id':event.view_id,'payload':event.model_dump(mode='json'),**outcome})

    def adjust(self,jid,token,body):

        with self.store.transaction() as db:
            j=self._authorize(db,jid,token);signature,receipt=self._operation(db,j,body.request_id,{'kind':'adjustment',**body.model_dump(mode='json')})
            if receipt:return self._response(j)
            if j['origin'] not in ('research_preview','shared_gaussian_lints'):raise ApiFailure(403,'standard_adjustment_unavailable','Standard guests do not receive personalized support controls.')
            self._view(j,body.parent_view_id);source=self._snapshot_source(j);content=self.flavour.content_model.model_validate(j['content']) if j['content'] else None
            constraints=Constraints(**j['context']['constraints']);candidate=next(c for c in self.flavour.evaluate(source,content,constraints) if c.configuration==body.configuration)
            if not candidate.feasible:raise ApiFailure(422,'infeasible_configuration','Adjusted configuration is unavailable.',reasons=list(candidate.reasons))
            doc,reminders=render(source,content,body.configuration,constraints,compose_fn=self.flavour.compose);vid='view:'+uuid4().hex
            selection=Selection(kind='manual_adjustment',configuration=body.configuration,action_schema=self.flavour.action_schema,label='Adjusted research preview - not a learned selection',explanation='Explicit child view; no policy scoring or reward update.').model_dump(mode='json')
            j['views'][vid]={'id':vid,'parent_view_id':body.parent_view_id,'created_at':now(),'selection':selection,'document':doc,'reminders':reminders}
            j['ever_adjusted']=True
            j['current_view_id']=vid;j['interaction']['explanation_open']=[];j['interaction']['map_visible']=body.configuration.relationships=='map'
            self._record(db,j,body.request_id,signature,{'type':'explicit_adjustment','view_id':vid,'parent_view_id':body.parent_view_id,'configuration':body.configuration.model_dump()})
            return self._response(j)

    def rate(self,jid,token,body):
        with self.store.transaction() as db:
            j=self._authorize(db,jid,token);signature,receipt=self._operation(db,j,body.event_id,{'kind':'rating',**body.model_dump(mode='json')})
            if receipt:return receipt
            self._view(j,body.view_id)
            if j['origin'] not in ('research_preview','shared_gaussian_lints'):raise ApiFailure(403,'standard_feedback_unavailable','Standard guests have no support-fit learning feedback.')
            if len(body.reasons)!=len(set(body.reasons)):raise ApiFailure(422,'duplicate_reasons','Reasons must be distinct.')
            if any(json.loads(row[0]).get('type')=='rating' and json.loads(row[0]).get('view_id')==body.view_id for row in db.execute('SELECT record FROM operations WHERE journey_id=?',(jid,))):raise ApiFailure(409,'already_rated','This preview view already has a rating.')
            eligible = (j['origin']=='shared_gaussian_lints' and not j.get('ever_adjusted',False)
                and j['views'][body.view_id]['parent_view_id'] is None and self.context(j['session_id'],j['procedure_id'],db=db)['personalization_enabled'])
            learning=None
            if eligible:
                if body.view_id not in j['interaction']['displayed_views']:
                    raise ApiFailure(409,'display_acknowledgment_required','Acknowledge the original displayed guidance before rating.')
                reward=int(body.rating=='fits')
                if self.policy is None:raise ApiFailure(503,'revised_policy_unavailable','Restart with the matching isolated PP1 model before rating this decision.')
                try:update=self.policy.update(db,j,body.event_id,reward)
                except ValueError as exc:raise ApiFailure(409,'policy_run_changed','This frozen decision belongs to a different model run; request fresh guidance.') from exc
                learning={'reward':reward,'policy_updated':True,'learning_eligible':True,**update}
            return self._record(db,j,body.event_id,signature,{'type':'rating','view_id':body.view_id,'rating':body.rating,'reasons':body.reasons,
                'ineligible_reason':None if eligible else 'preview_manual_or_personalization_disabled'},learning)

    def inspect(self,jid,token):
        if not self.research_enabled:raise ApiFailure(403,'research_inspection_disabled','Research inspection is disabled.')
        with self.store.transaction() as db:
            j=self._authorize(db,jid,token);source=self._snapshot_source(j)
            events=[json.loads(row[0]) for row in db.execute('SELECT record FROM operations WHERE journey_id=? ORDER BY rowid',(jid,))]
            context=copy.deepcopy(j['context']);context['session_id']='session:'+digest(j['session_id'])[:12]
            if context['profile_id']:context['profile_id']='profile:'+digest(context['profile_id'])[:12]
            return {'schema_version':'c4-guidance-inspection-1.0','record_kind':'completed_request_and_client_events','journey_id':jid,
                    'created_at':j['created_at'],'source_graph_fingerprint':source.graph_fingerprint,
                    'content_fingerprint':j['views'][j['current_view_id']]['document']['content_fingerprint'],
                    'effective_context':context,'measurements':measurements(source.graph,source.relationships).model_dump(mode='json'),
                    'availability':j['availability'],'views':[{k:v[k] for k in ('id','parent_view_id','created_at','selection')} for v in j['views'].values()],
                    'events':events,'features':{'names':__import__('app.guidance.features',fromlist=['NAMES']).NAMES,'selected':j['decision']['selected_features'],'fingerprint':j['decision']['feature_fingerprint']} if j.get('decision') else None,
                    'sampled_scores':j['decision']['candidates'] if j.get('decision') else None,
                    'policy':j['decision'] if j.get('decision') else None,'posterior_updates':sum(bool(e.get('policy_updated')) for e in events),
                    'scoring_status':'executed' if j.get('decision') else 'not_run','pp2_history_adjustment':'not_implemented','visibility_policy':self.visibility_policy,
                    'note':('Actual frozen PP1 scores/features and attributed explicit updates. Interaction events do not establish reading or completion.' if j.get('decision') else 'Only stored request/configuration evidence and actual client-reported events; no reading, completion or policy-learning claim.')}
