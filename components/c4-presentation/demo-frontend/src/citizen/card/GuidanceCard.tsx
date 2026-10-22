import { useEffect, useMemo, useRef, useState } from 'react';
import type { Configuration, EventBody, GuidanceResponse, RatingReason, RenderedAction, Route, RouteOption } from '../types';
import type { Layer } from '../model';
import { byId, entryOf, headingOf, layersOf, originOf, paragraphs, phaseGroups, phaseOf, plainName, procedureFacts } from '../model';
import { ChevronIcon, ExpandIcon, InfoIcon, ListIcon, SlidersIcon, Sheet } from '../ui';
import { Facts, Marker, StepBody } from './StepParts';
import RouteChoice from './Routes';
import ProcessGraph from './ProcessGraph';
import { SourcesContent, SupportControls } from './Sheets';
import FeedbackBar from './FeedbackBar';

type Props = {
  response: GuidanceResponse;
  emit?: (body: EventBody, options?: { refresh?: boolean }) => unknown;
  adjust?: (c: Configuration) => void;
  rate?: (rating: 'fits' | 'does_not_fit', reasons: RatingReason[]) => Promise<unknown>;
  busy?: boolean;
  /** Comparison and embedded previews: nothing is sent to the backend and local choices stay local. */
  readOnly?: boolean;
  research?: boolean;
};
type SheetName = 'support' | 'sources' | 'map' | 'peek' | null;
const noop = () => undefined;
const letter = (i: number) => String.fromCharCode(97 + i);

/** Browsing order for a read-only view: verified layers, with route steps only for chosen routes. */
function localBrowsing(response: GuidanceResponse, routes: Record<string, string[]>): string[] {
  const doc = response.document;
  return doc.actions.filter(a => !a.branch || routes[a.branch]?.includes(a.option ?? ''))
    .sort((a, b) => (entryOf(doc, a.id)?.layer ?? 0) - (entryOf(doc, b.id)?.layer ?? 0) || a.id.localeCompare(b.id)).map(a => a.id);
}

export default function GuidanceCard({ response, emit, adjust, rate, busy = false, readOnly = false, research = false }: Props) {
  const { document: doc, interaction, selection, controls } = response, config = doc.configuration, origin = originOf(response);
  const send = readOnly || !emit ? noop : emit;
  const guided = config.navigation === 'guided';

  // Live views read the server's interaction state; read-only views keep the same state locally.
  const [local, setLocal] = useState(() => ({ routes: interaction.route_choices, open: [] as string[], map: interaction.map_visible, active: interaction.navigation.active_action_id, seen: [] as string[] }));
  const routes = readOnly ? local.routes : interaction.route_choices;
  const openIds = readOnly ? local.open : interaction.explanation_open_action_ids;
  const mapVisible = readOnly ? local.map : interaction.map_visible;
  const browsing = readOnly ? localBrowsing(response, routes) : interaction.navigation.browsing_action_ids;
  const activeId = readOnly ? (local.active && browsing.includes(local.active) ? local.active : browsing[0] ?? null) : interaction.navigation.active_action_id;
  const position = activeId ? browsing.indexOf(activeId) : -1;
  const prevId = readOnly ? browsing[position - 1] ?? null : interaction.navigation.previous_action_id;
  const nextId = readOnly ? browsing[position + 1] ?? null : interaction.navigation.next_action_id;
  const [sheet, setSheet] = useState<SheetName>(null);
  const visited = useRef(new Set<string>());

  const chooseRoute = (route: Route, optionIds: string[]) => {
    if (readOnly) setLocal(s => ({ ...s, routes: { ...s.routes, [route.branch_id]: optionIds } }));
    else send({ type: 'route_focus', branch_id: route.branch_id, option_ids: optionIds });
  };
  const toggleExplanation = (id: string, open: boolean) => {
    if (readOnly) setLocal(s => ({ ...s, open: open ? [...s.open, id] : s.open.filter(x => x !== id) }));
    else send({ type: open ? 'explanation_open' : 'explanation_close', action_id: id });
  };
  const go = (id: string | null) => {
    if (!id) return;
    if (readOnly) setLocal(s => ({ ...s, active: id, seen: [...new Set([...s.seen, id])] }));
    else send({ type: 'navigate', action_id: id });
  };
  /** Explicit engagement with a step in Overview (click or focus inside it) is a visit; mounting or scrolling is not. */
  const engage = (id: string) => {
    if (readOnly || guided || visited.current.has(`${response.view_id}:${id}`)) return;
    visited.current.add(`${response.view_id}:${id}`);
    send({ type: 'step_open', action_id: id });
  };
  const setMap = (visible: boolean) => { if (readOnly) setLocal(s => ({ ...s, map: visible })); else send({ type: visible ? 'map_show' : 'map_hide' }); };

  // Exposure: record the essential layers actually displayed, once per view. Exposure is not a visit.
  const displayedIds = useMemo(() => {
    if (guided) return activeId ? [activeId] : [];
    return doc.actions.filter(a => !a.branch || routes[a.branch]?.includes(a.option ?? '')).map(a => a.id);
  }, [doc.actions, guided, activeId, routes]);
  const sentView = useRef<string | null>(null);
  useEffect(() => {
    if (readOnly || sentView.current === response.view_id || displayedIds.length === 0) return;
    sentView.current = response.view_id;
    send({ type: 'view_displayed', action_ids: displayedIds }, { refresh: false });
  }, [readOnly, response.view_id, displayedIds, send]);

  // Overview recap needs viewport evidence, so report which steps are on screen.
  const root = useRef<HTMLElement>(null), lastViewport = useRef('');
  useEffect(() => {
    if (readOnly || guided || config.recap !== 'on' || !root.current || typeof IntersectionObserver === 'undefined') return;
    const visible = new Set<string>(); let timer: number | undefined;
    const observer = new IntersectionObserver(entries => {
      for (const e of entries) { const id = (e.target as HTMLElement).dataset.stepId!; if (e.isIntersecting) visible.add(id); else visible.delete(id); }
      window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        const ids = [...visible].sort(), key = ids.join('|');
        if (key !== lastViewport.current) { lastViewport.current = key; send({ type: 'viewport_changed', action_ids: ids }); }
      }, 400);
    }, { threshold: 0.4 });
    root.current.querySelectorAll('[data-step-id]').forEach(el => observer.observe(el));
    return () => { window.clearTimeout(timer); observer.disconnect(); };
  }, [readOnly, guided, config.recap, displayedIds, send]);

  const phases = phaseGroups(doc), numbered = doc.navigation.numbering_enabled;
  const headingTag = (phases ? 'h4' : 'h3') as 'h3' | 'h4';
  const procedure = procedureFacts(doc);
  const agencies = [...new Set(doc.actions.map(a => a.agency))];
  const adjustable = controls.configuration_adjustment && !readOnly && !!adjust;

  const stepArticle = (a: RenderedAction, marker: string, markerKind: 'step' | 'route' = 'step', hide: string[] = []) => {
    const H = headingTag;
    return <article className="cz-step" key={a.id} data-step-id={a.id} id={`cz-step-${a.id}`} tabIndex={-1} onClick={() => engage(a.id)} onFocusCapture={() => engage(a.id)}>
      <header className="cz-stephead"><Marker text={marker} kind={markerKind} /><H>{headingOf(a, doc.source_limit)}</H></header>
      <StepBody action={a} doc={doc} config={config} open={openIds.includes(a.id)} onToggle={toggleExplanation} hideConditions={hide} heading={headingOf(a, doc.source_limit)} />
    </article>;
  };
  const routeSteps = (o: RouteOption) => <div className="cz-routesteps">{o.action_ids.map(id => byId(doc, id)).filter((a): a is RenderedAction => !!a)
    .sort((x, y) => (entryOf(doc, x.id)?.route_layer ?? 0) - (entryOf(doc, y.id)?.route_layer ?? 0) || x.id.localeCompare(y.id))
    .map(a => { const rl = entryOf(doc, a.id)?.route_layer; return stepArticle(a, numbered && rl ? `${rl}` : '', 'route', o.conditions); })}</div>;
  const inRoute = (o: RouteOption) => o.action_ids.map(id => byId(doc, id)).filter((a): a is RenderedAction => !!a)
    .sort((x, y) => (entryOf(doc, x.id)?.route_layer ?? 0) - (entryOf(doc, y.id)?.route_layer ?? 0) || x.id.localeCompare(y.id));
  const routePreview = (o: RouteOption) => <ol className="cz-preview" aria-label="Steps on this route">{inRoute(o).map(a => <li key={a.id}>{headingOf(a, doc.source_limit)}</li>)}</ol>;
  const routeFacts = (route: Route) => doc.facts.filter(f => f.scope === 'route' && f.branch_id === route.branch_id);
  const routeBlock = (route: Route) => <RouteChoice key={route.branch_id} route={route} selected={routes[route.branch_id] ?? []} onChoose={ids => chooseRoute(route, ids)} steps={routeSteps} preview={routePreview} facts={routeFacts(route)} doc={doc} />;

  const layerList = (layers: Layer[]) => <ol className="cz-layers">{layers.map(l => {
    const many = l.peers.length + l.routes.length > 1;
    return <li key={String(l.layer)} className="cz-layer">
      {numbered && l.layer != null && <p className="cz-layerhead"><b>Step {l.layer}</b>{many && <span> · no fixed order</span>}</p>}
      {l.peers.map((a, i) => stepArticle(a, many ? `${l.layer ?? ''}${letter(i)}` : ''))}
      {l.routes.map(routeBlock)}
    </li>;
  })}</ol>;

  const recap = interaction.recap.enabled && interaction.recap.items.length > 0 && <aside className="cz-recap" data-support="recap">
    <details open onToggle={e => { if (!readOnly) send({ type: e.currentTarget.open ? 'recap_open' : 'recap_close' }, { refresh: false }); }}>
      <summary>Earlier steps you viewed ({interaction.recap.items.length})</summary>
      <ul>{interaction.recap.items.map(i => <li key={i.action_id}>{i.text}</li>)}</ul>
      <p className="cz-fine">{interaction.recap.label}</p>
    </details></aside>;

  const mapNode = config.relationships === 'map' && doc.relationship_aid.map && <section className="cz-map" aria-label="Process map" data-support="relationships">
    <div className="cz-maphead"><h3>Process map</h3><div>
      <button type="button" className="cz-chip" aria-pressed={mapVisible} onClick={() => setMap(!mapVisible)}>{mapVisible ? 'Hide map' : 'Show map'}</button>
      {mapVisible && <button type="button" className="cz-chip" onClick={() => { send({ type: 'map_expand' }); setSheet('map'); }}><ExpandIcon />Expand</button>}</div></div>
    {mapVisible && <div className="cz-mapcanvas"><ProcessGraph doc={doc} map={doc.relationship_aid.map} size="compact" activeId={guided ? activeId : null} onSelect={id => { if (!guided) engage(id); go(id); }} /></div>}
    <details className="cz-more"><summary>Text version of the map</summary><ul>{doc.relationship_aid.map.text_equivalent.map((t, i) => <li key={i}>{t}</li>)}</ul></details>
  </section>;

  // Only facts that no step or route can claim stay here, as one slim row. Facts that belong to a step are shown at that step instead.
  const factsPanel = (procedure.documents.length + procedure.fees.length > 0) && <aside className="cz-service" aria-label="For the whole service">
    <p className="cz-service-h">For the whole service</p>
    <Facts facts={[...procedure.documents, ...procedure.fees]} doc={doc} />
    {procedure.fees.length > 1 && <p className="cz-fine">Charges are listed separately and are not added together.</p>}
  </aside>;

  const phase = phaseOf(doc, activeId);
  const activeAction = activeId ? byId(doc, activeId) : null;
  const entry = activeId ? entryOf(doc, activeId) : null;
  const activeRoute = activeId ? doc.routes.find(r => r.options.some(o => o.action_ids.includes(activeId))) : undefined;
  const unresolved = doc.routes.filter(r => r.selection !== 'AND' && (routes[r.branch_id] ?? []).length === 0);

  return <section ref={root} className="cz" aria-label="Procedural guidance" data-origin={origin.kind} data-kind={selection.kind} data-busy={busy || undefined}>
    <header className="cz-head">
      <div className="cz-titlerow"><h2>{plainName(response.procedure_title)}</h2>
        <span className={`cz-origin cz-origin-${origin.kind}`} title={origin.note}>{origin.label}</span></div>
      <p className="cz-meta">{agencies.join(' · ')}{agencies.length > 0 && ' · '}<span>{doc.synthetic ? 'Fictional example, not an official service' : 'Official-source snapshot, not live or independently verified'}</span></p>
      {response.preparation.content_state === 'demo_accepted' && <p className="cz-provisional" role="note"><b>Local research demo wording.</b> AI-assisted and checked only by automatic source-grounding checks. The project owner accepted it for this demonstration; no expert or government body has reviewed it.</p>}
      {response.preparation.content_state === 'provisional_demo' && <p className="cz-provisional" role="note"><b>Provisional demo wording.</b> Written with AI assistance and checked only by automatic source-grounding checks. No person or authority has reviewed it.</p>}
      <div className="cz-tools">
        {adjustable && <button type="button" className="cz-chip" onClick={() => setSheet('support')}><SlidersIcon />Support</button>}
        <button type="button" className="cz-chip" onClick={() => setSheet('sources')}><InfoIcon />Sources</button>
        {guided && <button type="button" className="cz-chip" onClick={() => { send({ type: 'overview_peek' }, { refresh: false }); setSheet('peek'); }}><ListIcon />Overview</button>}
      </div>
    </header>

    {factsPanel}
    {mapNode}
    {recap}

    {guided ? <div className="cz-guided">
      <nav className="cz-orient" aria-label="Where you are" data-support="navigation">
        <p>{phase && <span className="cz-phaselabel" data-support="segmentation">{phase.label.text}{doc.phase_order.length > 0 && ` (phase ${doc.phase_order.indexOf(phase.id) + 1} of ${doc.phase_order.length})`}</span>}
          {numbered && entry?.layer != null && <b>Step {entry.layer}</b>}
          {position >= 0 && <span className="cz-fine">{position + 1} of {browsing.length}</span>}</p>
        {browsing.length > 1 && <details className="cz-steplist"><summary>Steps <ChevronIcon /></summary>
          <ol>{browsing.map(id => { const a = byId(doc, id)!; return <li key={id}><button type="button" aria-current={id === activeId ? 'step' : undefined} onClick={() => go(id)}>{headingOf(a, doc.source_limit)}</button></li>; })}</ol></details>}
      </nav>
      {doc.routes.map(r => <RouteChoice key={r.branch_id} route={r} selected={routes[r.branch_id] ?? []} onChoose={ids => chooseRoute(r, ids)} preview={routePreview} facts={routeFacts(r)} doc={doc} compact />)}
      {activeAction
        ? <article className="cz-step cz-focus" data-step-id={activeAction.id} aria-labelledby={`cz-fh-${activeAction.id}`}>
          {activeRoute && <p className="cz-routehead"><Marker text={String.fromCharCode(65 + activeRoute.options.findIndex(o => o.action_ids.includes(activeAction.id)))} kind="route" />
            {activeRoute.options.find(o => o.action_ids.includes(activeAction.id))?.label}</p>}
          <h3 id={`cz-fh-${activeAction.id}`} tabIndex={-1}>{headingOf(activeAction, doc.source_limit)}</h3>
          <StepBody action={activeAction} doc={doc} config={config} open={openIds.includes(activeAction.id)} onToggle={toggleExplanation} heading={headingOf(activeAction, doc.source_limit)}
            hideConditions={activeRoute?.options.find(o => o.action_ids.includes(activeAction.id))?.conditions ?? []} />
        </article>
        : unresolved.length > 0 && <p className="cz-fine">Choose the route that applies to continue.</p>}
      <nav className="cz-pager" aria-label="Browse guidance">
        <button type="button" className="cz-btn cz-btn-quiet" disabled={!prevId || busy} onClick={() => go(prevId)}>Back</button>
        <p className="cz-fine" aria-live="polite">{position >= 0 ? `${position + 1} of ${browsing.length}` : ''}</p>
        <button type="button" className="cz-btn" disabled={!nextId || busy} onClick={() => go(nextId)}>Next</button>
      </nav>
      {research && <p className="cz-fine">{doc.navigation.order_semantics}</p>}
    </div> : phases
      ? <div className="cz-phases" data-support="segmentation">{phases.map(p => <section key={p.id} className="cz-phase" aria-labelledby={`cz-ph-${p.id}`}>
        <h3 id={`cz-ph-${p.id}`}>{p.ordered && <span>Phase {p.index + 1} · </span>}{p.label}</h3>{layerList(p.layers)}</section>)}</div>
      : layerList(layersOf(doc))}

    {!guided && doc.navigation.unresolved_route_ids.length > 0 && <p className="cz-fine">Choose the route that applies to see its steps in full.</p>}
    {doc.required_source_notes.map((n, i) => <aside className="cz-note" key={i}><b>Source note</b><p>{n}</p></aside>)}
    {controls.feedback && !readOnly && rate && (selection.learning_eligible || research) && <FeedbackBar eligible={selection.learning_eligible} rate={rate} busy={busy} />}

    {sheet === 'support' && adjust && <Sheet title="Adjust support" onClose={() => setSheet(null)}><SupportControls response={response} busy={busy} onChange={c => { setSheet(null); adjust(c); }} /></Sheet>}
    {sheet === 'sources' && <Sheet title="Sources and scope" onClose={() => setSheet(null)}><SourcesContent response={response} onSource={id => send({ type: 'source_open', source_id: id }, { refresh: false })} /></Sheet>}
    {sheet === 'map' && doc.relationship_aid.map && <Sheet title="Process map" variant="modal" onClose={() => { send({ type: 'map_collapse' }); setSheet(null); }}>
      <div className="cz-mapcanvas cz-mapcanvas-large"><ProcessGraph doc={doc} map={doc.relationship_aid.map} size="large" activeId={guided ? activeId : null} onSelect={id => { send({ type: 'map_collapse' }); setSheet(null); if (!guided) engage(id); go(id); }} /></div>
      <h3 className="cz-subhead">Text version</h3><ul className="cz-textlist">{doc.relationship_aid.map.text_equivalent.map((t, i) => <li key={i}>{t}</li>)}</ul></Sheet>}
    {sheet === 'peek' && <Sheet title="Overview (read-only)" onClose={() => setSheet(null)}>
      <p className="cz-fine">A temporary look at every step. Your guided view and its settings stay as they are.</p>
      {layersOf(doc).map(l => <div key={String(l.layer)} className="cz-peek">
        {numbered && l.layer != null && <p className="cz-layerhead"><b>Step {l.layer}</b></p>}
        <ul>{l.peers.map(a => <li key={a.id}><b>{headingOf(a, doc.source_limit)}</b><span>{paragraphs(a.essential, doc.source_limit)[0]}</span></li>)}
          {l.routes.map(r => <li key={r.branch_id}><b>{r.selection === 'XOR' ? 'Choose one route' : 'Routes'}</b>
            <ul>{r.options.map(o => <li key={o.option_id}><span>{o.label}</span><small>{o.action_ids.map(id => byId(doc, id)).filter((a): a is RenderedAction => !!a).map(a => headingOf(a, doc.source_limit)).join(' · ')}</small></li>)}</ul></li>)}</ul></div>)}
    </Sheet>}
  </section>;
}
