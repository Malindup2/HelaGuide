import { useCallback, useEffect, useRef, useState } from 'react';
import GuidanceMessage from './GuidanceMessage';
import type { Configuration, EventInput, Inspector, Journey, Receipt } from './types';
import './v2.css';
const BASE = import.meta.env.VITE_C4_V2_API ?? 'http://127.0.0.1:8017';
const KEY = `c4-v2-capability:${BASE}`;
type Identity = {id:string;token:string};
function stored(): Identity | null {try{return JSON.parse(sessionStorage.getItem(KEY)??'null');}catch{return null;}}
async function request<T>(path:string, body?:unknown, token?:string):Promise<T>{
  const response=await fetch(`${BASE}/v2${path}`, {method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json',...(token?{'X-C4-Token':token}:{})},body:body===undefined?undefined:JSON.stringify(body)});
  const value=await response.json(); if(!response.ok)throw Error(value.detail??'V2 request failed'); return value;
}

export default function V2App({inspector=false}:{inspector?:boolean}) {
  const [catalogue,setCatalogue]=useState<{id:string;title:string;synthetic:boolean}[]>([]);
  const [procedure,setProcedure]=useState('synthetic-practice-v2');
  const [familiarity,setFamiliarity]=useState(''), [confidence,setConfidence]=useState('');
  const [journey,setJourney]=useState<Journey|null>(null), [trace,setTrace]=useState<Inspector|null>(null);
  const [error,setError]=useState(''), [busy,setBusy]=useState(false);
  const identity=useRef<Identity|null>(stored()), latest=useRef<Journey|null>(null), queue=useRef<Promise<void>>(Promise.resolve());
  const accept=useCallback((j:Journey)=>{latest.current=j;setJourney(j);},[]);
  const refreshTrace=useCallback(async()=>{const i=identity.current;if(i)setTrace(await request<Inspector>(`/journeys/${encodeURIComponent(i.id)}/inspector`,undefined,i.token));},[]);
  useEffect(()=>{
    let active=true;
    request<typeof catalogue>('/procedures').then(c=>{if(active)setCatalogue(c);}).catch(e=>{if(active)setError(String(e));});
    const i=identity.current;
    if(i){const path=`/journeys/${encodeURIComponent(i.id)}${inspector?'/inspector':''}`;
      request<Journey|Inspector>(path,undefined,i.token).then(v=>{if(active){if(inspector)setTrace(v as Inspector);else accept(v as Journey);}}).catch(e=>{if(active)setError(String(e));});}
    return()=>{active=false;};
  },[inspector,accept]);
  const event=useCallback((e:EventInput)=>{
    const i=identity.current,j=latest.current;if(!i||!j)return;
    const payload={...e,event_id:crypto.randomUUID(),view_id:j.current_view,client_timestamp:new Date().toISOString()};
    queue.current=queue.current.then(async()=>{let result:Journey; try{result=await request<Journey>(`/journeys/${encodeURIComponent(i.id)}/events`,payload,i.token);}catch(error){if(!(error instanceof TypeError))throw error;result=await request<Journey>(`/journeys/${encodeURIComponent(i.id)}/events`,payload,i.token);}accept(result);}).catch(e=>setError(String(e)));
  },[accept]);
  const start=async()=>{setBusy(true);setError('');try{
    await queue.current;
    const j=await request<Journey>('/journeys',{procedure_id:procedure,request_id:crypto.randomUUID(),context:{familiarity:familiarity?Number(familiarity):null,confidence:confidence?Number(confidence):null}});
    identity.current={id:j.id,token:j.token!};sessionStorage.setItem(KEY,JSON.stringify(identity.current));accept(j);
  }catch(e){setError(String(e));}finally{setBusy(false);}};
  const adjust=async(config:Configuration)=>{setBusy(true);setError('');try{await queue.current;const i=identity.current!,j=latest.current!;
    accept(await request<Journey>(`/journeys/${encodeURIComponent(i.id)}/adjustments`,{event_id:crypto.randomUUID(),view_id:j.current_view,configuration:config},i.token));
  }catch(e){setError(String(e));}finally{setBusy(false);}};
  const rate=async(rating:string)=>{await queue.current;const i=identity.current!,j=latest.current!;
    try{return await request<Receipt>(`/journeys/${encodeURIComponent(i.id)}/ratings`,{view_id:j.current_view,rating},i.token);}catch(e){setError(String(e));throw e;}};
  if(inspector)return <main className="v2-shell"><header><h1>C4 V2 Research Inspector</h1><p>Read-only inspection. Scores are linear surrogates, not probabilities or causal explanations.</p><a href="#c4-v2">Citizen response</a> <button onClick={()=>void refreshTrace().catch(e=>setError(String(e)))}>Refresh saved trace</button></header>
    {error&&<p role="alert">{error}</p>}{!trace?<p>Open a V2 journey in this tab first. No journey is created here.</p>:<>
      <h2>Selection</h2><p>{trace.decision.selection_mode} · revision at selection {trace.decision.policy_revision} · seed {trace.decision.draw_seed}</p>
      <pre>{JSON.stringify(trace.decision.configuration,null,2)}</pre><h2>Current policy</h2><pre>{JSON.stringify(trace.policy,null,2)}</pre>
      <h2>Context and structure</h2><pre>{JSON.stringify(trace.decision.context,null,2)}</pre><details><summary>Structural measurements</summary><pre>{JSON.stringify(trace.decision.measurements,null,2)}</pre></details>
      <h2>Feasible candidate scores</h2><div className="v2-table"><table><thead><tr><th>Configuration</th><th>Mean</th><th>SD</th><th>Sampled score</th></tr></thead><tbody>{trace.decision.scores.map(s=><tr key={s.id}><td>{s.id}</td><td>{s.mean.toFixed(5)}</td><td>{s.std.toFixed(5)}</td><td>{s.sampled.toFixed(5)}</td></tr>)}</tbody></table></div>
      <details><summary>All feasibility reasons</summary><pre>{JSON.stringify(trace.decision.evaluation,null,2)}</pre></details>
      <details><summary>{trace.decision.features.length} named selected features</summary><table><tbody>{trace.decision.feature_names.map((n,i)=><tr key={n}><td>{n}</td><td>{trace.decision.features[i]}</td></tr>)}</tbody></table></details>
      <details><summary>Content coverage and frozen document</summary><pre>{JSON.stringify(trace.journey.document,null,2)}</pre></details>
      <details><summary>Opportunities, events and adjusted views</summary><pre>{JSON.stringify({opportunities:trace.journey.opportunities,events:trace.journey.events,views:trace.journey.views},null,2)}</pre></details>
      <p>PP2 individual-history score adjustment: abstain; not implemented.</p>
    </>}</main>;
  return <main className="v2-shell"><header className="v2-demo"><strong>C4 V2 research workspace</strong> <a href="#c4-v2-inspector">Research Inspector</a> · <a href="#">V1 workspace</a>
    <details open={!journey}><summary>Choose procedure and optional starting context</summary><label>Procedure<select value={procedure} onChange={e=>setProcedure(e.target.value)}>{catalogue.map(p=><option key={p.id} value={p.id}>{p.title}</option>)}</select></label>
      <label>Familiarity with this procedure<select value={familiarity} onChange={e=>setFamiliarity(e.target.value)}><option value="">Not supplied</option>{[1,2,3,4,5].map(n=><option key={n}>{n}</option>)}</select></label>
      <label>Navigation confidence<select value={confidence} onChange={e=>setConfidence(e.target.value)}><option value="">Not supplied</option>{[1,2,3,4,5].map(n=><option key={n}>{n}</option>)}</select></label>
      <button disabled={busy} onClick={()=>void start()}>Request guidance</button><p>Research context, not a permanent novice/expert category. A new request begins a new journey.</p></details></header>
    {error&&<p role="alert" className="v2-notice">{error}</p>}
    {journey&&<fieldset disabled={busy} className="v2-container"><GuidanceMessage key={journey.current_view} journey={journey} event={event} adjust={c=>void adjust(c)} rate={rate}/></fieldset>}
  </main>;
}
