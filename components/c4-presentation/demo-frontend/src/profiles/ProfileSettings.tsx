import {useEffect,useState} from 'react';
import type {ActiveIdentity,GuestSession,ProcedureSummary} from '../api/types';
import {workspaceRequest} from '../guidance-v2/workspaceClient';

type Settings={session:GuestSession;preferences:Record<string,string>;locks:Record<string,string>;legacy_review:Record<string,unknown>;settings_revision:number};
const choices:Record<string,{label:string;states:[string,string][]}>={
 navigation:{label:'Navigation',states:[['overview','Full overview'],['guided','Focused guidance']]},
 explanation:{label:'Explanation depth',states:[['concise','Concise instructions'],['expanded','Expanded explanation']]},
 disclosure:{label:'Optional information',states:[['collapsed','Start collapsed'],['expanded','Start expanded']]},
 relationships:{label:'Relationship support',states:[['none','No additional aid'],['inline','Inline cues'],['map','Integrated process map']]},
 recap:{label:'Earlier-viewed steps in this journey',states:[['off','No automatic recap'],['on','Offer earlier-step recap']]},
 summary:{label:'Consolidated preparation summary',states:[['off','Action-level requirements'],['on','Preparation at a glance']]},
};
export default function ProfileSettings({active,procedures,onSession}:{active:ActiveIdentity;procedures:ProcedureSummary[];onSession:(s:GuestSession)=>void}){
 const [settings,setSettings]=useState<Settings|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[notice,setNotice]=useState('');
 const path=`/workspace/sessions/${encodeURIComponent(active.session.session_id)}/settings`;
 const services=[...new Map(procedures.map(p=>[p.requested_service_id,p])).values()];
 useEffect(()=>{let mounted=true;workspaceRequest<Settings>(path).then(s=>{if(mounted)setSettings(s);}).catch(e=>{if(mounted)setError(String(e));});return()=>{mounted=false;};},[path]);
 const update=(group:'preferences'|'locks',key:string,value:string)=>setSettings(old=>{if(!old)return old;const next={...old[group]};if(value)next[key]=value;else delete next[key];return {...old,[group]:next};});
 const save=async()=>{if(!settings)return;setBusy(true);setError('');try{
  const result=await workspaceRequest<Settings>(path,{request_id:crypto.randomUUID(),expected_revision:settings.settings_revision,
   context:{navigation_capability:settings.session.settings.navigation_capability,accessibility:settings.session.settings.accessibility},
   familiarity:settings.session.settings.familiarity,preferences:settings.preferences,locks:settings.locks},undefined,'PATCH');
  setSettings(result);onSession(result.session);setNotice('Saved for future requests. Request fresh guidance to use the updated settings.');
 }catch(e){setError(String(e));}finally{setBusy(false);}};
 return <details className="profile-settings"><summary>{active.kind==='profile'?'Edit saved context, preferences and accessibility':'Optional accessibility and display settings'}</summary>
 <button type="button" className="text-button" disabled={busy} onClick={()=>void workspaceRequest<Settings>(path).then(s=>{setSettings(s);setError('');setNotice('Latest saved settings loaded.');}).catch(e=>setError(String(e)))}>Reload saved settings</button><p className="helper-text">Answers stay saved. You can update them when your needs change; no repeated questionnaire is required.</p>
 {error&&<p role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}
 {settings&&<fieldset disabled={busy} className="form-fields"><legend className="sr-only">Reusable context settings</legend>
 {active.kind==='profile'&&<><label>Navigation confidence<select value={settings.session.settings.navigation_capability??''} onChange={e=>setSettings({...settings,session:{...settings.session,settings:{...settings.session.settings,navigation_capability:e.target.value?Number(e.target.value) as 1|2|3|4|5:null}}})}><option value="">Unknown</option>{[1,2,3,4,5].map(n=><option key={n}>{n}</option>)}</select></label>
 <details><summary>Familiarity with each procedure</summary>{services.map(p=><label key={p.requested_service_id}>{p.title}<select value={settings.session.settings.familiarity.find(f=>f.service_id===p.requested_service_id)?.score??''} onChange={e=>setSettings({...settings,session:{...settings.session,settings:{...settings.session.settings,familiarity:[...settings.session.settings.familiarity.filter(f=>f.service_id!==p.requested_service_id),{service_id:p.requested_service_id,score:e.target.value?Number(e.target.value) as 1|2|3|4|5:null,source:'self_reported'}]}}})}><option value="">Unknown / not supplied</option>{[1,2,3,4,5].map(n=><option key={n}>{n}</option>)}</select></label>)}</details>
 <details><summary>Optional presentation preferences</summary><p className="helper-text">These inform the learned model; they do not force a configuration.</p>{Object.entries(choices).map(([key,c])=><label key={key}>{c.label}<select value={settings.preferences[key]??''} onChange={e=>update('preferences',key,e.target.value)}><option value="">Let the system choose</option>{c.states.map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>)}</details></>}
 <details><summary>Accessibility and explicit requirements</summary>
 {(['allow_relationship_visuals','allow_collapsed_content','allow_guided_navigation'] as const).map((name,i)=><label className="check-row" key={name}><input type="checkbox" checked={settings.session.settings.accessibility[name]} onChange={e=>setSettings({...settings,session:{...settings.session,settings:{...settings.session.settings,accessibility:{...settings.session.settings.accessibility,[name]:e.target.checked}}}})}/>{['Allow optional diagrams','Allow optional details to start collapsed','Allow focused navigation'][i]}</label>)}
 {active.kind==='profile'&&<details><summary>Require a particular support state</summary><p>Requirements constrain selection. Conflicting or unsupported requirements produce a clear error.</p>{Object.entries(choices).map(([key,c])=><label key={key}>{c.label}<select value={settings.locks[key]??''} onChange={e=>update('locks',key,e.target.value)}><option value="">No requirement</option>{c.states.map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>)}</details>}
 </details>
 {Object.keys(settings.legacy_review).length>0&&<p className="notice">This copied profile contains older map, recap or prerequisite choices. Those meanings have changed. Review the preferences above; saving explicitly confirms the displayed choices for future guidance.</p>}
 <button className="button button-primary" onClick={()=>void save()} type="button">{busy?'Saving…':'Save settings'}</button>
 </fieldset>}
 </details>;
}
