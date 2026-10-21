"""Actual loopback PP1 selection -> display -> rating -> restart recovery.

Only starts/stops its own test children; never binds or opens an old store.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
from uuid import uuid4

C4=Path(__file__).resolve().parents[1]


def verify(checkpoint,report,experiment=None):
    report=Path(report).resolve();checkpoint=Path(checkpoint).resolve()
    if not report.is_relative_to(C4) or report.exists() or not checkpoint.is_relative_to(C4):raise ValueError('Use new C4-only report and checkpoint')
    folder=C4/'service/.local/pp1-learning'/('live-'+uuid4().hex[:8]);folder.mkdir(parents=True)
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    env=os.environ.copy();env.update(C4_WORKSPACE_DATABASE=str(folder/'v2/workspace/state.sqlite3'),C4_WORKSPACE_MODE='simulation',
        C4_PREPARED_CONTENT_DIRECTORY=str(folder/'prepared-content'),C4_WORKSPACE_CONTENT_MODE='demo',C4_PREPARED_CONTENT_ENABLED='true',
        C4_PREPARED_CONTENT_MODE='demo',C4_PREPARATION_ON_MISS='false',C4_LLM_ENABLED='false',C4_DEV_LLM_ENABLED='false',
        C4_GUIDANCE_API_ENABLED='true',C4_RESEARCH_PREVIEWS_ENABLED='true',C4_PP1_POLICY_ENABLED='true',
        C4_PP1_POLICY_DIRECTORY=str(folder/'model'),C4_PP1_POLICY_SEED='11',C4_PP1_POLICY_MODE='simulation',C4_PP1_CHECKPOINT=str(checkpoint),
        OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
    if experiment:env['C4_PP1_EXPERIMENT_DIRECTORY']=str(Path(experiment).resolve())
    base=f'http://127.0.0.1:{port}';root='/workspace/guidance';token='pp1-sandbox-capability-'+uuid4().hex
    def call(path,body=None,token=None):
        headers={'Content-Type':'application/json'}
        if token:headers['X-C4-Token']=token
        req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
        with urllib.request.urlopen(req,timeout=20) as response:return json.load(response)
    def launch():
        log=(folder/'server.log').open('a',encoding='utf-8')
        child=subprocess.Popen([sys.executable,'-B','-m','uvicorn','app.workspace:app','--host','127.0.0.1','--port',str(port)],cwd=C4/'service',env=env,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            deadline=time.monotonic()+40
            while True:
                try:return child,log,call(root+'/status')
                except (OSError,TimeoutError):
                    if child.poll() is not None or time.monotonic()>deadline:raise RuntimeError('server startup failed: '+str(folder/'server.log'))
                    time.sleep(.15)
        except Exception:child.terminate();child.wait(timeout=10);log.close();raise
    child,log,status=launch()
    try:
        host_before=call('/v2/policy')
        service=next(p['service_id'] for p in call(root+'/procedures') if p['procedure_id']=='synthetic-practice-v2')
        sid=call(root+'/profiles',{'profile_id':'profile:'+uuid4().hex,'display_name':'Isolated PP1 verification','personalization_enabled':True,
            'initial_context':{'navigation_capability':1,'familiarity':[{'service_id':service,'score':1}]}})['session']['session_id']
        body={'request_id':uuid4().hex,'session_id':sid,'procedure_id':'synthetic-practice-v2','capability_token':token,'mode':'personalized'}
        j=call(root+'/requests',body);path=root+'/journeys/'+j['journey_id']
        assert j['selection']['kind']=='shared_gaussian_lints'
        call(path+'/events',{'event_id':uuid4().hex,'view_id':j['view_id'],'type':'view_displayed','action_ids':[j['document']['actions'][0]['id']]},token)
        before=call(root+'/status')['policy'];rating={'event_id':uuid4().hex,'view_id':j['view_id'],'rating':'fits'}
        receipt=call(path+'/ratings',rating,token);assert receipt['policy_updated'] and receipt['reward']==1
        assert call(path+'/ratings',rating,token)==receipt
        after=call(root+'/status')['policy'];assert after['posterior_revision']==before['posterior_revision']+1
        inspector=call(path+'/inspector',token=token);assert inspector['posterior_updates']==1 and len(inspector['features']['selected'])==525
        best=max(inspector['sampled_scores'],key=lambda c:c['sampled_score']);assert best['configuration']==j['selection']['configuration']
        child.terminate();child.wait(timeout=15);log.close()
        child,log,restarted=launch();assert restarted['policy']==after
        assert call(path,token=token)['selection']==j['selection']
        assert call('/v2/policy')==host_before
        report.parent.mkdir(parents=True,exist_ok=True)
        report.write_text(json.dumps({'execution':'real uvicorn loopback HTTP, actual trained checkpoint, isolated stores',
            'port':port,'checkpoint':str(checkpoint),'selected':j['selection'],'before':before,'after':after,'restart':restarted['policy'],
            'receipt':receipt,'frozen_scoring_seed':inspector['policy']['seed'],'source_preparation':j['preparation'],
            'historical_host_515_unchanged':True,'duplicate_exact_receipt':True,'restart_recovery':True},indent=2),encoding='utf-8')
        return folder
    finally:
        child.terminate();child.wait(timeout=15);log.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--checkpoint',required=True);p.add_argument('--report',required=True);p.add_argument('--experiment')
    a=p.parse_args();print(verify(a.checkpoint,a.report,a.experiment))
