/** Pure derivations from the backend response. Nothing here selects, alters or invents guidance content. */
import type {
  Availability, Configuration, Dimension, Doc, GuidanceResponse, Interaction, NavigationEntry, RelationCue, RenderedAction, Route, ScopedFact,
} from './types';

export const DIMENSIONS: Dimension[] = ['navigation', 'explanation', 'disclosure', 'relationships', 'recap', 'segmentation'];

export const DIMENSION_TEXT: Record<Dimension, { title: string; hint: string; values: Record<string, string> }> = {
  navigation: { title: 'Navigation', hint: 'See every step, or one at a time', values: { overview: 'Overview', guided: 'Guided' } },
  explanation: { title: 'Explanation', hint: 'Short instructions, or fuller reviewed explanation', values: { concise: 'Concise', detailed: 'Detailed' } },
  disclosure: { title: 'Extra information', hint: 'Keep supplementary information behind a small control', values: { off: 'Off', on: 'On' } },
  relationships: { title: 'Connections', hint: 'How steps relate to one another', values: { none: 'Text only', inline: 'Inline', map: 'Map' } },
  recap: { title: 'Earlier steps', hint: 'Short reminders of steps you viewed', values: { off: 'Off', on: 'On' } },
  segmentation: { title: 'Phases', hint: 'Group steps into reviewed phases', values: { off: 'Off', on: 'On' } },
};

export type Origin = { kind: 'standard' | 'preview' | 'adjusted' | 'selected'; label: string; note: string };

/** Origin comes only from the backend's selection record. Nothing is inferred from a profile. */
export function originOf(r: Pick<GuidanceResponse, 'selection' | 'parent_view_id'>): Origin {
  switch (r.selection.kind) {
    case 'shared_gaussian_lints': return { kind: 'selected', label: 'Selected for you', note: r.selection.label };
    case 'research_preview': return { kind: 'preview', label: 'Research preview', note: 'Not a learned selection' };
    case 'manual_adjustment': return { kind: 'adjusted', label: 'Adjusted by you', note: 'Your own change; not a selected presentation' };
    case 'constraint_standard': return { kind: 'standard', label: 'Standard guidance', note: 'Adjusted to your saved restrictions' };
    default: return { kind: 'standard', label: 'Standard guidance', note: 'Fixed baseline' };
  }
}

/** Paragraphs of source text; a paragraph that is only the source limitation is shown once, in the notice. */
export function paragraphs(text: string, sourceLimit?: string): string[] {
  const limit = sourceLimit?.trim() ?? '';
  // A fallback paragraph can be the whole limitation or only its opening sentence; both are the notice, not guidance.
  const isLimit = (p: string) => !!limit && (p === limit || (p.length >= 40 && limit.startsWith(p)));
  return text.split(/\n\s*\n/).map(p => p.trim()).filter(p => p && !isLimit(p));
}

/** Fallback headings are whole source sentences; show the first paragraph only. */
export function headingOf(a: RenderedAction, sourceLimit?: string): string {
  return paragraphs(a.heading, sourceLimit)[0] ?? a.heading;
}

export function formatAmount(f: { value?: number; currency?: string }): string {
  const value = typeof f.value === 'number' ? f.value.toLocaleString('en-US', { maximumFractionDigits: 2 }) : '';
  return `${f.currency ?? ''} ${value}`.trim();
}

export function entryOf(doc: Doc, id: string): NavigationEntry | undefined { return doc.navigation.entries.find(e => e.action_id === id); }
export function byId(doc: Doc, id: string): RenderedAction | undefined { return doc.actions.find(a => a.id === id); }

export function stageName(doc: Doc, fact: ScopedFact): string | null {
  return doc.stages.find(s => s.service_id === (fact.stage_id ?? fact.service_id))?.name ?? null;
}

/** Where a fact came from, in words. A stage fee is never presented as payable at a particular step. */
export function scopeNote(doc: Doc, fact: ScopedFact): string | null {
  if (fact.scope === 'stage') { if (doc.stages.length <= 1) return null; const n = stageName(doc, fact); return n ? `For: ${n}` : 'For one part of the service'; }
  if (fact.scope === 'service') return 'For the whole service';
  if (fact.scope === 'route') return 'On the matching route';
  return null;
}

/** Facts that no action carries are listed once for the procedure. */
export function procedureFacts(doc: Doc) {
  const attached = new Set(doc.actions.flatMap(a => a.facts.map(f => f.id)));
  const only = (list: ScopedFact[]) => list.filter(f => !attached.has(f.id));
  return { documents: only(doc.requirements.documents), fees: only(doc.requirements.fees) };
}

/** Dependency layer for drawing. After a route is chosen the backend leaves other routes' layers empty; place them from their verified edges. */
export function layerMap(doc: Doc, edges: { source_id: string; target_id: string }[]): Map<string, number> {
  const layers = new Map<string, number>();
  for (const a of doc.actions) { const l = entryOf(doc, a.id)?.layer; if (l != null) layers.set(a.id, l); }
  for (let pass = 0; pass < doc.actions.length; pass++) for (const a of doc.actions) {
    if (layers.has(a.id)) continue;
    const before = edges.filter(e => e.target_id === a.id).map(e => layers.get(e.source_id));
    if (before.length > 0 && before.every(x => x !== undefined)) layers.set(a.id, Math.max(...(before as number[])) + 1);
  }
  for (const a of doc.actions) if (!layers.has(a.id)) layers.set(a.id, 1);
  return layers;
}

export type Layer = { layer: number | null; peers: RenderedAction[]; routes: Route[] };

/**
 * Layers come from the backend's verified prerequisite layers. They orient browsing only; peers in one
 * layer have no stated order, and routes are choices placed at the layer of their first action.
 */
export function layersOf(doc: Doc, subset?: Set<string>): Layer[] {
  const inSubset = (id: string) => !subset || subset.has(id);
  const order = new Map(doc.navigation.browsing_action_ids.map((id, i) => [id, i]));
  const layerOf = (id: string) => entryOf(doc, id)?.layer ?? null;
  const map = new Map<number | null, Layer>();
  const layer = (n: number | null) => { if (!map.has(n)) map.set(n, { layer: n, peers: [], routes: [] }); return map.get(n)!; };
  for (const a of doc.actions) if (!a.branch && inSubset(a.id)) layer(layerOf(a.id)).peers.push(a);
  for (const r of doc.routes) {
    const ids = r.options.flatMap(o => o.action_ids).filter(inSubset);
    if (ids.length === 0) continue;
    const known = ids.map(layerOf).filter((n): n is number => n !== null);
    layer(known.length ? Math.min(...known) : null).routes.push(r);
  }
  for (const l of map.values()) l.peers.sort((a, b) => (order.get(a.id) ?? 99) - (order.get(b.id) ?? 99) || a.id.localeCompare(b.id));
  return [...map.values()].sort((a, b) => (a.layer ?? 99) - (b.layer ?? 99));
}

export type PhaseGroup = { id: string; label: string; basis: string; ordered: boolean; index: number; layers: Layer[] };

/** Phases exist only when Segmentation is ON. An empty phase_order means unordered groups: no sequence is implied. */
export function phaseGroups(doc: Doc): PhaseGroup[] | null {
  if (doc.configuration.segmentation !== 'on' || doc.phases.length === 0) return null;
  const ordered = doc.phase_order.length > 0;
  const phases = ordered ? doc.phase_order.map(id => doc.phases.find(p => p.id === id)).filter((p): p is NonNullable<typeof p> => !!p) : doc.phases;
  return phases.map((p, index) => ({ id: p.id, label: p.label.text, basis: p.basis, ordered, index, layers: layersOf(doc, new Set(p.action_ids)) }));
}

export function phaseOf(doc: Doc, actionId: string | null) {
  return actionId ? doc.phases.find(p => p.action_ids.includes(actionId)) ?? null : null;
}

export function routeSelection(interaction: Interaction, route: Route): string[] { return interaction.route_choices[route.branch_id] ?? []; }
export function routeOfAction(doc: Doc, actionId: string): { route: Route; optionId: string } | null {
  for (const route of doc.routes) { const o = route.options.find(x => x.action_ids.includes(actionId)); if (o) return { route, optionId: o.option_id }; }
  return null;
}

export function cueView(cue: RelationCue): { label: string; body: string } {
  const after = (prefix: string) => cue.text.startsWith(prefix) ? cue.text.slice(prefix.length) : cue.text;
  switch (cue.kind) {
    case 'before': return { label: 'Before this', body: after('Before this: ') };
    case 'join': return { label: 'Also required', body: cue.text.includes(': ') ? cue.text.slice(cue.text.indexOf(': ') + 2) : cue.text };
    case 'parallel': return { label: 'Can be done alongside', body: after('Verified parallel work: ') };
    case 'parallel_area': return { label: 'Can be done alongside', body: after('These verified work areas may proceed independently: ') };
    default: return { label: 'Related', body: cue.text };
  }
}

/** Values of one dimension that stay feasible when only that dimension changes (from the backend's own feasibility list). */
export function allowedValues(availability: Availability, config: Configuration, dim: Dimension): { value: string; feasible: boolean; reason: string | null }[] {
  const options = [...new Set(availability.candidates.map(c => c.configuration[dim] as string))];
  return options.map(value => {
    const hit = availability.candidates.find(c => (Object.keys(config) as Dimension[]).every(k => (k === dim ? c.configuration[k] === value : c.configuration[k] === config[k])));
    return { value, feasible: !!hit?.feasible, reason: hit && !hit.feasible ? hit.reasons[0] ?? null : null };
  });
}

/** Configurations feasible given partial choices; used by the research preview chooser. */
export function feasibleFor(availability: Availability, partial: Partial<Configuration>, dim: Dimension, value: string): boolean {
  return availability.candidates.some(c => c.feasible && c.configuration[dim] === value
    && (Object.keys(partial) as Dimension[]).every(k => k === dim || c.configuration[k] === partial[k]));
}

const REASONS: Record<string, string> = {
  'disclosure:no_reviewed_remainder_for_selected_depth': 'no reviewed explanation to collapse at this depth yet',
  'disclosure:no_reviewed_supplement': 'no reviewed supplementary information yet',
  'explanation:reviewed_detailed_missing': 'no reviewed detailed explanation yet',
  'recap:reviewed_reminders_missing': 'no reviewed reminder wording yet',
  'relationships:incomplete_map_or_accessibility': 'a map needs complete verified structure and is off if restricted',
  'segmentation:reviewed_meaningful_groups_missing': 'no reviewed phase grouping yet',
};
export function reasonText(reason: string): string { return REASONS[reason] ?? reason.replace(':', ': ').replaceAll('_', ' '); }

const LIMIT = { compact: 44, large: 90 } as const;
/** Display only: long source-sentence labels are shortened with an ellipsis. The full text stays in the tooltip, the accessible name and the text version. */
export function shortLabel(text: string, size: 'compact' | 'large'): string {
  const first = text.split(/\n\s*\n/)[0].trim(), max = LIMIT[size];
  if (first.length <= max) return first;
  const cut = first.slice(0, max - 1), at = cut.lastIndexOf(' ');
  return `${cut.slice(0, at > max * 0.6 ? at : cut.length).replace(/[\s,;:.]+$/, '')}…`;
}
