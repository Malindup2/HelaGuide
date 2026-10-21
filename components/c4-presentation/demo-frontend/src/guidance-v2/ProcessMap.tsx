import { useId, useState } from 'react';
import type { Document, Expression } from './types';
import { expressionText, relationshipLines } from './semantics';
import { actionMarks, displayTitle } from './presentation';
import { MapIcon, Sheet } from './card/parts';

type Size = { w: number; h: number; gx: number; gy: number; pad: number; font: number };
const SIZES: Record<'compact' | 'large', Size> = {
  compact: { w: 104, h: 44, gx: 10, gy: 26, pad: 8, font: 11 },
  large: { w: 210, h: 68, gx: 24, gy: 56, pad: 20, font: 14 },
};
const BADGE = { XOR: 'Choose one', AND: 'All of these', OR: 'Some may apply' } as const;

function refs(e: Expression, doc: Document): string[] {
  if (e.kind === 'action') return [e.ref!];
  if (e.kind === 'selected_option_of') return doc.branches.find(b => b.group_id === e.ref)?.options.flatMap(o => o.action_ids) ?? [];
  return e.children.flatMap(c => refs(c, doc));
}
const titleOf = (doc: Document, id: string) => { const a = doc.actions.find(x => x.id === id); return a ? displayTitle(a) : id; };

function layout(doc: Document, z: Size) {
  // Rows follow supplied prerequisite depth only. Browsing order is never drawn as an edge.
  const depth = new Map(doc.actions.map(a => [a.id, 0]));
  const edges = [...doc.edges, ...doc.joins.flatMap(j => refs(j.requirement, doc).map(id => ({ source_id: id, target_id: j.target })))];
  for (let pass = 0; pass < doc.actions.length; pass++) for (const e of edges) depth.set(e.target_id, Math.max(depth.get(e.target_id)!, depth.get(e.source_id)! + 1));
  const levels = Math.max(...depth.values()) + 1;
  const rows = Array.from({ length: levels }, (_, l) => doc.actions.filter(a => depth.get(a.id) === l));
  const widest = Math.max(...rows.map(r => r.length));
  const width = widest * z.w + (widest - 1) * z.gx + z.pad * 2;
  const pos = new Map<string, { x: number; y: number }>();
  rows.forEach((row, l) => row.forEach((a, i) => pos.set(a.id, { x: (width - (row.length * z.w + (row.length - 1) * z.gx)) / 2 + i * (z.w + z.gx), y: z.pad + l * (z.h + z.gy) })));
  return { pos, width, height: levels * (z.h + z.gy) - z.gy + z.pad * 2 };
}

export function ProcessGraph({ doc, size, current, onAction }: { doc: Document; size: 'compact' | 'large'; current?: string; onAction: (id: string) => void }) {
  const z = SIZES[size], marker = useId().replaceAll(':', ''), { pos, width, height } = layout(doc, z), marks = actionMarks(doc);
  const frames = doc.branches.filter(b => b.options.length > 1).flatMap(b => {
    const members = new Set(b.options.flatMap(o => o.action_ids)), pts = [...members].map(id => pos.get(id)!).filter(Boolean);
    if (pts.length < 2) return [];
    const x1 = Math.min(...pts.map(p => p.x)) - 5, y1 = Math.min(...pts.map(p => p.y)) - 5, x2 = Math.max(...pts.map(p => p.x)) + z.w + 5, y2 = Math.max(...pts.map(p => p.y)) + z.h + 5;
    const clean = doc.actions.every(a => members.has(a.id) || !pos.has(a.id) || pos.get(a.id)!.x + z.w < x1 || pos.get(a.id)!.x > x2 || pos.get(a.id)!.y + z.h < y1 || pos.get(a.id)!.y > y2);
    return clean ? [{ b, x1, y1, x2, y2 }] : [];
  });
  return <svg className={`gc-graph gc-graph-${size}`} viewBox={`0 0 ${width} ${height}`} role="group" aria-label="Procedure map. A complete text equivalent follows.">
    <defs><marker id={marker} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" className="gc-arrow" /></marker></defs>
    {frames.map(f => <g key={f.b.group_id}><rect className="gc-frame" x={f.x1} y={f.y1} width={f.x2 - f.x1} height={f.y2 - f.y1} rx="8" />
      {size === 'large' && <text className="gc-frame-label" x={f.x1 + 8} y={f.y1 - 6}>{BADGE[f.b.selection]}</text>}</g>)}
    {doc.edges.map((e, i) => { const s = pos.get(e.source_id)!, t = pos.get(e.target_id)!;
      return <path key={i} className="gc-edge" d={`M ${s.x + z.w / 2} ${s.y + z.h} C ${s.x + z.w / 2} ${s.y + z.h + z.gy / 2},${t.x + z.w / 2} ${t.y - z.gy / 2},${t.x + z.w / 2} ${t.y}`} markerEnd={`url(#${marker})`} />; })}
    {doc.joins.flatMap((j, ji) => refs(j.requirement, doc).map((source, si) => { const s = pos.get(source)!, t = pos.get(j.target)!;
      return <path key={`j${ji}-${si}`} className="gc-join" d={`M ${s.x + z.w / 2} ${s.y + z.h} L ${t.x + z.w / 2} ${t.y}`} markerEnd={`url(#${marker})`} />; }))}
    {doc.actions.map(a => { const p = pos.get(a.id)!, mark = marks.get(a.id)!;
      return <g key={a.id} transform={`translate(${p.x},${p.y})`}><rect className={`gc-node${a.id === current ? ' gc-node-current' : ''}`} width={z.w} height={z.h} rx="8" />
        <foreignObject width={z.w} height={z.h}><button type="button" className="gc-node-btn" style={{ fontSize: z.font }} title={displayTitle(a)} aria-current={a.id === current ? 'step' : undefined} onClick={() => onAction(a.id)}>
          <span className={`gc-mark gc-mark-${mark.kind}`} aria-hidden="true">{mark.label}</span><span className="gc-node-t">{displayTitle(a)}</span></button></foreignObject></g>; })}
  </svg>;
}

export function TextEquivalent({ doc }: { doc: Document }) {
  return <details className="gc-text-eq"><summary>Complete text equivalent</summary>
    <ul>{relationshipLines(doc).map((line, i) => <li key={i}>{line}</li>)}</ul>
    {doc.stage_edges.map((e, i) => <p key={i}>Service dependency: {doc.stages.find(s => s.service_id === e.source_id)?.name} precedes {doc.stages.find(s => s.service_id === e.target_id)?.name}. This does not create extra action prerequisites.</p>)}
    {doc.joins.map((j, i) => <p key={`j${i}`}>{titleOf(doc, j.target)} requires {expressionText(j.requirement, doc)}.</p>)}
    <ul>{doc.actions.map(a => <li key={a.id}>{displayTitle(a)}: {a.actor ?? `service agency ${a.service_agency}; action owner not supplied`}. {a.conditions.join(' ')}</li>)}</ul>
  </details>;
}

/** Compact preview with an expandable larger view; both are the same supplied structure. */
export default function ProcessMap({ doc, onAction, current, event }: {
  doc: Document; onAction: (id: string) => void; current?: string; event?: (type: 'map_expand' | 'map_collapse') => void;
}) {
  const [large, setLarge] = useState(false);
  const open = () => { setLarge(true); event?.('map_expand'); };
  const close = () => { setLarge(false); event?.('map_collapse'); };
  return <section className="gc-map" aria-label="Integrated supplied process" data-support="relationships">
    <div className="gc-map-head"><p className="gc-fine">Arrows show what comes first, not what has been done.</p>
      <button type="button" className="gc-chip" onClick={open}><MapIcon />Expand map</button></div>
    <div className="gc-map-canvas"><ProcessGraph doc={doc} size="compact" current={current} onAction={onAction} /></div>
    <TextEquivalent doc={doc} />
    {large && <Sheet title="Process map" onClose={close} wide>
      <div className="gc-map-canvas gc-map-canvas-large"><ProcessGraph doc={doc} size="large" current={current} onAction={id => { close(); onAction(id); }} /></div>
      {doc.stage_edges.length > 0 && <aside className="gc-note"><b>Service-level dependencies</b>{doc.stage_edges.map((e, i) => <p key={i}>{doc.stages.find(s => s.service_id === e.source_id)?.name} → {doc.stages.find(s => s.service_id === e.target_id)?.name}</p>)}<small>These do not add action-level prerequisites.</small></aside>}
      <TextEquivalent doc={doc} /></Sheet>}
  </section>;
}
