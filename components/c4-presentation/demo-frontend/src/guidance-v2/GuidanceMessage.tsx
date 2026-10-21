import { useEffect, useRef, useState } from 'react';
import type { Configuration, Document, EventInput, Journey, Receipt } from './types';
import { expressionText, previousActions } from './semantics';
import { actionMarks, browsingList, displayTitle, factLabel, groupFacts, hasRelations, originOf, prefersReducedMotion, sourceFor } from './presentation';
import type { FactEntry } from './presentation';
import type { Dimension } from './presentation';
import ProcessMap from './ProcessMap';
import StepCard from './ui/StepCard';
import FeedbackCard from './ui/FeedbackCard';
import { RecapTrail, ServiceHeader, SourcesPanel, SupportLine, SupportSheet } from './ui/parts';

export function PreparationSummary({ doc, checklist = false }: { doc: Document; checklist?: boolean }) {
  const [done, setDone] = useState<string[]>([]);
  const toggle = (key: string) => setDone(old => old.includes(key) ? old.filter(x => x !== key) : [...old, key]);
  const groups = groupFacts(doc);
  const item = (entry: FactEntry, scope: string, key: string, service?: boolean) => {
    const f = entry.fact, label = factLabel(f, doc), source = sourceFor(doc, f.fact_id);
    return <li key={key}>{checklist
      ? <label className="v2-check"><input type="checkbox" checked={done.includes(key)} onChange={() => toggle(key)} /><span>{label}</span></label>
      : label}
      <small className="v2-kind">{f.kind === 'fee' ? 'Charge' : 'Document'}</small>
      <small>{service ? (f.kind === 'fee' ? 'Service-level charge; no action-level fee inferred.' : 'Service-level fact; action scope not supplied') : scope}</small>
      {entry.routes.length > 0 && entry.always.length > 0 && entry.routes.map(a => <small className="v2-route-line" key={a.id}>Route-dependent: {a.conditions.length ? `if ${a.conditions.join(' AND ')}, ` : ''}{displayTitle(a)}</small>)}
      {source && <a className="v2-fine" href={source.url} target="_blank" rel="noreferrer">Source</a>}</li>;
  };
  return <aside className="v2-summary" id="v2-prep" data-support="summary"><h3>Before you start</h3>
    {checklist && <p className="v2-fine">Optional tick-list for your own reference. Ticking does not confirm that anything is prepared or done, and nothing is sent or saved.</p>}
    {groups.always.length > 0 && <section><h4>Needed in every case</h4><ul>{groups.always.map(e => item(e, e.always.map(a => displayTitle(a)).join('; '), `always:${e.fact.fact_id}`))}</ul></section>}
    {groups.conditional.map(g => <section key={g.key}><h4>Only if: {g.key}</h4><ul>{g.entries.map(e => item(e, e.routes.map(a => displayTitle(a)).join('; '), `${g.key}:${e.fact.fact_id}`))}</ul></section>)}
    {groups.service.length > 0 && <section><h4>Not tied to a specific action</h4><ul>{groups.service.map(f => item({ fact: f, always: [], routes: [] }, '', `service:${f.fact_id}`, true))}</ul></section>}
    <p className="v2-fine">Charges are not added into a total. Read each action for timing, exclusions and applicable conditions.</p>
    {doc.actions.some(a => a.actor) && <p className="v2-fine">{doc.actions.filter(a => a.actor).map(a => `${displayTitle(a)}: ${a.actor}`).join(' · ')}</p>}
  </aside>;
}

type Props = {
  journey: Journey; event: (e: EventInput) => void; adjust: (c: Configuration) => void; rate: (r: string) => Promise<Receipt>;
  readOnly?: boolean; research?: boolean; onCompare?: () => void; highlight?: Dimension | null;
};

export default function GuidanceMessage({ journey, event, adjust, rate, readOnly = false, research = false, onCompare, highlight = null }: Props) {
  const view = journey.views[journey.current_view], config = view.configuration, doc = journey.document;
  const [focus, setFocus] = useState(journey.focus ?? doc.actions[0]?.id ?? '');
  const current = doc.actions.find(a => a.id === focus) ?? doc.actions[0];
  // Read-only views keep a local viewed list, so recap and position markers still work without recording anything.
  const [localSeen, setLocalSeen] = useState<string[]>([]);
  const shown = readOnly ? { ...journey, seen: [...new Set([...journey.seen, ...localSeen, current.id])] } : journey;
  const previous = previousActions(shown, current.id);
  const controls = useRef<HTMLElement>(null), focusTarget = useRef<string | null>(null);

  useEffect(() => {
    if (readOnly) return;
    const observer = new IntersectionObserver(entries => {
      for (const entry of entries) if (entry.isIntersecting) {
        const dimension = (entry.target as HTMLElement).dataset.dimension;
        if (dimension) event({ type: 'opportunity_visible', opportunity_id: `${view.id}:${dimension}` });
        observer.unobserve(entry.target);
      }
    }, { threshold: 0.5 });
    controls.current?.querySelectorAll('[data-dimension]').forEach(el => observer.observe(el));
    return () => observer.disconnect();
  }, [view.id, event, readOnly]);

  useEffect(() => {
    const id = focusTarget.current;
    if (!id) return;
    focusTarget.current = null;
    const heading = document.getElementById(`v2-h-${id}`);
    if (config.navigation === 'overview') document.getElementById(`v2-${id}`)?.scrollIntoView({ behavior: prefersReducedMotion() ? 'auto' : 'smooth', block: 'start' });
    heading?.focus({ preventScroll: true });
  }, [focus, config.navigation]);

  const browsing = browsingList(journey), marks = actionMarks(doc);
  const position = browsing.findIndex(a => a.id === current.id);
  const jump = (id: string) => { focusTarget.current = id; setFocus(id); if (readOnly) setLocalSeen(s => [...s, current.id, id]); else event({ type: 'navigate', action_id: id }); };
  const allowed = (key: keyof Configuration, value: string) => doc.capabilities[key].states.includes(value)
    && (!journey.available_configurations || journey.available_configurations.some(c => Object.entries({ ...config, [key]: value }).every(([k, v]) => c[k as keyof Configuration] === v)));
  const change = (key: keyof Configuration, value: string) => adjust({ ...config, [key]: value } as Configuration);
  const guided = config.navigation === 'guided';
  const actions = guided ? [current] : doc.actions;
  const orphanFacts = doc.facts.filter(f => !doc.actions.some(a => a.fact_ids.includes(f.fact_id)));
  const noop = () => undefined;

  return <section className="v2-message" aria-label="Procedural guidance" data-highlight={highlight ?? undefined}>
    <ServiceHeader doc={doc} />
    <SupportLine origin={originOf(journey)} config={config} onCompare={readOnly ? undefined : onCompare}>
      {!readOnly && <SupportSheet doc={doc} config={config} allowed={allowed} onChange={change} controlsRef={controls}
        onUndo={view.parent ? () => adjust(journey.views[view.parent!].configuration) : undefined} />}
    </SupportLine>
    {config.relationships !== 'map' && (doc.stage_edges.length > 0 || doc.parallel.length > 0 || doc.parallel_areas.length > 0) && <aside className="v2-essential-relationships" data-support="relationships"><h3>Supplied process relationships</h3>
      {doc.stage_edges.length > 0 && <><strong>Service-level dependencies</strong>{doc.stage_edges.map((edge, i) => <p key={`stage-${i}`}>{doc.stages.find(s => s.service_id === edge.target_id)?.name} depends on {doc.stages.find(s => s.service_id === edge.source_id)?.name}. This does not add action-level prerequisites.</p>)}</>}
      {doc.parallel.map(group => <p key={group.group_id}>Explicit parallel work: {doc.actions.filter(a => group.action_ids.includes(a.id)).map(a => displayTitle(a)).join(' + ')}.</p>)}
      {doc.parallel_areas.map((area, i) => <p key={`area-${i}`}>Explicit parallel work areas: {area.map(e => expressionText(e, doc)).join(' + ')}.</p>)}
    </aside>}
    {config.summary === 'on' && <PreparationSummary doc={doc} checklist />}
    {config.summary === 'off' && orphanFacts.length > 0 && <aside className="v2-summary"><h3>Additional supplied requirements</h3><ul>{orphanFacts.map(f => <li key={f.fact_id}>{factLabel(f, doc)} (service-level scope)</li>)}</ul></aside>}
    {config.relationships === 'map' && <ProcessMap doc={doc} onAction={jump} event={readOnly ? undefined : type => event({ type })}
      onHide={readOnly ? undefined : () => change('relationships', 'none')} hideDisabled={!allowed('relationships', 'none')} />}
    {doc.branches.map(b => <section className="v2-route" key={b.group_id}><h3>{b.selection === 'XOR' ? 'Choose the route that applies' : b.selection === 'AND' ? 'Joint requirements' : 'Applicable options'}</h3>
      <p>{b.selection === 'XOR' ? 'These are supplied alternatives. Showing a route does not check whether it applies to you.' : b.selection === 'AND' ? 'These supplied options are joint requirements.' : 'More than one option may apply. Check each supplied condition; all options remain available.'}</p>
      <div className="v2-route-options">{b.options.map(o => <div key={o.option_id}><strong>{o.condition_ids.map(id => doc.conditions.find(c => c.condition_id === id)?.text).join(' AND ') || 'No additional condition supplied'}</strong>
        <p>{doc.actions.filter(a => o.action_ids.includes(a.id)).map(a => displayTitle(a)).join(' · ')}</p>
        {b.selection === 'XOR' && <button type="button" onClick={() => { if (!readOnly) event({ type: 'route_focus', value: o.option_id }); jump(doc.actions.find(a => o.action_ids.includes(a.id))!.id); }}>Show this route</button>}</div>)}</div>
    </section>)}
    {guided
      ? <nav className="v2-stepper" aria-label="Action navigation" data-support="navigation">
        <p className="v2-where" aria-live="polite">Browsing position {position + 1} of {browsing.length}<span className="sr-only">: {displayTitle(current)}</span></p>
        <ol className="v2-steps">{browsing.map(a => <li key={a.id}><button type="button" title={displayTitle(a)} aria-current={a.id === current.id ? 'step' : undefined} className={shown.seen.includes(a.id) ? 'seen' : undefined} onClick={() => jump(a.id)}>
          <span className={`v2-dot v2-num-${marks.get(a.id)!.kind}`} aria-hidden="true">{marks.get(a.id)!.label || '•'}</span><span className="v2-steplabel">{displayTitle(a)}</span>{marks.get(a.id)!.note && <span className="sr-only"> ({marks.get(a.id)!.note})</span>}{shown.seen.includes(a.id) && <span className="sr-only"> (viewed)</span>}</button></li>)}</ol>
        <p className="v2-fine">Your position in the guidance, in browsing order. Viewing an action does not mean it has been done.{doc.branches.some(b => b.selection === 'XOR') && ' Alternative routes are listed separately; follow only the one that applies.'}</p>
      </nav>
      : doc.actions.length > 4 && <nav className="v2-index" aria-label="All guidance actions"><span>Jump to</span>{doc.actions.map(a => <button type="button" key={a.id} aria-current={focus === a.id ? 'step' : undefined} onClick={() => jump(a.id)}>{displayTitle(a)}</button>)}</nav>}
    {hasRelations(doc) && !guided && <p className="v2-fine">Listed for browsing. Relationships shown say what must come first.</p>}
    {doc.facts.some(f => f.kind === 'fee') && <p className="v2-fine">Charges sit with the action they belong to and are never added up. The action text says what each covers.</p>}
    <ol className="v2-path">{actions.map(a => <li key={a.id}><StepCard action={a} mark={marks.get(a.id)!} doc={doc} config={config} viewId={view.id} readOnly={readOnly}
      event={readOnly ? noop : event} jump={jump}
      recap={a.id === current.id && config.recap === 'on' && previous.length > 0 ? <RecapTrail previous={previous} jump={jump} onOpen={() => { if (!readOnly) event({ type: 'recap_open', action_id: current.id }); }} /> : null} /></li>)}</ol>
    {guided && <nav className="v2-pager" aria-label="Browse guidance"><button type="button" disabled={position <= 0} onClick={() => jump(browsing[position - 1].id)}>Back</button>
      <button type="button" className="v2-primary" disabled={position === browsing.length - 1} onClick={() => jump(browsing[Math.max(0, position + 1)].id)}>Next</button></nav>}
    {!readOnly && <FeedbackCard origin={originOf(journey)} existing={view.rating} canRate={view.displayed.length > 0} routing={journey.routing} research={research} rate={rate} event={event} />}
    <SourcesPanel doc={doc} event={readOnly ? noop : event} />
  </section>;
}
