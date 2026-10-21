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
        return {'schema_version':API_SCHEMA,'action_schema':'c4-scaffolds-v3.0','nominal_configuration_count':96,
                'standard_guidance_available':True,'research_previews_enabled':result.research_enabled,
                'personalized_selection_available':False,'encoder_status':'525_proposed_awaiting_approval',
                'policy':None,'history_adjustment':'deferred_to_PP2',
                'pp1_remaining_requirements':['approved_revised_encoder','fresh_posterior','synthetic_training','held_out_evaluation','genuine_feasible_LinTS_selection'],
                'visibility_policy':result.visibility_policy,'contracts':'/openapi.json'}

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
    def availability(procedure_id:str,session_id:str,language:str='en'):
        return api().availability(procedure_id,session_id,language)[0]

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
