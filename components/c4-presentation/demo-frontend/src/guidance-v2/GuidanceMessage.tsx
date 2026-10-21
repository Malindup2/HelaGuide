import { useEffect, useRef, useState } from 'react';
import type {ReactNode} from 'react';
import type { Action, Configuration, Document, EventInput, Journey, Receipt } from './types';
import { expressionText, previousActions } from './semantics';
import ProcessMap from './ProcessMap';

function factLabel(f: Document['facts'][number], doc: Document) {
  if(f.kind==='document') return f.name;
  const scope=doc.stages.find(s=>s.fee_fact_id===f.fact_id)?.name;
  return `${scope ? `${scope}: ` : 'Recorded charge: '}${f.currency} ${f.value}`;
}

function ActionPanel({action, doc, config, viewId, event, jump, recap}: {action: Action; doc: Document; config: Configuration; viewId: string; event: (e: EventInput)=>void; jump:(id:string)=>void; recap?:ReactNode}) {
  const ref=useRef<HTMLElement>(null);
  useEffect(()=>{
    const element=ref.current;
    if(!element) return;
    const observer=new IntersectionObserver(entries=>{if(entries.some(e=>e.isIntersecting)){event({type:'action_visible',action_id:action.id});observer.disconnect();}}, {threshold:0.1});
    observer.observe(element); return ()=>observer.disconnect();
  },[action.id,viewId,event]);
  const prerequisites=doc.edges.filter(e=>e.target_id===action.id);
  return <article ref={ref} id={`v2-${action.id}`} className="v2-action" tabIndex={-1}>
    <h3>{action.title}</h3>{recap}
    <p className="v2-muted">{action.actor?`Responsible: ${action.actor}`:`Service agency: ${action.service_agency}`}</p>
    {action.conditions.length>0 && <p className="v2-condition"><strong>Applies when:</strong> {action.conditions.join(' AND ')}</p>}
    {config.relationships==='none' && prerequisites.length>0 && <p className="v2-muted">Prerequisites: {prerequisites.map(p=>doc.actions.find(a=>a.id===p.source_id)?.title).join('; ')}.</p>}
    {config.relationships!=='none' && prerequisites.length>0 && <aside>Before this: {prerequisites.map(p=><button key={p.source_id} onClick={()=>jump(p.source_id)}>{doc.actions.find(a=>a.id===p.source_id)?.title}</button>)}</aside>}
    {doc.joins.filter(j=>j.target===action.id).map((j,i)=><aside key={i}>Requires {expressionText(j.requirement,doc)}.</aside>)}
    {config.summary==='off' && action.fact_ids.length>0 && <p className="v2-facts">{action.fact_ids.map(id=>doc.facts.find(f=>f.fact_id===id)).filter(f=>f!==undefined).map(f=>factLabel(f,doc)).join(' · ')}</p>}
    <div className="v2-prose">{(config.explanation==='expanded'?action.expanded:action.concise).split('\n\n').map((p,i)=><p key={i}>{p}</p>)}</div>
    {action.optional.map(block=><details key={`${viewId}:${block.id}`} open={config.disclosure==='expanded'} >
      <summary onClick={e=>event({type:(e.currentTarget.parentElement as HTMLDetailsElement).open?'detail_close':'detail_open',action_id:action.id,value:block.id})}>Optional explanation</summary><p>{block.text}</p></details>)}
    {action.unreviewed_supplement.map((text,i)=><p key={i}>{text}</p>)}
  </article>;
}

export function PreparationSummary({doc}: {doc: Document}) {
  return <aside className="v2-summary"><h3>Preparation at a glance</h3>
    <ul>{doc.facts.map(f=><li key={f.fact_id}>{factLabel(f,doc)}
      <small>{doc.actions.filter(a=>a.fact_ids.includes(f.fact_id) && (f.kind!=='fee' || doc.stages.some(stage=>stage.fee_fact_id===f.fact_id&&stage.service_id===a.service_id))).map(a=>`${a.title}${a.conditions.length?` (${a.conditions.join(' AND ')})`:''}`).join('; ') || (f.kind==='fee'?'Service-level charge; no action-level fee inferred.':'Service-level fact; action scope not supplied')}</small>
    </li>)}</ul><p>Charges are not added into a total. Read each action for timing, exclusions and applicable conditions.</p>
    {doc.actions.some(a=>a.actor) && <p>{doc.actions.filter(a=>a.actor).map(a=>`${a.title}: ${a.actor}`).join(' · ')}</p>}
  </aside>;
}

export default function GuidanceMessage({journey,event,adjust,rate}: {journey: Journey; event:(e:EventInput)=>void; adjust:(c:Configuration)=>void; rate:(r:string)=>Promise<Receipt>}) {
  const view=journey.views[journey.current_view], config=view.configuration, doc=journey.document;
  const [focus,setFocus]=useState(journey.focus ?? doc.actions[0]?.id ?? '');
  const [negative,setNegative]=useState(false), [receipt,setReceipt]=useState<Receipt|null>(null);
  const current=doc.actions.find(a=>a.id===focus) ?? doc.actions[0];
  const previous=previousActions(journey,current.id);
  const controls=useRef<HTMLElement>(null);
  useEffect(()=>{
    const observer=new IntersectionObserver(entries=>{for(const entry of entries) if(entry.isIntersecting){
      const dimension=(entry.target as HTMLElement).dataset.dimension;
      if(dimension) event({type:'opportunity_visible',opportunity_id:`${view.id}:${dimension}`});
      observer.unobserve(entry.target);
    }},{threshold:0.5});
    controls.current?.querySelectorAll('[data-dimension]').forEach(el=>observer.observe(el));
    return()=>observer.disconnect();
  },[view.id,event]);
  const browsing=doc.actions.filter(a=>!a.branch || doc.branches.find(b=>b.group_id===a.branch)?.selection!=='XOR' || !journey.focused_routes?.[a.branch] || journey.focused_routes[a.branch]===a.option);
  const position=browsing.findIndex(a=>a.id===current.id);
  const jump=(id:string)=>{setFocus(id);event({type:'navigate',action_id:id}); if(config.navigation==='overview') document.getElementById(`v2-${id}`)?.scrollIntoView({behavior:'smooth',block:'start'});};
  const change=<K extends keyof Configuration>(key:K,value:Configuration[K])=>adjust({...config,[key]:value});
  const allowed=(key:keyof Configuration,value:string)=>doc.capabilities[key].states.includes(value) && (!journey.available_configurations || journey.available_configurations.some(c=>Object.entries({...config,[key]:value}).every(([k,v])=>c[k as keyof Configuration]===v)));
  const actions=config.navigation==='guided'?[current]:doc.actions;
  const feedback=receipt ?? view.rating;
  const submit=async(r:string)=>{try {setReceipt(await rate(r));setNegative(false);} catch { /* Parent shows the request error; keep feedback available for retry. */ }};
  return <section className="v2-message" aria-label="Procedural guidance">
    <header><span className="v2-eyebrow">HelaGuide · {doc.synthetic?'Fictional research example':'Bounded source snapshot'}</span><h2>{doc.title}</h2><p>{doc.scope}</p></header>
    {Object.values(doc.completeness).some(v=>v!=='complete') && <p className="v2-notice">Some procedure coverage is incomplete. Missing relationships do not establish independence. This response covers the supplied scope.</p>}
    <details className="v2-adjustments"><summary>Adjust support for this visit</summary><nav ref={controls} className="v2-controls" aria-label="Adjust support for this visit">
      <button data-dimension="navigation" disabled={!allowed('navigation',config.navigation==='guided'?'overview':'guided')} onClick={()=>change('navigation',config.navigation==='guided'?'overview':'guided')}>{config.navigation==='guided'?'Show overview':'Guide me'}</button>
      <button data-dimension="explanation" disabled={!allowed('explanation',config.explanation==='expanded'?'concise':'expanded')} onClick={()=>change('explanation',config.explanation==='expanded'?'concise':'expanded')}>{config.explanation==='expanded'?'Less explanation':'More explanation'}</button>
      {doc.capabilities.disclosure.applicable && <button data-dimension="disclosure" disabled={!allowed('disclosure',config.disclosure==='expanded'?'collapsed':'expanded')} onClick={()=>change('disclosure',config.disclosure==='expanded'?'collapsed':'expanded')}>{config.disclosure==='expanded'?'Collapse optional details':'Expand optional details'}</button>}
      {doc.capabilities.relationships.applicable && <><button data-dimension="relationships" disabled={!allowed('relationships',config.relationships==='map'?'none':'map')} onClick={()=>change('relationships',config.relationships==='map'?'none':'map')}>{config.relationships==='map'?'Hide map':'Show map'}</button><button disabled={!allowed('relationships',config.relationships==='inline'?'none':'inline')} onClick={()=>change('relationships',config.relationships==='inline'?'none':'inline')}>{config.relationships==='inline'?'Hide relationship cues':'Inline relationship cues'}</button></>}
      {doc.capabilities.recap.applicable && <button data-dimension="recap" disabled={!allowed('recap',config.recap==='on'?'off':'on')} onClick={()=>change('recap',config.recap==='on'?'off':'on')}>{config.recap==='on'?'Hide earlier-step recap':'Show earlier-step recap'}</button>}
      {doc.capabilities.summary.applicable && <button data-dimension="summary" disabled={!allowed('summary',config.summary==='on'?'off':'on')} onClick={()=>change('summary',config.summary==='on'?'off':'on')}>{config.summary==='on'?'Hide preparation summary':'Preparation summary'}</button>}
      {view.parent && <button onClick={()=>adjust(journey.views[view.parent!].configuration)}>Undo latest adjustment</button>}
    </nav></details>
    {config.relationships!=='map' && (doc.stage_edges.length>0||doc.parallel.length>0||doc.parallel_areas.length>0) && <aside className="v2-essential-relationships"><h3>Supplied process relationships</h3>
      {doc.stage_edges.length>0&&<><strong>Service-level dependencies</strong>{doc.stage_edges.map((edge,i)=><p key={`stage-${i}`}>{doc.stages.find(s=>s.service_id===edge.target_id)?.name} depends on {doc.stages.find(s=>s.service_id===edge.source_id)?.name}. This does not add action-level prerequisites.</p>)}</>}
      {doc.parallel.map(group=><p key={group.group_id}>Explicit parallel work: {doc.actions.filter(a=>group.action_ids.includes(a.id)).map(a=>a.title).join(' + ')}.</p>)}
      {doc.parallel_areas.map((area,i)=><p key={`area-${i}`}>Explicit parallel work areas: {area.map(e=>expressionText(e,doc)).join(' + ')}.</p>)}
    </aside>}
    {config.summary==='on' && <PreparationSummary doc={doc}/>}
    {config.summary==='off' && doc.facts.some(f=>!doc.actions.some(a=>a.fact_ids.includes(f.fact_id))) && <aside className="v2-summary"><h3>Additional supplied requirements</h3><ul>{doc.facts.filter(f=>!doc.actions.some(a=>a.fact_ids.includes(f.fact_id))).map(f=><li key={f.fact_id}>{factLabel(f,doc)} (service-level scope)</li>)}</ul></aside>}
    {config.relationships==='map' && <section className="process-section"><div className="section-heading"><h3>Your process at a glance</h3><button disabled={!allowed('relationships','none')} onClick={()=>change('relationships','none')}>Hide map</button></div><ProcessMap doc={doc} onAction={jump} event={type=>event({type})}/></section>}
    {doc.branches.map(b=><section className="v2-route" key={b.group_id}><h3>{b.selection==='XOR'?'Choose the applicable route':b.selection==='AND'?'Joint requirements':'Applicable options'}</h3>
      <p>{b.selection==='XOR'?'These are supplied alternatives. Focusing a route does not determine eligibility.':b.selection==='AND'?'These supplied options are joint requirements.':'More than one option may apply. Check each supplied condition; all options remain available.'}</p>
      {b.options.map(o=><div key={o.option_id}><strong>{o.condition_ids.map(id=>doc.conditions.find(c=>c.condition_id===id)?.text).join(' AND ') || 'No additional condition supplied'}</strong>
        <p>{doc.actions.filter(a=>o.action_ids.includes(a.id)).map(a=>a.title).join(' · ')}</p>
        {b.selection==='XOR'&&<button onClick={()=>{event({type:'route_focus',value:o.option_id});jump(doc.actions.find(a=>o.action_ids.includes(a.id))!.id);}}>Focus this route</button>}</div>)}
    </section>)}
    <nav className="v2-index" aria-label="All guidance actions">{doc.actions.map(a=><button key={a.id} aria-current={focus===a.id?'step':undefined} onClick={()=>jump(a.id)}>{a.title}</button>)}</nav>
    {actions.map(a=><ActionPanel key={a.id} action={a} doc={doc} config={config} viewId={view.id} event={event} jump={jump} recap={a.id===current.id?(config.recap==='on' && previous.length>0 && <aside className="v2-recap"><details onToggle={e=>{if(e.currentTarget.open)event({type:'recap_open',action_id:current.id});}}><summary>Earlier in this journey ({previous.length})</summary><p>Viewed guidance; completion has not been confirmed.</p>{previous.map(a=><p key={a.id}>{a.recap} <button onClick={()=>jump(a.id)}>Revisit</button></p>)}</details></aside>):null}/>)}
    {config.navigation==='guided' && <nav className="v2-controls" aria-label="Browse guidance"><button disabled={position<=0} onClick={()=>jump(browsing[position-1].id)}>Back</button><span>Browsing guidance, not confirming completion</span><button disabled={position===browsing.length-1} onClick={()=>jump(browsing[Math.max(0,position+1)].id)}>Next</button></nav>}
    <footer className="v2-feedback"><p>Was the amount of help right?</p>{feedback?<p role="status">Saved: {feedback.rating.replaceAll('_',' ')}. {feedback.eligible?'Recorded for the selected presentation.':journey.routing==='standard'?'Standard guidance; no policy update.':feedback.exclusion_reason==='personalization_revoked'?'Personalization disabled; no policy update.':'Adjusted view; no policy update.'}</p>:<><button disabled={!view.displayed.length} onClick={()=>void submit('about_right')} aria-label="About right">👍</button><button disabled={!view.displayed.length} onClick={()=>setNegative(true)} aria-label="Support did not fit">👎</button>{negative && <div><button onClick={()=>void submit('need_more')}>Need more support</button><button onClick={()=>void submit('too_much')}>Too much support</button></div>}</>}
      {feedback && feedback.rating!=='about_right' && <details><summary>Optional: was the current explanation depth the main issue?</summary><button onClick={()=>event({type:'reason',value:'explanation'})}>Yes, explanation depth</button><button onClick={()=>event({type:'reason',value:'other_or_unsure'})}>Something else / unsure</button></details>}
    </footer>
    <details onToggle={e=>{if(e.currentTarget.open)event({type:'source_open'});}}><summary>Sources, requirements and scope</summary><p>{doc.scope}</p><PreparationSummary doc={doc}/>{doc.sources.map(s=><p key={s.evidence_id}><a href={s.source_url} target="_blank" rel="noreferrer">Source passage</a>{s.retrieved_at?` · retrieved ${s.retrieved_at}`:' · authored fictional evidence'}<br/>{s.text}</p>)}</details>
  </section>;
}
