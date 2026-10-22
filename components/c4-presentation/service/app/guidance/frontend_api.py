"""Frontend-ready opt-in routes in the existing application, not a new runtime."""
import json
from fastapi import Header, HTTPException
from fastapi.responses import JSONResponse
from app.guidance.frontend_contracts import (API_SCHEMA, StartGuidance, PreviewGuidance, ContextPatch,
    Interaction, AdjustView, Rating, GuidanceResponse, ProfileContextPatch, AvailabilityResponse, EffectiveContext, Receipt)
from app.guidance.frontend_runtime import ApiFailure
from app.models.demo_profiles import CreateDemoProfileRequest, DemoProfileResponse, PersonalizationRequest


def register_routes(app):
    def api():
        result=getattr(app.state,'guidance_api',None)
        if result is None:raise HTTPException(404,{'code':'guidance_api_disabled','message':'Enable the controlled revised guidance API.'})
        return result

    @app.exception_handler(ApiFailure)
    async def failure(request,exc):
        return JSONResponse(status_code=exc.status,content={'detail':exc.detail})

    @app.get('/workspace/guidance/status',tags=['Revised Guidance'])
    def status():
        result=api()
        return {'schema_version':API_SCHEMA,'action_schema':result.flavour.action_schema,'content_schema':result.flavour.content_schema,'nominal_configuration_count':96,
                'standard_guidance_available':True,'research_previews_enabled':result.research_enabled,
                'personalized_selection_available':result.policy is not None,'encoder_status':result.policy.profile.encoder_schema if result.policy else 'approved_525_policy_disabled',
                'policy':result.policy.status() if result.policy else None,'history_adjustment':'deferred_to_PP2',
                'pp1_remaining_requirements':[] if result.policy else ['enable_isolated_PP1_policy'],
                'visibility_policy':result.visibility_policy,'demo_provisional_content':[] if result.demo_accepted else sorted(result.provisional),'demo_accepted_content':sorted(result.provisional) if result.demo_accepted else [],'contracts':'/openapi.json'}

    @app.get('/workspace/guidance/research/learning',tags=['Revised Guidance'])
    def learning_report():
        from pathlib import Path
        from app.guidance.policy import C4_ROOT
        result=api()
        if not result.research_enabled or not result.experiment_directory:
            raise HTTPException(404,{'code':'learning_report_unavailable','message':'Configure an explicit completed synthetic experiment.'})
        path=Path(result.experiment_directory).resolve()
        if not path.is_relative_to(C4_ROOT) or 'pp1-learning' not in path.parts:
            raise HTTPException(422,'Experiment path must be isolated inside C4/pp1-learning')
        if not (path/'report.json').is_file():raise HTTPException(404,'Completed learning report unavailable')
        return json.loads((path/'report.json').read_text(encoding='utf-8'))

    @app.get('/workspace/guidance/research/traces/{run}',tags=['Revised Guidance'])
    def learning_trace(run:str,offset:int=0,limit:int=20):
        from pathlib import Path
        report=learning_report()
        entry=next((r for r in report['runs'] if r['run']==run),None)
        if entry is None:raise HTTPException(404,'Unknown recorded run')
        if offset<0 or not 1<=limit<=100:raise HTTPException(422,'Use nonnegative offset and limit 1..100')
        path=Path(api().experiment_directory)/entry['trace']
        if path.parent.resolve()!=Path(api().experiment_directory).resolve():raise HTTPException(422,'Invalid trace path')
        import itertools
        with path.open(encoding='utf-8') as file:
            return {'run':run,'offset':offset,'observations':[json.loads(line) for line in itertools.islice(file,offset,offset+limit)]}

    @app.get('/workspace/guidance/research/learning/{artifact}',tags=['Revised Guidance'])
    def learning_plot(artifact:str):
        from pathlib import Path
        from fastapi.responses import FileResponse
        learning_report()
        if artifact not in ('learning.svg','baselines.svg','regret.svg','distribution.svg','ablation.svg','constraints.svg','report.html','learning-curve-dev.png','learning-curve-test.png','sensitivity-test.png','families-test.png','selection-mismatch.png','summary.md'):
            raise HTTPException(404,'Unknown learning artifact')
        path=Path(api().experiment_directory)/artifact
        if not path.is_file():raise HTTPException(404,'Artifact unavailable; generate plots first')
        return FileResponse(path)

    @app.get('/workspace/guidance/profiles',response_model=list[DemoProfileResponse],tags=['Revised Guidance'])
    def profiles():
        result=api()
        with result.runtime.lock:return [DemoProfileResponse.model_validate_json(json.dumps(result.runtime.profile_response(p))) for p in result.runtime.profiles]

    @app.post('/workspace/guidance/profiles',response_model=DemoProfileResponse,tags=['Revised Guidance'])
    def create_profile(body:CreateDemoProfileRequest):return DemoProfileResponse.model_validate_json(json.dumps(api().runtime.create_profile(body)))

    @app.patch('/workspace/guidance/profiles/{profile_id}/personalization',response_model=DemoProfileResponse,tags=['Revised Guidance'])
    def personalization(profile_id:str,body:PersonalizationRequest):return DemoProfileResponse.model_validate_json(json.dumps(api().runtime.personalization(profile_id,body)))

    @app.post('/workspace/guidance/guests',tags=['Revised Guidance'])
    def guest():return api().runtime.create_session()

    @app.get('/workspace/guidance/procedures',tags=['Revised Guidance'])
    def procedures():
        result=api();items=[]
        with result.runtime.lock:identifiers=list(result.runtime.procedures)
        for pid in identifiers:
            source=result.source(pid);graph=source.graph
            items.append({'procedure_id':pid,'service_id':graph.requested_service_id,'title':next(s.name for s in graph.stages if s.service_id==graph.requested_service_id),
                          'synthetic':graph.synthetic,'source_origin':'fictional_authored' if graph.synthetic else 'bounded_official_source_snapshot_not_independently_validated',
                          'source_limit':graph.disclaimer,'graph_fingerprint':source.graph_fingerprint,'completeness':graph.completeness.model_dump()})
        return items

    @app.get('/workspace/guidance/context/{session_id}',response_model=EffectiveContext,tags=['Revised Guidance'])
    def context(session_id:str,procedure_id:str):return api().context(session_id,procedure_id)

    @app.patch('/workspace/guidance/context/{session_id}',tags=['Revised Guidance'])
    def edit_context(session_id:str,body:ContextPatch):return api().patch_context(session_id,body)

    @app.patch('/workspace/guidance/profile-context/{session_id}',tags=['Revised Guidance'])
    def edit_profile_context(session_id:str,body:ProfileContextPatch):
        from app.models.user_context import ContextUpdate
        from app.v2.identity import SettingsPatch
        changes={}
        if 'confidence' in body.model_fields_set:changes['navigation_capability']=body.confidence
        if body.accessibility is not None:changes['accessibility']=body.accessibility.model_dump(exclude_unset=True)
        patch=SettingsPatch(request_id=body.request_id,expected_revision=body.expected_identity_revision,
                            context=ContextUpdate(**changes),familiarity=body.familiarity)
        return api().runtime.update_settings(session_id,patch)

    @app.get('/workspace/guidance/procedures/{procedure_id}/availability',response_model=AvailabilityResponse,tags=['Revised Guidance'])
    def availability(procedure_id:str,session_id:str,language:str='en',provisional:bool=False):
        return api().availability(procedure_id,session_id,language,provisional=provisional)[0]

    @app.post('/workspace/guidance/requests',response_model=GuidanceResponse,tags=['Revised Guidance'])
    def request_guidance(body:StartGuidance):return api().start(body)

    @app.post('/workspace/guidance/research/previews',response_model=GuidanceResponse,tags=['Revised Guidance'])
    def preview(body:PreviewGuidance):return api().start(body,preview=True)

    @app.get('/workspace/guidance/journeys/{journey_id}',response_model=GuidanceResponse,tags=['Revised Guidance'])
    def read(journey_id:str,x_c4_token:str=Header()):return api().read(journey_id,x_c4_token)

    @app.post('/workspace/guidance/journeys/{journey_id}/events',response_model=Receipt,tags=['Revised Guidance'])
    def event(journey_id:str,body:Interaction,x_c4_token:str=Header()):return api().event(journey_id,x_c4_token,body)

    @app.post('/workspace/guidance/journeys/{journey_id}/views',response_model=GuidanceResponse,tags=['Revised Guidance'])
    def adjust(journey_id:str,body:AdjustView,x_c4_token:str=Header()):return api().adjust(journey_id,x_c4_token,body)

    @app.post('/workspace/guidance/journeys/{journey_id}/ratings',response_model=Receipt,tags=['Revised Guidance'])
    def rate(journey_id:str,body:Rating,x_c4_token:str=Header()):return api().rate(journey_id,x_c4_token,body)

    @app.get('/workspace/guidance/journeys/{journey_id}/inspector',tags=['Revised Guidance'])
    def inspect(journey_id:str,x_c4_token:str=Header()):return api().inspect(journey_id,x_c4_token)
