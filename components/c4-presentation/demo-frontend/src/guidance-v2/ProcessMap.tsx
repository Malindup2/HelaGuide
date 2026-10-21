import { useId, useState } from 'react';
import type { Document } from './types';
import { expressionText, relationshipLines } from './semantics';

export default function ProcessMap({doc, onAction,event}: {doc: Document; onAction: (id: string) => void; event?:(type:'map_expand'|'map_collapse')=>void}) {
  const [enlarged,setEnlarged]=useState(false);
  const marker = useId().replaceAll(':','');
  // Navigation order is not drawn as edges. Only supplied prerequisite edges are solid.
  const depth=new Map(doc.actions.map(a=>[a.id,0]));
  function refs(e: import('./types').Expression):string[]{
    if(e.kind==='action') return [e.ref!];
    if(e.kind==='selected_option_of') return doc.branches.find(b=>b.group_id===e.ref)?.options.flatMap(o=>o.action_ids)??[];
    return e.children.flatMap(refs);
  }
  const layoutEdges=[...doc.edges,...doc.joins.flatMap(j=>refs(j.requirement).map(id=>({source_id:id,target_id:j.target})))];
  for(let pass=0;pass<doc.actions.length;pass++) for(const e of layoutEdges) depth.set(e.target_id,Math.max(depth.get(e.target_id)!,depth.get(e.source_id)!+1));
  const positions=new Map<string,{x:number;y:number}>();
  const levels=Math.max(...depth.values())+1;
  const maxWidth=Math.max(...Array.from({length:levels},(_,level)=>doc.actions.filter(a=>depth.get(a.id)===level).length));
  const width=Math.max(680,maxWidth*310+40);
  for(let level=0;level<levels;level++){
    const row=doc.actions.filter(a=>depth.get(a.id)===level);
    row.forEach((a,i)=>positions.set(a.id,{x:(width-row.length*310)/2+i*310,y:30+level*170}));
  }
  const height=levels*170+30;
  return <section className={"v2-map"+(enlarged?" v2-map-enlarged":"")} aria-label="Integrated supplied process">
    <div className="section-heading"><h3>Process and responsibilities</h3><button onClick={()=>{setEnlarged(!enlarged);event?.(enlarged?'map_collapse':'map_expand');}}>{enlarged?'Compact map':'Enlarge map'}</button></div>
    <p>All supplied actions and relationships. Arrows describe prerequisites, not completed work.</p>
    {doc.stage_edges.length>0 && <aside className="v2-service-flow"><strong>Service-level dependencies</strong>{doc.stage_edges.map((e,i)=><p key={i}>{doc.stages.find(s=>s.service_id===e.source_id)?.name} → {doc.stages.find(s=>s.service_id===e.target_id)?.name}</p>)}<small>These do not add action-level prerequisites.</small></aside>}
    <div className="v2-map-canvas" tabIndex={0} aria-label="Scrollable process diagram"><svg viewBox={`0 0 ${width} ${height}`} role="group" aria-label="Procedure map. A complete text equivalent follows.">
      <defs><marker id={marker} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" /></marker></defs>
      {doc.edges.map((e,i) => {const s=positions.get(e.source_id)!, t=positions.get(e.target_id)!; return <path key={i} d={`M ${s.x+145} ${s.y+84} C ${s.x+145} ${s.y+105},${t.x+145} ${t.y-20},${t.x+145} ${t.y}`} markerEnd={`url(#${marker})`} className="v2-edge"/>;})}
      {doc.joins.flatMap((j,ji)=>refs(j.requirement).map((source,si)=>{const s=positions.get(source)!,t=positions.get(j.target)!;
        return <g key={`join-${ji}-${si}`}><path d={`M ${s.x+145} ${s.y+84} L ${t.x+145} ${t.y}`} className="v2-conditional-edge" markerEnd={`url(#${marker})`}/>
          <text x={(s.x+t.x)/2+145} y={(s.y+t.y)/2+65} textAnchor="middle" fontSize="11">conditional join*</text></g>;}))}
      {doc.actions.map(a => {const p=positions.get(a.id)!; return <g key={a.id} transform={`translate(${p.x},${p.y})`}>
        <rect width="290" height="84" rx="10"/>
        <foreignObject width="290" height="84"><button className="v2-map-node" onClick={()=>onAction(a.id)}>{a.title}<small>{a.actor ?? `Service: ${a.service_agency}`}</small>{a.branch && <small>Conditional route action</small>}</button></foreignObject>
      </g>;})}
    </svg></div>
    <div className="v2-map-mobile" aria-label="Compact process map">
      {doc.actions.map(a=><section key={a.id}><button onClick={()=>onAction(a.id)}>{a.title}</button><small>{a.actor ?? `Service: ${a.service_agency}`}</small>
        {a.conditions.length>0 && <p>{a.conditions.join(' AND ')}</p>}
        {doc.edges.filter(e=>e.target_id===a.id).map(e=><p key={e.source_id}>Requires: <button onClick={()=>onAction(e.source_id)}>{doc.actions.find(x=>x.id===e.source_id)?.title}</button></p>)}
        {doc.joins.filter(j=>j.target===a.id).map((j,i)=><p key={i}>Requires {expressionText(j.requirement,doc)}</p>)}
      </section>)}
    </div>
    <div className="v2-map-groups">{doc.joins.length>0&&<p>* Dashed join links describe the requirement expression below; they do not require all alternative routes.</p>}
      {doc.branches.map(b=><section key={b.group_id}><strong>{b.selection === 'XOR' ? 'One applicable route' : b.selection==='AND'?'Joint requirements':'One or more applicable options'}</strong>
        {b.options.map(o=><p key={o.option_id}>{o.condition_ids.map(id=>doc.conditions.find(c=>c.condition_id===id)?.text).join(' AND ')}: {doc.actions.filter(a=>o.action_ids.includes(a.id)).map(a=>a.title).join(' · ')}</p>)}
      </section>)}
      {doc.joins.map((j,i)=><p key={`j${i}`}><strong>{doc.actions.find(a=>a.id===j.target)?.title}:</strong> requires {expressionText(j.requirement,doc)}.</p>)}
      {doc.parallel.map(p=><p key={p.group_id}><strong>Explicit parallel group:</strong> {p.action_ids.map(id=>doc.actions.find(a=>a.id===id)?.title).join(' + ')}</p>)}
      {doc.parallel_areas.map((p,i)=><p key={`p${i}`}><strong>Explicit parallel areas:</strong> {p.map(e=>expressionText(e,doc)).join(' + ')}</p>)}
    </div>
    <details><summary>Complete text equivalent</summary><ul>{relationshipLines(doc).map((line,i)=><li key={i}>{line}</li>)}</ul>
      {doc.stage_edges.map((e,i)=><p key={i}>Service dependency: {doc.stages.find(s=>s.service_id===e.source_id)?.name} precedes {doc.stages.find(s=>s.service_id===e.target_id)?.name}. This does not create extra action prerequisites.</p>)}
      <ul>{doc.actions.map(a=><li key={a.id}>{a.title}: {a.actor ?? `service agency ${a.service_agency}; action owner not supplied`}. {a.conditions.join(' ')}</li>)}</ul>
    </details>
  </section>;
}
