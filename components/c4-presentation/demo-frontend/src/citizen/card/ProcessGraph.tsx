import { useId } from 'react';
import type { Doc, Expression, ProcessMap } from '../types';
import { entryOf, layerMap } from '../model';

type Size = { w: number; h: number; gx: number; gy: number; pad: number; font: number };
const SIZES: Record<'compact' | 'large', Size> = {
  compact: { w: 104, h: 46, gx: 10, gy: 24, pad: 8, font: 11 },
  large: { w: 220, h: 70, gx: 28, gy: 58, pad: 24, font: 14 },
};
const BADGE = { XOR: 'Choose one', AND: 'All of these', OR: 'Some may apply' } as const;

function leaves(e: Expression, map: ProcessMap): string[] {
  if (e.kind === 'action') return [e.ref!];
  if (e.kind === 'selected_option_of') return map.branches.find(b => b.group_id === e.ref)?.options.flatMap(o => o.action_ids) ?? [];
  return e.children.flatMap(c => leaves(c, map));
}

/** Layout rows are the backend's verified dependency layers. Browsing order is never drawn as an edge. */
function layout(doc: Doc, map: ProcessMap, z: Size) {
  const ids = doc.actions.map(a => a.id), layers = layerMap(doc, map.edges);
  const layerOf = (id: string) => layers.get(id) ?? 0;
  const levels = [...new Set(ids.map(layerOf))].sort((a, b) => a - b);
  const rows = levels.map(l => ids.filter(id => layerOf(id) === l).sort());
  const widest = Math.max(...rows.map(r => r.length));
  const width = widest * z.w + (widest - 1) * z.gx + z.pad * 2;
  const pos = new Map<string, { x: number; y: number }>();
  rows.forEach((row, r) => row.forEach((id, i) => pos.set(id, { x: (width - (row.length * z.w + (row.length - 1) * z.gx)) / 2 + i * (z.w + z.gx), y: z.pad + r * (z.h + z.gy) })));
  return { pos, width, height: rows.length * (z.h + z.gy) - z.gy + z.pad * 2 };
}

function markerOf(doc: Doc, id: string): string {
  const entry = entryOf(doc, id);
  if (!doc.navigation.numbering_enabled || entry?.layer == null) return '';
  const route = doc.routes.find(r => r.options.some(o => o.action_ids.includes(id)));
  const letter = route ? String.fromCharCode(65 + route.options.findIndex(o => o.action_ids.includes(id))) : '';
  return `${entry.layer}${letter}`;
}

export default function ProcessGraph({ doc, map, size, activeId, onSelect }: { doc: Doc; map: ProcessMap; size: 'compact' | 'large'; activeId?: string | null; onSelect: (id: string) => void }) {
  const z = SIZES[size], marker = useId().replaceAll(':', ''), { pos, width, height } = layout(doc, map, z);
  const label = (id: string) => map.labels[id] ?? doc.actions.find(a => a.id === id)?.heading ?? id;
  const frames = map.branches.filter(b => b.options.length > 1).flatMap(b => {
    const members = new Set(b.options.flatMap(o => o.action_ids)), pts = [...members].map(id => pos.get(id)!).filter(Boolean);
    if (pts.length < 2) return [];
    const x1 = Math.min(...pts.map(p => p.x)) - 5, y1 = Math.min(...pts.map(p => p.y)) - 5, x2 = Math.max(...pts.map(p => p.x)) + z.w + 5, y2 = Math.max(...pts.map(p => p.y)) + z.h + 5;
    const clean = [...pos].every(([id, p]) => members.has(id) || p.x + z.w < x1 || p.x > x2 || p.y + z.h < y1 || p.y > y2);
    return clean ? [{ b, x1, y1, x2, y2 }] : [];
  });
  return <svg className={`cz-graph cz-graph-${size}`} style={{ maxWidth: Math.round(width * (size === 'compact' ? 1 : 1.35)) }} viewBox={`0 0 ${width} ${height}`} role="group" aria-label="Procedure map. A text version follows.">
    <defs><marker id={marker} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" className="cz-arrow" /></marker></defs>
    {frames.map(f => <g key={f.b.group_id}><rect className="cz-frame" x={f.x1} y={f.y1} width={f.x2 - f.x1} height={f.y2 - f.y1} rx="8" />
      {size === 'large' && <text className="cz-frame-label" x={f.x1 + 8} y={f.y1 - 6}>{BADGE[f.b.selection as keyof typeof BADGE] ?? 'Choice'}</text>}</g>)}
    {map.edges.map((e, i) => { const s = pos.get(e.source_id), t = pos.get(e.target_id); if (!s || !t) return null;
      return <path key={i} className="cz-edge" d={`M ${s.x + z.w / 2} ${s.y + z.h} C ${s.x + z.w / 2} ${s.y + z.h + z.gy / 2},${t.x + z.w / 2} ${t.y - z.gy / 2},${t.x + z.w / 2} ${t.y}`} markerEnd={`url(#${marker})`} />; })}
    {map.joins.flatMap((j, ji) => leaves(j.requirement, map).map((src, si) => { const s = pos.get(src), t = pos.get(j.target); if (!s || !t) return null;
      const word = j.requirement.kind === 'all_of' ? 'all of' : j.requirement.kind === 'any_of' ? 'one of' : null;
      return <g key={`j${ji}-${si}`}><path className="cz-join" d={`M ${s.x + z.w / 2} ${s.y + z.h} L ${t.x + z.w / 2} ${t.y}`} markerEnd={`url(#${marker})`} />
        {size === 'large' && word && si === 0 && <text className="cz-join-label" textAnchor="end" x={t.x - 8} y={t.y + z.h / 2}>needs {word}</text>}</g>; }))}
    {doc.actions.map(a => { const p = pos.get(a.id); if (!p) return null; const m = markerOf(doc, a.id), active = a.id === activeId;
      return <g key={a.id} transform={`translate(${p.x},${p.y})`}><rect className={`cz-node${active ? ' cz-node-active' : ''}`} width={z.w} height={z.h} rx="8" />
        <foreignObject width={z.w} height={z.h}><button type="button" className="cz-node-btn" style={{ fontSize: z.font }} title={label(a.id)} aria-current={active ? 'step' : undefined} onClick={() => onSelect(a.id)}>
          {m && <span className="cz-nodemark" aria-hidden="true">{m}</span>}<span className="cz-node-t">{label(a.id)}</span></button></foreignObject></g>; })}
  </svg>;
}
