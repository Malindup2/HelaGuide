import { useEffect, useId, useRef, useState } from 'react';
import type { Document, Expression } from './types';
import { expressionText, relationshipLines } from './semantics';
import { actionMarks, displayTitle } from './presentation';

const NW = 236, NH = 92, GX = 28, GY = 70, PAD = 24;

function refs(e: Expression, doc: Document): string[] {
  if (e.kind === 'action') return [e.ref!];
  if (e.kind === 'selected_option_of') return doc.branches.find(b => b.group_id === e.ref)?.options.flatMap(o => o.action_ids) ?? [];
  return e.children.flatMap(c => refs(c, doc));
}

const titleOf = (doc: Document, id: string) => { const a = doc.actions.find(x => x.id === id); return a ? displayTitle(a) : id; };
const BRANCH_BADGE = { XOR: 'Choose one route', AND: 'All of these', OR: 'Some may apply' } as const;

function layout(doc: Document) {
  // Navigation order is not drawn as edges. Only supplied prerequisite edges are solid.
  const depth = new Map(doc.actions.map(a => [a.id, 0]));
  const layoutEdges = [...doc.edges, ...doc.joins.flatMap(j => refs(j.requirement, doc).map(id => ({ source_id: id, target_id: j.target })))];
  for (let pass = 0; pass < doc.actions.length; pass++) for (const e of layoutEdges) depth.set(e.target_id, Math.max(depth.get(e.target_id)!, depth.get(e.source_id)! + 1));
  const levels = Math.max(...depth.values()) + 1;
  const rows = Array.from({ length: levels }, (_, level) => doc.actions.filter(a => depth.get(a.id) === level));
  const widest = Math.max(...rows.map(r => r.length));
  const width = Math.max(560, widest * NW + (widest - 1) * GX + PAD * 2);
  const positions = new Map<string, { x: number; y: number }>();
  rows.forEach((row, level) => row.forEach((a, i) => positions.set(a.id, { x: (width - (row.length * NW + (row.length - 1) * GX)) / 2 + i * (NW + GX), y: PAD + 20 + level * (NH + GY) })));
  return { positions, width, height: levels * (NH + GY) + PAD * 2 };
}

function MapSvg({ doc, onAction }: { doc: Document; onAction: (id: string) => void }) {
  const marker = useId().replaceAll(':', '');
  const { positions, width, height } = layout(doc), marks = actionMarks(doc);
  const badge = new Map<string, string>();
  for (const b of doc.branches) for (const o of b.options) for (const id of o.action_ids) badge.set(id, BRANCH_BADGE[b.selection]);
  for (const p of doc.parallel) for (const id of p.action_ids) badge.set(id, badge.has(id) ? `${badge.get(id)} · can run in parallel` : 'Can run in parallel');
  const frames = doc.branches.filter(b => b.options.length > 1).flatMap(b => {
    const members = new Set(b.options.flatMap(o => o.action_ids));
    const pts = [...members].map(id => positions.get(id)!).filter(Boolean);
    if (pts.length < 2) return [];
    const x1 = Math.min(...pts.map(p => p.x)) - 10, y1 = Math.min(...pts.map(p => p.y)) - 24, x2 = Math.max(...pts.map(p => p.x)) + NW + 10, y2 = Math.max(...pts.map(p => p.y)) + NH + 10;
    const clean = doc.actions.every(a => members.has(a.id) || !positions.has(a.id) || (positions.get(a.id)!.x + NW < x1 || positions.get(a.id)!.x > x2 || positions.get(a.id)!.y + NH < y1 || positions.get(a.id)!.y > y2));
    return clean ? [{ b, x1, y1, x2, y2 }] : [];
  });
  return <svg viewBox={`0 0 ${width} ${height}`} role="group" aria-label="Procedure map. A complete text equivalent follows.">
    <defs><marker id={marker} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" /></marker></defs>
    {frames.map(f => <g key={f.b.group_id}><rect className="v2-frame" x={f.x1} y={f.y1} width={f.x2 - f.x1} height={f.y2 - f.y1} rx="14" />
      <text className="v2-frame-label" x={f.x1 + 12} y={f.y1 + 16}>{BRANCH_BADGE[f.b.selection]}</text></g>)}
    {doc.edges.map((e, i) => {
      const s = positions.get(e.source_id)!, t = positions.get(e.target_id)!;
      return <path key={i} d={`M ${s.x + NW / 2} ${s.y + NH} C ${s.x + NW / 2} ${s.y + NH + 34},${t.x + NW / 2} ${t.y - 34},${t.x + NW / 2} ${t.y}`} markerEnd={`url(#${marker})`} className="v2-edge" />;
    })}
    {doc.joins.flatMap((j, ji) => refs(j.requirement, doc).map((source, si) => {
      const s = positions.get(source)!, t = positions.get(j.target)!, label = j.requirement.kind === 'all_of' ? 'all of' : j.requirement.kind === 'any_of' ? 'one of' : null;
      return <g key={`join-${ji}-${si}`}><path d={`M ${s.x + NW / 2} ${s.y + NH} L ${t.x + NW / 2} ${t.y}`} className="v2-conditional-edge" markerEnd={`url(#${marker})`} />
        {label && si === 0 && <text className="v2-join-label" textAnchor="end" x={t.x - 10} y={t.y + NH / 2 + 4}>needs {label}</text>}</g>;
    }))}
    {doc.actions.map(a => {
      const p = positions.get(a.id)!, mark = marks.get(a.id)!;
      return <g key={a.id} transform={`translate(${p.x},${p.y})`}><rect width={NW} height={NH} rx="12" />
        <foreignObject width={NW} height={NH}><button type="button" className="v2-map-node" title={displayTitle(a)} onClick={() => onAction(a.id)}>
          <span className={`v2-map-num v2-num-${mark.kind}`} aria-hidden="true">{mark.label || '•'}</span><span className="v2-map-title">{displayTitle(a)}</span>
          {(badge.get(a.id) || a.actor) && <small>{[badge.get(a.id), a.actor].filter(Boolean).join(' · ')}</small>}</button></foreignObject></g>;
    })}
  </svg>;
}

export default function ProcessMap({ doc, onAction, event, onHide, hideDisabled }: {
  doc: Document; onAction: (id: string) => void; event?: (type: 'map_expand' | 'map_collapse') => void; onHide?: () => void; hideDisabled?: boolean;
}) {
  const [enlarged, setEnlarged] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = dialog.current;
    if (!enlarged || !d) return;
    if (typeof d.showModal === 'function') { if (!d.open) d.showModal(); } else d.setAttribute('open', '');
  }, [enlarged]);
  const isOpen = useRef(false);
  const open = () => { isOpen.current = true; setEnlarged(true); event?.('map_expand'); };
  const close = () => { if (!isOpen.current) return; isOpen.current = false; setEnlarged(false); event?.('map_collapse'); };
  const goto = (id: string) => { close(); onAction(id); };

  return <section className="v2-map" aria-label="Integrated supplied process" data-support="relationships">
    <div className="v2-map-head"><div><h3>Process map</h3><p className="v2-fine">All supplied actions and how they connect. Arrows show what comes first, not what has been done.</p></div>
      <div className="v2-map-actions"><button type="button" onClick={open}>Enlarge map</button>
        {onHide && <button type="button" disabled={hideDisabled} onClick={onHide}>Hide map</button>}</div></div>
    {doc.stage_edges.length > 0 && <aside className="v2-service-flow"><strong>Service-level dependencies</strong>{doc.stage_edges.map((e, i) => <p key={i}>{doc.stages.find(s => s.service_id === e.source_id)?.name} → {doc.stages.find(s => s.service_id === e.target_id)?.name}</p>)}<small>These do not add action-level prerequisites.</small></aside>}
    <div className="v2-map-canvas" tabIndex={0} aria-label="Scrollable process diagram"><MapSvg doc={doc} onAction={onAction} /></div>
    {enlarged && <dialog ref={dialog} className="v2-map-dialog" aria-label="Process map, enlarged" onClose={close} onCancel={close}>
      <div className="v2-map-head"><h3>Process map</h3><button type="button" onClick={close}>Close</button></div>
      <div className="v2-map-canvas" tabIndex={0} aria-label="Scrollable enlarged process diagram"><MapSvg doc={doc} onAction={goto} /></div></dialog>}
    <div className="v2-map-mobile" aria-label="Compact process map">
      {doc.actions.map(a => <section key={a.id}><button type="button" onClick={() => onAction(a.id)}>{displayTitle(a)}</button><small>{a.actor ?? `Service: ${a.service_agency}`}</small>
        {a.conditions.length > 0 && <p>{a.conditions.join(' AND ')}</p>}
        {doc.edges.filter(e => e.target_id === a.id).map(e => <p key={e.source_id}>Requires: <button type="button" onClick={() => onAction(e.source_id)}>{titleOf(doc, e.source_id)}</button></p>)}
        {doc.joins.filter(j => j.target === a.id).map((j, i) => <p key={i}>Requires {expressionText(j.requirement, doc)}</p>)}
      </section>)}
    </div>
    <div className="v2-map-groups">{doc.joins.length > 0 && <p>Dashed links show a requirement that combines several actions. They do not require every alternative route.</p>}
      {doc.branches.map(b => <section key={b.group_id}><strong>{b.selection === 'XOR' ? 'One applicable route' : b.selection === 'AND' ? 'Joint requirements' : 'One or more applicable options'}</strong>
        {b.options.map(o => <p key={o.option_id}>{o.condition_ids.map(id => doc.conditions.find(c => c.condition_id === id)?.text).join(' AND ')}: {doc.actions.filter(a => o.action_ids.includes(a.id)).map(a => displayTitle(a)).join(' · ')}</p>)}
      </section>)}
      {doc.joins.map((j, i) => <p key={`j${i}`}><strong>{titleOf(doc, j.target)}:</strong> requires {expressionText(j.requirement, doc)}.</p>)}
      {doc.parallel.map(p => <p key={p.group_id}><strong>Explicit parallel group:</strong> {p.action_ids.map(id => titleOf(doc, id)).join(' + ')}</p>)}
      {doc.parallel_areas.map((p, i) => <p key={`p${i}`}><strong>Explicit parallel areas:</strong> {p.map(e => expressionText(e, doc)).join(' + ')}</p>)}
    </div>
    <details><summary>Complete text equivalent</summary><ul>{relationshipLines(doc).map((line, i) => <li key={i}>{line}</li>)}</ul>
      {doc.stage_edges.map((e, i) => <p key={i}>Service dependency: {doc.stages.find(s => s.service_id === e.source_id)?.name} precedes {doc.stages.find(s => s.service_id === e.target_id)?.name}. This does not create extra action prerequisites.</p>)}
      <ul>{doc.actions.map(a => <li key={a.id}>{displayTitle(a)}: {a.actor ?? `service agency ${a.service_agency}; action owner not supplied`}. {a.conditions.join(' ')}</li>)}</ul>
    </details>
  </section>;
}
