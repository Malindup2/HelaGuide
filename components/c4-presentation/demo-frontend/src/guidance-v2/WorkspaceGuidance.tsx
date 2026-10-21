import {useCallback,useEffect,useRef,useState} from 'react';
import {API_BASE} from '../api/client';
import type {ActiveIdentity,ProcedureSummary} from '../api/types';
import GuidanceMessage from './GuidanceMessage';
import type {Configuration,EventInput,Journey,Receipt} from './types';
import './v2.css';
import {workspaceRequest,WorkspaceError} from './workspaceClient';

type Capability={id:string;token:string};

function saved(key:string):Capability|null{try{return JSON.parse(sessionStorage.getItem(key)??'null');}catch{return null;}}
export default function WorkspaceGuidance({active,procedure,disabled,onActivityChange}:{active:ActiveIdentity;procedure:ProcedureSummary;disabled:boolean;onActivityChange:(busy:boolean)=>void}){
 const sid=active.session.session_id,key=`c4-workspace:${API_BASE}:${sid}:${procedure.procedure_id}`;
 const [journey,setJourney]=useState<Journey|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const responseRoot=useRef<HTMLElement>(null);
 const identity=useRef<Capability|null>(saved(key)),latest=useRef<Journey|null>(null),queue=useRef<Promise<void>>(Promise.resolve());
 const accept=useCallback((j:Journey)=>{latest.current=j;setJourney(j);},[]);
 useEffect(()=>{onActivityChange(busy);return()=>onActivityChange(false);},[busy,onActivityChange]);
 useEffect(()=>{let mounted=true;const i=identity.current;if(i)workspaceRequest<Journey>(`/v2/journeys/${encodeURIComponent(i.id)}`,undefined,i.token).then(j=>{if(mounted)accept(j);}).catch(e=>{if(mounted)setError(String(e));});return()=>{mounted=false;};},[accept,active.session]);
 const event=useCallback((input:EventInput)=>{
  const i=identity.current,j=latest.current;if(!i||!j)return;
  const payload={...input,event_id:crypto.randomUUID(),view_id:j.current_view,client_timestamp:new Date().toISOString()};
  queue.current=queue.current.then(async()=>{let value:Journey;try{value=await workspaceRequest<Journey>(`/v2/journeys/${encodeURIComponent(i.id)}/events`,payload,i.token);}catch(e){if(!(e instanceof TypeError))throw e;value=await workspaceRequest<Journey>(`/v2/journeys/${encodeURIComponent(i.id)}/events`,payload,i.token);}accept(value);}).catch(e=>setError(String(e)));
 },[accept]);
 const start=async()=>{setBusy(true);setError('');try{await queue.current;
  const settings=await workspaceRequest<{settings_revision:number}>(`/workspace/sessions/${encodeURIComponent(sid)}/settings`);
  const pendingKey=`${key}:pending`;
  let payload;try{payload=JSON.parse(sessionStorage.getItem(pendingKey)??'null');}catch{payload=null;}
  if(!payload){payload={procedure_id:procedure.procedure_id,request_id:crypto.randomUUID(),capability_token:crypto.randomUUID()+crypto.randomUUID(),expected_revision:settings.settings_revision};sessionStorage.setItem(pendingKey,JSON.stringify(payload));}
  const j=await workspaceRequest<Journey>(`/workspace/sessions/${encodeURIComponent(sid)}/guidance`,payload);
  sessionStorage.removeItem(pendingKey);
  identity.current={id:j.id,token:j.token!};sessionStorage.setItem(key,JSON.stringify(identity.current));sessionStorage.setItem(`c4-v2-capability:${API_BASE}`,JSON.stringify(identity.current));accept(j);requestAnimationFrame(()=>responseRoot.current?.scrollIntoView({behavior:'smooth',block:'start'}));
 }catch(e){if(e instanceof WorkspaceError&&e.status===409)sessionStorage.removeItem(`${key}:pending`);setError(String(e));}finally{setBusy(false);}};
 const adjust=async(configuration:Configuration)=>{setBusy(true);setError('');try{await queue.current;const i=identity.current!,j=latest.current!;accept(await workspaceRequest<Journey>(`/v2/journeys/${encodeURIComponent(i.id)}/adjustments`,{event_id:crypto.randomUUID(),view_id:j.current_view,configuration},i.token));}catch(e){setError(String(e));}finally{setBusy(false);}};
 const rate=async(rating:string)=>{await queue.current;const i=identity.current!,j=latest.current!;try{return await workspaceRequest<Receipt>(`/v2/journeys/${encodeURIComponent(i.id)}/ratings`,{view_id:j.current_view,rating},i.token);}catch(e){setError(String(e));throw e;}};
 return <section ref={responseRoot} className="panel unified-guidance" aria-label="Your guidance"><div className="section-heading"><div><p className="eyebrow">Your guidance</p><h2>{journey?'Guidance for this visit':procedure.title}</h2></div><button className="button button-primary" disabled={disabled||busy} onClick={()=>void start()}>{busy?'Preparing guidance…':'Request fresh guidance'}</button></div>
  <p className="helper-text">{active.kind==='profile'&&active.profile.personalization_enabled?'Saved procedure familiarity, confidence and settings inform the learned support selection.':'Standard guidance. Personalization is off.'} No application action is marked complete by browsing.</p>
  {error&&<p className="alert alert-error" role="alert">{error}</p>}
  {journey?.constraints_revoked&&<p className="notice" role="status">Your accessibility or hard requirements changed. Request fresh guidance to use the updated requirements.</p>}
  {journey&&!journey.constraints_revoked&&<fieldset disabled={disabled||busy} className="v2-shell v2-container"><GuidanceMessage key={journey.current_view} journey={journey} event={event} adjust={c=>void adjust(c)} rate={rate}/></fieldset>}
 </section>;
}
