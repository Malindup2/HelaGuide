/** Separate read-only research view; the old standalone citizen form is retired. */
import {useCallback,useEffect,useState} from 'react';
import {API_BASE} from '../api/client';
import type {Inspector} from './types';
import {workspaceRequest} from './workspaceClient';
import './v2.css';
export default function ResearchInspector(){
 const [trace,setTrace]=useState<Inspector|null>(null),[error,setError]=useState('');
 const refreshTrace=useCallback(async()=>{let identity;try{identity=JSON.parse(sessionStorage.getItem(`c4-v2-capability:${API_BASE}`)??'null');}catch{identity=null;}if(identity)setTrace(await workspaceRequest<Inspector>(`/v2/journeys/${encodeURIComponent(identity.id)}/inspector`,undefined,identity.token));},[]);
 useEffect(()=>{let mounted=true;let identity;try{identity=JSON.parse(sessionStorage.getItem(`c4-v2-capability:${API_BASE}`)??'null');}catch{identity=null;}
  if(identity)workspaceRequest<Inspector>(`/v2/journeys/${encodeURIComponent(identity.id)}/inspector`,undefined,identity.token).then(value=>{if(mounted)setTrace(value);}).catch(e=>{if(mounted)setError(String(e));});
  return()=>{mounted=false;};
 },[]);
 return <main className="v2-shell"><header><h1>C4 Research Inspector</h1><p>Read-only inspection. Scores are linear surrogates, not probabilities or causal explanations.</p><a href="#c4-v2">Citizen response</a> <button onClick={()=>void refreshTrace().catch(e=>setError(String(e)))}>Refresh saved trace</button></header>
    {error&&<p role="alert">{error}</p>}{!trace?<p>Request guidance in the citizen workspace first. This page does not create a journey.</p>:<>
      <h2>Selection</h2><p>{trace.decision.selection_mode} · revision at selection {trace.decision.policy_revision} · seed {trace.decision.draw_seed}</p>
      <pre>{JSON.stringify(trace.decision.configuration,null,2)}</pre><h2>Current policy</h2><pre>{JSON.stringify(trace.policy,null,2)}</pre>
      <h2>Effective context and sources</h2><pre>{JSON.stringify(trace.decision.effective_context,null,2)}</pre><h2>Context and structure</h2><pre>{JSON.stringify(trace.decision.context,null,2)}</pre><details><summary>Structural measurements</summary><pre>{JSON.stringify(trace.decision.measurements,null,2)}</pre></details>
      <h2>Feasible candidate scores</h2><div className="v2-table"><table><thead><tr><th>Configuration</th><th>Mean</th><th>SD</th><th>Sampled score</th></tr></thead><tbody>{trace.decision.scores.map(s=><tr key={s.id}><td>{s.id}</td><td>{s.mean.toFixed(5)}</td><td>{s.std.toFixed(5)}</td><td>{s.sampled.toFixed(5)}</td></tr>)}</tbody></table></div>
      <details><summary>All feasibility reasons</summary><pre>{JSON.stringify(trace.decision.evaluation,null,2)}</pre></details>
      <details><summary>{trace.decision.features.length} named selected features</summary><table><tbody>{trace.decision.feature_names.map((n,i)=><tr key={n}><td>{n}</td><td>{trace.decision.features[i]}</td></tr>)}</tbody></table></details>
      <details><summary>Content coverage and frozen document</summary><pre>{JSON.stringify(trace.journey.document,null,2)}</pre></details>
      <details><summary>Opportunities, events and adjusted views</summary><pre>{JSON.stringify({opportunities:trace.journey.opportunities,events:trace.journey.events,views:trace.journey.views},null,2)}</pre></details>
      <p>PP2 individual-history score adjustment: abstain; not implemented.</p>
    </>}</main>;
}
