/** Pure presentation helpers. Nothing here chooses a configuration or alters backend facts. */
import type { Action, Branch, Configuration, Document, Journey } from './types';

export const DIMENSIONS = ['navigation', 'explanation', 'disclosure', 'relationships', 'recap', 'summary'] as const;
export type Dimension = (typeof DIMENSIONS)[number];
export type Origin = 'standard' | 'personalised' | 'adjusted';

type StateText = { label: string; benefit: string };
export const SUPPORT_TEXT: Record<Dimension, { title: string; question: string; states: Record<string, StateText> }> = {
  navigation: { title: 'Navigation', question: 'How should the actions be laid out?', states: {
    overview: { label: 'Overview', benefit: 'All actions on one page' },
    guided: { label: 'Guided', benefit: 'One action at a time, with your position' } } },
  explanation: { title: 'Explanation', question: 'How much explanation do you want?', states: {
    concise: { label: 'Concise', benefit: 'Short instructions' },
    expanded: { label: 'Fuller', benefit: 'More explanation for each action' } } },
  disclosure: { title: 'Optional detail', question: 'Should optional detail start open?', states: {
    collapsed: { label: 'Tucked away', benefit: 'Optional detail stays out of the way' },
    expanded: { label: 'Extra info open', benefit: 'Optional detail is open by default' } } },
  relationships: { title: 'How actions connect', question: 'How should dependencies be shown?', states: {
    none: { label: 'Text only', benefit: 'Dependencies described in the text' },
    inline: { label: 'Inline', benefit: 'What comes first is marked beside each action' },
    map: { label: 'Process map', benefit: 'The whole route at a glance' } } },
  recap: { title: 'Earlier guidance', question: 'Show a reminder of what you viewed?', states: {
    off: { label: 'Off', benefit: 'No reminder' },
    on: { label: 'Reminder', benefit: 'Short reminders of guidance you viewed earlier' } } },
  summary: { title: 'Preparation', question: 'Gather documents and charges in one place?', states: {
    off: { label: 'With each action', benefit: 'Documents and charges are listed under each action' },
    on: { label: 'Summary', benefit: 'Documents and charges gathered in one place' } } },
};

/** States that add a visible aid compared with the plainest presentation (a display notion, not policy). */
const AID_STATES: Record<Dimension, string[]> = {
  navigation: ['guided'], explanation: ['expanded'], disclosure: ['expanded'],
  relationships: ['inline', 'map'], recap: ['on'], summary: ['on'],
};

export function originOf(journey: Pick<Journey, 'routing' | 'views' | 'current_view'>): Origin {
  if (journey.views[journey.current_view]?.parent) return 'adjusted';
  return journey.routing === 'adaptive' ? 'personalised' : 'standard';
}

export const ORIGIN_TEXT: Record<Origin, { label: string; detail: string }> = {
  standard: { label: 'Standard guidance', detail: 'The same plain layout for everyone.' },
  personalised: { label: 'Selected for you', detail: 'The layout was chosen using your saved profile.' },
  adjusted: { label: 'Adjusted by you', detail: 'You changed the support for this visit.' },
};

export function activeSupports(config: Configuration) {
  return DIMENSIONS.filter(d => AID_STATES[d].includes(config[d])).map(d => ({ dimension: d, ...SUPPORT_TEXT[d].states[config[d]] }));
}

export type DimensionDiff = { dimension: Dimension; standard: string; selected: string; same: boolean };
export function diffConfigurations(standard: Configuration, selected: Configuration): DimensionDiff[] {
  return DIMENSIONS.map(d => ({ dimension: d, standard: standard[d], selected: selected[d], same: standard[d] === selected[d] }));
}

/** States the procedure itself cannot offer, with the backend's stated reason. */
export function unavailableStates(doc: Document) {
  return DIMENSIONS.flatMap(d => {
    const cap = doc.capabilities[d];
    return Object.keys(SUPPORT_TEXT[d].states).filter(s => !cap.states.includes(s)).map(s => ({ dimension: d, state: s, reason: cap.reason }));
  });
}

/** Counts computed only from the real document and configuration. */
export function presentationCounts(doc: Document, config: Configuration) {
  const optional = doc.actions.reduce((n, a) => n + a.optional.length, 0);
  return {
    actionsVisible: config.navigation === 'guided' ? Math.min(1, doc.actions.length) : doc.actions.length,
    optionalOpen: config.disclosure === 'expanded' ? optional : 0,
    optionalTotal: optional,
    relationshipCues: config.relationships === 'none' ? 0 : doc.edges.length + doc.joins.length,
  };
}

export function agencies(doc: Document): string[] {
  return [...new Set(doc.actions.map(a => a.service_agency))];
}

/** Actions that remain browsable once any focused exclusive route is applied. */
export function browsingList(journey: Pick<Journey, 'document' | 'focused_routes'>): Action[] {
  const { document: doc, focused_routes } = journey;
  return doc.actions.filter(a => !a.branch || doc.branches.find(b => b.group_id === a.branch)?.selection !== 'XOR'
    || !focused_routes?.[a.branch] || focused_routes[a.branch] === a.option);
}

export function factLabel(f: Document['facts'][number], doc: Document): string {
  if (f.kind === 'document') return f.name ?? 'Document';
  const scope = doc.stages.find(s => s.fee_fact_id === f.fact_id)?.name;
  return `${scope ? `${scope}: ` : 'Recorded charge: '}${f.currency} ${f.value}`;
}

/** Actions a fact is attached to; a stage fee only counts for actions of its own stage. */
export function factActions(doc: Document, f: Document['facts'][number]): Action[] {
  return doc.actions.filter(a => a.fact_ids.includes(f.fact_id)
    && (f.kind !== 'fee' || doc.stages.some(s => s.fee_fact_id === f.fact_id && s.service_id === a.service_id)));
}

export function actionFacts(doc: Document, action: Action) {
  return action.fact_ids.map(id => doc.facts.find(f => f.fact_id === id)).filter((f): f is Document['facts'][number] => f !== undefined);
}

type Fact = Document['facts'][number];

/**
 * The backend's source-excerpt fallback cuts a title at 115 characters, which can end mid-phrase.
 * When that happened, show the complete first source sentence instead. Nothing is added or reworded.
 */
export function displayTitle(a: Action): string {
  const first = a.concise.split('. ')[0].replace(/\.$/, '');
  return a.wording_status?.title === 'source_excerpt' && a.title.length < first.length && first.startsWith(a.title) ? first : a.title;
}

export type Mark = { kind: 'common' | 'route' | 'joint' | 'optional'; label: string; note: string };

/**
 * Browsing order is not an execution order, so actions are never numbered as a sequence.
 * Actions inside a branch group are marked by their option (A, B, ...) with the group's meaning.
 */
export function actionMarks(doc: Document): Map<string, Mark> {
  const marks = new Map<string, Mark>();
  for (const b of doc.branches) b.options.forEach((o, i) => {
    const letter = String.fromCharCode(65 + i);
    for (const id of o.action_ids) if (!marks.has(id)) marks.set(id, b.selection === 'XOR'
      ? { kind: 'route', label: letter, note: `Route ${letter} · choose one` }
      : b.selection === 'AND' ? { kind: 'joint', label: letter, note: `Part ${letter} · needed together` }
        : { kind: 'optional', label: letter, note: `Option ${letter} · may apply` });
  });
  for (const a of doc.actions) if (!marks.has(a.id)) marks.set(a.id, { kind: 'common', label: '', note: '' });
  return marks;
}

export function isConditional(doc: Document, a: Action): boolean {
  return a.conditions.length > 0 || (a.branch !== null && doc.branches.find(b => b.group_id === a.branch)?.selection !== 'AND');
}

export type FactEntry = { fact: Fact; always: Action[]; routes: Action[] };
export type FactGroups = { always: FactEntry[]; conditional: { key: string; entries: FactEntry[] }[]; service: Fact[] };

/** Splits requirements by what the supplied actions say; alternatives are never merged into one line. */
export function groupFacts(doc: Document): FactGroups {
  const groups: FactGroups = { always: [], conditional: [], service: [] };
  for (const fact of doc.facts) {
    const acts = factActions(doc, fact);
    if (acts.length === 0) { groups.service.push(fact); continue; }
    const plain = acts.filter(a => !isConditional(doc, a)), routes = acts.filter(a => isConditional(doc, a));
    if (plain.length > 0) { groups.always.push({ fact, always: plain, routes }); continue; }
    for (const a of routes) {
      const key = a.conditions.join(' AND ') || 'This route applies (condition not supplied)';
      const group = groups.conditional.find(g => g.key === key) ?? (groups.conditional.push({ key, entries: [] }), groups.conditional[groups.conditional.length - 1]);
      group.entries.push({ fact, always: [], routes: [a] });
    }
  }
  return groups;
}

export function feedbackNote(origin: Origin): string {
  if (origin === 'standard') return 'Optional. Your answer is saved to evaluate this guidance. It does not change the guidance shown to you or anyone else.';
  if (origin === 'adjusted') return 'Optional. Your answer is saved with your adjusted view. It does not change which layout is selected for you.';
  return 'Optional. Your answer may be used to improve how support is chosen for this kind of procedure.';
}

export function sourceFor(doc: Document, factId: string): { url: string; retrieved: string | null } | null {
  const p = doc.provenance?.find(x => x.fact_id === factId);
  return p ? { url: p.source_url, retrieved: p.retrieved_at } : null;
}

export function hasRelations(doc: Document): boolean {
  return doc.edges.length + doc.joins.length + doc.branches.length + doc.parallel.length + doc.parallel_areas.length > 0;
}

export function incomplete(doc: Document): boolean {
  return Object.values(doc.completeness).some(v => v !== 'complete');
}

export function statusChip(doc: Document): string {
  return doc.synthetic ? 'Practice example, not an official service' : 'Information snapshot. Check the official source before acting';
}

export function qualifier(doc: Document): string {
  return doc.synthetic ? 'Practice example · not an official service'
    : 'Bounded snapshot · not a current or verified service · check the official source';
}

export type RouteOption = { id: string; letter: string; conditions: string[]; actions: Action[] };
export type Block = { kind: 'action'; action: Action } | { kind: 'group'; group: Branch; options: RouteOption[] };

/**
 * Browsing outline. Actions in one branch group are gathered into a single route block so alternatives
 * are never shown as consecutive steps. The position of a group is where its first action is browsed.
 */
export function outline(doc: Document): Block[] {
  const blocks: Block[] = [], groups = new Map<string, Extract<Block, { kind: 'group' }>>();
  for (const action of doc.actions) {
    const group = action.branch ? doc.branches.find(b => b.group_id === action.branch) : undefined;
    if (!group) { blocks.push({ kind: 'action', action }); continue; }
    let block = groups.get(group.group_id);
    if (!block) {
      block = { kind: 'group', group, options: group.options.map((o, i) => ({
        id: o.option_id, letter: String.fromCharCode(65 + i), actions: [],
        conditions: o.condition_ids.map(id => doc.conditions.find(c => c.condition_id === id)?.text).filter((t): t is string => Boolean(t)) })) };
      groups.set(group.group_id, block); blocks.push(block);
    }
    block.options.find(o => o.id === action.option)?.actions.push(action);
  }
  return blocks;
}

/** Maps the backend configuration to layout decisions. It never selects or alters the configuration. */
export function resolveLayout(c: Configuration) {
  return {
    list: c.navigation === 'guided' ? 'focused' : 'accordion',
    strip: c.relationships === 'map' ? 'graph' : c.navigation === 'guided' ? 'dots' : 'none',
    needs: c.summary === 'on' && c.navigation === 'overview' ? 'reference' : 'inline',
    cues: c.relationships === 'none' ? 'text' : 'links',
    explanation: c.explanation === 'expanded' ? 'full' : 'plain',
    optionalOpen: c.disclosure === 'expanded',
    recap: c.recap === 'on',
    prepare: c.summary === 'on',
    map: c.relationships === 'map',
  } as const;
}

export function prefersReducedMotion(): boolean {
  try { return typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches; } catch { return false; }
}
