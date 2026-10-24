"""Capture real isolated TestClient API responses; not frontend/runtime fixtures."""
import argparse
import json
import sys
from pathlib import Path
from uuid import uuid4

C4=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(C4/'service'))
from fastapi.testclient import TestClient
from app.host.application import create_app
from app.host.identity import WorkspaceRuntime
from app.procedures.registration import workspace_registry

ROOT='/workspace/guidance'
TOKEN='documentation-sandbox-only-not-a-production-capability'
RICH={'navigation':'guided','explanation':'detailed','disclosure':'on','relationships':'map','recap':'on','segmentation':'on'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    output=Path(args.output).resolve()
    if not output.is_relative_to(C4) or output.exists():raise ValueError('Choose a new output directory inside C4; never overwrite historical exports.')
    output.mkdir(parents=True)
    temp=C4/'service'/'.local'/'v2'/('api-export-'+uuid4().hex[:8])/'prepared-content'
    runtime=WorkspaceRuntime(procedures=workspace_registry());before=runtime.status()
    captures=[]
    options={'directory':temp,'demo_fixtures':True}
    with TestClient(create_app(runtime=runtime,workspace=True,prepared_content_options=options,guidance_api_options={'research_enabled':True})) as client:
        def capture(name,method,path,body=None,token=False,expected=200):
            response=client.request(method,path,json=body,headers={'X-C4-Token':TOKEN} if token else {})
            if response.status_code!=expected:raise RuntimeError(name+': '+response.text)
            data={'method':method,'path':path,'request':body,'status_code':response.status_code,'response':response.json()}
            if token:data['headers']={'X-C4-Token':TOKEN}
            (output/(name+'.json')).write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
            captures.append(name+'.json')
            return response.json()
        capture('status','GET',ROOT+'/status')
        procedures=capture('procedures','GET',ROOT+'/procedures')
        sid=capture('guest','POST',ROOT+'/guests')['session_id']
        for entry in procedures:
            pid=entry['procedure_id']
            body={'request_id':str(uuid4()),'session_id':sid,'procedure_id':pid,'capability_token':TOKEN}
            capture('standard-'+pid,'POST',ROOT+'/requests',body)
        for pid in ('synthetic-linear-v1','synthetic-conditional-v1','synthetic-parallel-v1','synthetic-practice-v2'):
            config={**RICH,'segmentation':'off'} if pid=='synthetic-linear-v1' else RICH
            body={'request_id':str(uuid4()),'session_id':sid,'procedure_id':pid,'capability_token':TOKEN,'mode':'research_preview','configuration':config}
            result=capture('preview-'+pid,'POST',ROOT+'/research/previews',body)
            if pid=='synthetic-practice-v2':
                journey=result
                capture('practice-availability','GET',ROOT+'/procedures/'+pid+'/availability?session_id='+sid)
        body={'request_id':str(uuid4()),'session_id':sid,'procedure_id':'official-nic_amendment-v3','capability_token':TOKEN,'mode':'research_preview','configuration':RICH}
        capture('error-official-unavailable','POST',ROOT+'/research/previews',body,expected=422)
        capture('error-personalized-unavailable','POST',ROOT+'/requests',{k:v for k,v in {**body,'mode':'personalized'}.items() if k!='configuration'},expected=503)
        profile=capture('create-profile','POST',ROOT+'/profiles',{'profile_id':'profile:'+uuid4().hex,'display_name':'Documentation example','personalization_enabled':True,
            'initial_context':{'navigation_capability':2,'familiarity':[{'service_id':'svc:birth_copy','score':1},{'service_id':'svc:nic_amendment','score':4}]}})
        psid=profile['session']['session_id']
        for pid in ('official-birth_copy-v3','official-nic_amendment-v3'):
            capture('profile-context-'+pid,'GET',ROOT+'/context/'+psid+'?procedure_id='+pid)
        path=ROOT+'/journeys/'+journey['journey_id']
        for aid in ('action:register_application','action:submit_application'):
            capture('event-'+aid.split(':')[1],'POST',path+'/events',{'event_id':str(uuid4()),'view_id':journey['view_id'],'type':'navigate','action_id':aid},token=True)
        capture('practice-earned-recap','GET',path,token=True)
        capture('practice-inspector','GET',path+'/inspector',token=True)
        schema=client.get('/openapi.json').json()
        paths={k:v for k,v in schema['paths'].items() if k.startswith(ROOT)}
        definitions=schema.get('components',{}).get('schemas',{})
        needed=set()
        def references(value):
            if isinstance(value,dict):
                for k,v in value.items():
                    if k=='$ref' and isinstance(v,str) and v.startswith('#/components/schemas/'):needed.add(v.rsplit('/',1)[1])
                    else:references(v)
            elif isinstance(value,list):
                for v in value:references(v)
        references(paths)
        while True:
            count=len(needed)
            for key in list(needed):references(definitions[key])
            if len(needed)==count:break
        filtered={**schema,'paths':paths,'components':{'schemas':{k:definitions[k] for k in sorted(needed)}}}
        (output/'openapi.json').write_text(json.dumps(filtered,indent=2)+'\n',encoding='utf-8')
        assert runtime.status()==before and not runtime.state['decisions']
    runtime.close()
    manifest={'capture_origin':'Actual FastAPI TestClient HTTP responses from isolated C4 storage, not frontend fixtures',
              'api_schema':'c4-guidance-api-1.0','policy_scoring':'not_run','posterior_updates':0,
              'sample_capability':'Documentation sandbox only; never use a real user token in these files',
              'files':captures+['openapi.json']}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(str(output))

if __name__=='__main__':main()
