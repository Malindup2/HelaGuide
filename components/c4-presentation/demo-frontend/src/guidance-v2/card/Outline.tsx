import type { Action, Document } from '../types';
import { displayTitle, outline } from '../presentation';
import type { Block, Mark, RouteOption } from '../presentation';
import ActionBody, { Cues, NeedsInline, NeedsLine } from './ActionBody';
import type { BodyProps } from './ActionBody';
import { ChevronIcon, MarkDot } from './parts';

export type OutlineState = {
  openIds: string[]; toggle: (id: string) => void;
  routeSel: Record<string, string>; selectRoute: (groupId: string, option: RouteOption, notify: boolean) => void;
  marks: Map<string, Mark>;
};
type Shared = Omit<BodyProps, 'action' | 'shownConditions'> & OutlineState;

const GROUP_TEXT = {
  XOR: { title: 'Which applies to you?', hint: 'Choose one route. Showing a route does not check whether it applies to you.' },
  AND: { title: 'All of these are needed', hint: 'These supplied options are joint requirements.' },
  OR: { title: 'More than one may apply', hint: 'More than one option may apply. Check each supplied condition; all options remain available.' },
} as const;

function Row({ action, showMark, shownConditions, s }: { action: Action; showMark: boolean; shownConditions?: string[]; s: Shared }) {
  const open = s.openIds.includes(action.id), mark = s.marks.get(action.id)!;
  return <div className={showMark ? "gc-row" : "gc-row gc-row-nomark"} data-open={open}>
    <h3 className="gc-rowh"><button type="button" id={`gc-h-${action.id}`} aria-expanded={open} aria-controls={`gc-body-${action.id}`} onClick={() => s.toggle(action.id)}>
      {showMark && <MarkDot mark={mark} />}
      <span className="gc-rowt">{mark.note && <span className="sr-only">{mark.note}: </span>}{displayTitle(action)}</span>
      <ChevronIcon /></button></h3>
    <Cues action={action} doc={s.doc} layout={s.layout} shownConditions={shownConditions} jump={s.jump} />
    {!open && (s.layout.needs === 'reference' ? <NeedsLine doc={s.doc} action={action} reference /> : <NeedsInline doc={s.doc} action={action} />)}
    {open && <ActionBody {...s} action={action} shownConditions={shownConditions} />}
  </div>;
}

function Group({ block, s }: { block: Extract<Block, { kind: 'group' }>; s: Shared }) {
  const g = block.group, text = GROUP_TEXT[g.selection], selected = s.routeSel[g.group_id];
  return <section className="gc-route" aria-label={text.title}>
    <h3 className="gc-route-title">{text.title}</h3><p className="gc-fine">{text.hint}</p>
    {block.options.map(o => {
      const collapsed = g.selection === 'XOR' && !!selected && selected !== o.id, mark = o.actions[0] ? s.marks.get(o.actions[0].id) : undefined;
      return <div className="gc-opt" key={o.id} data-selected={selected === o.id}>
        <div className="gc-opt-head">
          {mark && <MarkDot mark={{ ...mark, label: o.letter }} />}
          <div><p className="gc-opt-cond">{o.conditions.join(' AND ') || 'No additional condition supplied'}</p>{mark?.note && <p className="gc-fine">{mark.note}</p>}</div>
          {g.selection === 'XOR' && <button type="button" className="gc-chip" aria-pressed={selected === o.id} onClick={() => s.selectRoute(g.group_id, o, true)}>{selected === o.id ? 'Showing' : collapsed ? 'Show this route' : 'Show steps'}</button>}
        </div>
        {!collapsed && <ul className="gc-rows">{o.actions.map(a => <li key={a.id}><Row action={a} showMark={false} shownConditions={o.conditions} s={s} /></li>)}</ul>}
      </div>;
    })}
  </section>;
}

/** Overview layout: one scannable accordion. Alternative routes are a choice, never consecutive steps. */
export function Overview({ doc, s }: { doc: Document; s: Shared }) {
  return <ol className="gc-list">{outline(doc).map((b, i) => <li key={i}>{b.kind === 'action'
    ? <Row action={b.action} showMark s={s} /> : <Group block={b} s={s} />}</li>)}</ol>;
}

/** Compact jump list used by the guided layout; it keeps every action and route condition reachable. */
export function JumpList({ doc, marks, current, seen, onJump }: { doc: Document; marks: Map<string, Mark>; current: string; seen: string[]; onJump: (id: string) => void }) {
  const item = (a: Action) => <li key={a.id}><button type="button" aria-current={a.id === current ? 'step' : undefined} onClick={() => onJump(a.id)}>
    <MarkDot mark={marks.get(a.id)!} /><span>{displayTitle(a)}</span>{seen.includes(a.id) && <small>viewed</small>}</button></li>;
  return <ol className="gc-jump-list">{outline(doc).map((b, i) => <li key={i}>{b.kind === 'action' ? <ul>{item(b.action)}</ul>
    : <div className="gc-jump-group"><p className="gc-fine"><b>{GROUP_TEXT[b.group.selection].title}</b></p>
      {b.options.map(o => <div key={o.id}><p className="gc-jump-cond">{o.letter}. {o.conditions.join(' AND ') || 'No additional condition supplied'}</p><ul>{o.actions.map(item)}</ul></div>)}</div>}</li>)}</ol>;
}
