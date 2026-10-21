"""Real loopback startup smoke test in fresh C4-only storage; no training."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from uuid import uuid4

C4=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',required=True)
    args=parser.parse_args()
    report=Path(args.report).resolve()
    if not report.is_relative_to(C4) or report.exists():raise ValueError('Choose a new report path inside C4.')
    service=C4/'service';folder=service/'.local'/'v2'/('api-smoke-'+uuid4().hex[:8]);folder.mkdir(parents=True)
    env=os.environ.copy()
    env.update(C4_WORKSPACE_DATABASE=str(folder/'workspace'/'state.sqlite3'),C4_WORKSPACE_MODE='simulation',C4_WORKSPACE_SEED='0',
        C4_PREPARED_CONTENT_DIRECTORY=str(folder/'prepared-content'),C4_WORKSPACE_CONTENT_MODE='demo',C4_PREPARED_CONTENT_ENABLED='true',
        C4_PREPARED_CONTENT_MODE='demo',C4_PREPARATION_ON_MISS='false',C4_LLM_ENABLED='false',C4_DEV_LLM_ENABLED='false',
        C4_GUIDANCE_API_ENABLED='true',C4_RESEARCH_PREVIEWS_ENABLED='true')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    base='http://127.0.0.1:'+str(port)
    def call(path,body=None,token=None):
        headers={'Content-Type':'application/json'}
        if token:headers['X-C4-Token']=token
        request=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
        with urllib.request.urlopen(request,timeout=10) as response:return json.load(response)
    log=(folder/'server.log').open('w',encoding='utf-8')
    proc=subprocess.Popen([sys.executable,'-B','-m','uvicorn','app.workspace:app','--host','127.0.0.1','--port',str(port)],
        cwd=service,env=env,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:
        deadline=time.monotonic()+30
        while True:
            try:status=call('/workspace/guidance/status');break
            except (urllib.error.URLError,TimeoutError):
                if proc.poll() is not None or time.monotonic()>deadline:raise RuntimeError('Sandbox startup failed; inspect '+str(folder/'server.log'))
                time.sleep(.1)
        before=call('/v2/policy');sid=call('/workspace/guidance/guests',{})['session_id']
        token='sandbox-smoke-capability-not-a-real-user-secret'
        baseline=call('/workspace/guidance/requests',{'request_id':str(uuid4()),'session_id':sid,'procedure_id':'official-nic_amendment-v3','capability_token':token})
        rich={'navigation':'guided','explanation':'detailed','disclosure':'on','relationships':'map','recap':'on','segmentation':'on'}
        preview=call('/workspace/guidance/research/previews',{'request_id':str(uuid4()),'session_id':sid,'procedure_id':'synthetic-practice-v2',
                     'capability_token':token,'mode':'research_preview','configuration':rich})
        path='/workspace/guidance/journeys/'+preview['journey_id']
        for aid in ('action:register_application','action:submit_application'):
            call(path+'/events',{'event_id':str(uuid4()),'view_id':preview['view_id'],'type':'navigate','action_id':aid},token)
        current=call(path,token=token);inspector=call(path+'/inspector',token=token);after=call('/v2/policy')
        assert before==after and baseline['selection']['kind']=='standard' and current['selection']['kind']=='research_preview'
        assert current['interaction']['recap']['items'] and inspector['features'] is None and inspector['sampled_scores'] is None
        result={'execution':'Real uvicorn app.workspace:app loopback HTTP smoke in fresh isolated storage','port':port,
                'status':status,'baseline_procedure':baseline['procedure_id'],'baseline_origin':baseline['selection']['kind'],
                'preview_configuration':current['selection']['configuration'],'recap_item_ids':[x['action_id'] for x in current['interaction']['recap']['items']],
                'actual_event_count':len(inspector['events']),'model_features':inspector['features'],'model_sampled_scores':inspector['sampled_scores'],
                'policy_unchanged':before==after,'live_generation_enabled':current['preparation']['generation_enabled'],
                'source_review_kind':current['preparation']['review_kind'],'historical_database_used':False}
        report.parent.mkdir(parents=True,exist_ok=True);report.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print(str(report))
    finally:
        proc.terminate()  # Only the child created above, never an existing C4 server.
        try:proc.wait(timeout=10)
        except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)
        log.close()

if __name__=='__main__':main()
