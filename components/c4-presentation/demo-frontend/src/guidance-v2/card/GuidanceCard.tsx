import { useEffect, useRef, useState } from 'react';
import type { Configuration, EventInput, Journey, Receipt } from '../types';
import { expressionText, previousActions } from '../semantics';
import { ORIGIN_TEXT, actionMarks, activeSupports, agencies, browsingList, displayTitle, factLabel, incomplete, originOf, prefersReducedMotion, qualifier, resolveLayout } from '../presentation';
import type { Dimension, RouteOption } from '../presentation';
import ProcessMap from '../ProcessMap';
import ActionBody, { Cues } from './ActionBody';
import FeedbackLine from './FeedbackLine';
import { JumpList, Overview } from './Outline';
import { ListIcon, MarkDot, SlidersIcon, InfoIcon, Sheet } from './parts';
import { PreparationSummary, SourcesContent, SupportContent } from './Sheets';

type Props = {
  journey: Journey; event: (e: EventInput) => void; adjust: (c: Configuration) => void; rate: (r: string) => Promise<Receipt>;
  readOnly?: boolean; research?: boolean; highlight?: Dimension | null;
};
type SheetName = 'support' | 'prepare' | 'sources' | null;
const noop = () => undefined;

export default function GuidanceCard({ journey, event, adjust, rate, readOnly = false, research = false, highlight = null }: Props) {
  const view = journey.views[journey.current_view], config = view.configuration, doc = journey.document, layout = resolveLayout(config);
  const [focus, setFocus] = useState(journey.focus ?? doc.actions[0]?.id ?? '');
  const current = doc.actions.find(a => a.id === focus) ?? doc.actions[0];
  const [openIds, setOpenIds] = useState<string[]>(() => [current.id]);
  const [routeSel, setRouteSel] = useState<Record<string, string>>({}), [sheet, setSheet] = useState<SheetName>(null);
  // Read-only views keep a local viewed list, so recap and position still work without recording anything.
  const [localSeen, setLocalSeen] = useState<string[]>([]);
  const focusTarget = useRef<string | null>(null);

  const focused = { ...journey.focused_routes, ...routeSel };
  const shown = { ...journey, focused_routes: focused, seen: readOnly ? [...new Set([...journey.seen, ...localSeen, current.id])] : journey.seen };
  const previous = previousActions(shown, current.id), browsing = browsingList({ document: doc, focused_routes: focused }), marks = actionMarks(doc);
  const position = browsing.findIndex(a => a.id === current.id), origin = originOf(journey), guided = layout.list === 'focused';
  const emit = readOnly ? noop : event;

  useEffect(() => {
    const id = focusTarget.current;
    if (!id) return;
    focusTarget.current = null;
    const target = document.getElementById(`gc-fh-${id}`) ?? document.getElementById(`gc-h-${id}`);
    if (!guided) target?.scrollIntoView({ behavior: prefersReducedMotion() ? 'auto' : 'smooth', block: 'nearest' });
    target?.focus({ preventScroll: true });
  }, [focus, guided, openIds]);

  const visit = (id: string) => { focusTarget.current = id; setFocus(id); if (readOnly) setLocalSeen(s => [...s, current.id, id]); else event({ type: 'navigate', action_id: id }); };
  const jump = (id: string) => { setOpenIds(o => o.includes(id) ? o : [...o, id]); visit(id); };
  const toggle = (id: string) => {
    if (openIds.includes(id)) { setOpenIds(o => o.filter(x => x !== id)); return; }
    jump(id);
  };
  const selectRoute = (groupId: string, option: RouteOption, notify: boolean) => {
    setRouteSel(r => ({ ...r, [groupId]: option.id }));
    if (notify && !readOnly) event({ type: 'route_focus', value: option.id });
    if (option.actions[0]) jump(option.actions[0].id);
  };
  const allowed = (key: keyof Configuration, value: string) => doc.capabilities[key].states.includes(value)
    && (!journey.available_configurations || journey.available_configurations.some(c => Object.entries({ ...config, [key]: value }).every(([k, v]) => c[k as keyof Configuration] === v)));
  const change = (key: keyof Configuration, value: string) => adjust({ ...config, [key]: value } as Configuration);

  const supports = activeSupports(config), names = agencies(doc);
  const orphanFacts = doc.facts.filter(f => !doc.actions.some(a => a.fact_ids.includes(f.fact_id)));
  const common = { doc, config, layout, viewId: view.id, readOnly, event: emit, jump };
  const currentGroup = current.branch ? doc.branches.find(b => b.group_id === current.branch) : undefined;
  const currentOption = currentGroup?.options.find(o => o.option_id === current.option);
  const optionConditions = currentOption ? currentOption.condition_ids.map(id => doc.conditions.find(c => c.condition_id === id)?.text).filter((t): t is string => Boolean(t)) : [];
  const mark = marks.get(current.id)!;
  const otherOptions = currentGroup?.selection === 'XOR' ? currentGroup.options.filter(o => o.option_id !== current.option) : [];
  const recap = layout.recap && previous.length > 0 && <aside className="gc-recap" data-support="recap"><details onToggle={e => { if (e.currentTarget.open) emit({ type: 'recap_open', action_id: current.id }); }}>
    <summary>Earlier in this journey ({previous.length})<span className="gc-teaser">{previous[previous.length - 1].recap}</span></summary>
    <p className="gc-fine">Viewed guidance; completion has not been confirmed.</p>
    <ul>{previous.map(a => <li key={a.id}><span>{a.recap}</span> <button type="button" className="gc-link" onClick={() => jump(a.id)}>Revisit</button></li>)}</ul>
  </details></aside>;

  return <section className="gc" aria-label="Procedural guidance" data-origin={origin} data-highlight={highlight ?? undefined}>
    <header className="gc-head">
      <div className="gc-titlerow"><h2 className="gc-title">{doc.title}</h2><span className={`gc-origin gc-origin-${origin}`} title={ORIGIN_TEXT[origin].detail}>{ORIGIN_TEXT[origin].label}</span></div>
      <p className="gc-meta">{names.length > 0 && <>{names.join(' · ')} · </>}<span className="gc-qual">{qualifier(doc)}{incomplete(doc) && ' · partial coverage'}</span></p>
      {supports.length > 0 && <p className="gc-supports">Support: {supports.map(s => s.label).join(' · ')}</p>}
      <div className="gc-tools">
        {!readOnly && <button type="button" className="gc-chip" onClick={() => setSheet('support')}><SlidersIcon />Support</button>}
        {layout.prepare && <button type="button" className="gc-chip" onClick={() => setSheet('prepare')}><ListIcon />Before you start ({doc.facts.length})</button>}
        <button type="button" className="gc-chip" onClick={() => setSheet('sources')}><InfoIcon />Sources and scope</button>
      </div>
    </header>

    {!layout.map && (doc.stage_edges.length > 0 || doc.parallel.length > 0 || doc.parallel_areas.length > 0) && <details className="gc-links" data-support="relationships"><summary>Service dependencies and parallel work</summary>
      {doc.stage_edges.length > 0 && <><b>Service-level dependencies</b>{doc.stage_edges.map((edge, i) => <p key={`s${i}`}>{doc.stages.find(s => s.service_id === edge.target_id)?.name} depends on {doc.stages.find(s => s.service_id === edge.source_id)?.name}. This does not add action-level prerequisites.</p>)}</>}
      {doc.parallel.map(group => <p key={group.group_id}>Explicit parallel work: {doc.actions.filter(a => group.action_ids.includes(a.id)).map(a => displayTitle(a)).join(' + ')}.</p>)}
      {doc.parallel_areas.map((area, i) => <p key={`a${i}`}>Explicit parallel work areas: {area.map(e => expressionText(e, doc)).join(' + ')}.</p>)}
    </details>}

    {layout.map && <ProcessMap doc={doc} onAction={jump} current={guided ? current.id : undefined} event={readOnly ? undefined : type => event({ type })} />}

    {guided ? <div className="gc-guided">
      {layout.strip === 'dots' && <ol className="gc-dots" aria-label="Browsing position" data-support="navigation">{browsing.map(a => <li key={a.id}>
        <button type="button" title={displayTitle(a)} aria-label={`${displayTitle(a)}${shown.seen.includes(a.id) ? ' (viewed)' : ''}`} aria-current={a.id === current.id ? 'step' : undefined}
          className={shown.seen.includes(a.id) ? 'seen' : undefined} onClick={() => jump(a.id)}><MarkDot mark={marks.get(a.id)!} /></button></li>)}</ol>}
      {recap}
      <article className="gc-focus" aria-labelledby={`gc-fh-${current.id}`}>
        {mark.note && <p className="gc-routehead"><MarkDot mark={mark} />{mark.note}{optionConditions.length > 0 && <> — {optionConditions.join(' AND ')}</>}</p>}
        <h3 id={`gc-fh-${current.id}`} tabIndex={-1} className="gc-focus-title">{displayTitle(current)}</h3>
        <Cues action={current} doc={doc} layout={layout} shownConditions={optionConditions} jump={jump} />
        <ActionBody {...common} action={current} shownConditions={optionConditions} />
        {otherOptions.map(o => <p className="gc-other" key={o.option_id}>Other route: {o.condition_ids.map(id => doc.conditions.find(c => c.condition_id === id)?.text).join(' AND ') || 'another route'}{' '}
          <button type="button" className="gc-link" onClick={() => { const first = doc.actions.find(a => o.action_ids.includes(a.id)); if (first) { setRouteSel(r => ({ ...r, [currentGroup!.group_id]: o.option_id })); if (!readOnly) event({ type: 'route_focus', value: o.option_id }); jump(first.id); } }}>Show this route</button></p>)}
      </article>
      <nav className="gc-pager" aria-label="Browse guidance">
        <button type="button" className="gc-btn gc-btn-quiet" disabled={position <= 0} onClick={() => jump(browsing[position - 1].id)}>Back</button>
        <p className="gc-where" aria-live="polite">Browsing position {position + 1} of {browsing.length}<span className="sr-only">: {displayTitle(current)}</span></p>
        <button type="button" className="gc-btn" disabled={position === browsing.length - 1} onClick={() => jump(browsing[Math.max(0, position + 1)].id)}>Next</button>
      </nav>
      <p className="gc-fine">Your position in the guidance, in browsing order. Viewing an action does not mean it has been done.{doc.branches.some(b => b.selection === 'XOR') && ' Alternative routes are listed separately; follow only the one that applies.'}</p>
      <details className="gc-jump"><summary>All actions</summary><JumpList doc={doc} marks={marks} current={current.id} seen={shown.seen} onJump={jump} /></details>
    </div> : <>
      {recap}
      <Overview doc={doc} s={{ ...common, openIds, toggle, routeSel: focused, selectRoute, marks }} />
    </>}

    {doc.facts.some(f => f.kind === 'fee') && <p className="gc-fine">Charges sit with the action they belong to and are never added up. The action text says what each covers.</p>}
    {layout.prepare === false && orphanFacts.length > 0 && <p className="gc-fine"><b>Also supplied (service-level):</b> {orphanFacts.map(f => factLabel(f, doc)).join(' · ')}</p>}
    {!readOnly && <FeedbackLine origin={origin} existing={view.rating} canRate={view.displayed.length > 0} routing={journey.routing} research={research} rate={rate} event={event} />}

    {sheet === 'support' && <Sheet title="Adjust support" onClose={() => setSheet(null)}>
      <SupportContent doc={doc} config={config} viewId={view.id} allowed={allowed} onChange={change} event={event}
        onUndo={view.parent ? () => adjust(journey.views[view.parent!].configuration) : undefined} /></Sheet>}
    {sheet === 'prepare' && <Sheet title="Before you start" onClose={() => setSheet(null)}><PreparationSummary doc={doc} checklist /></Sheet>}
    {sheet === 'sources' && <Sheet title="Sources and scope" onClose={() => setSheet(null)}><SourcesContent doc={doc} event={emit} /></Sheet>}
  </section>;
}
