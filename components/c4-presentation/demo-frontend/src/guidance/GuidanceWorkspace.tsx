import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { API_BASE, api } from "../api/client";
import type { ActiveIdentity, GuestSession, ProcedureSummary } from "../api/types";
import FeedbackPanel from "../feedback/FeedbackPanel";
import { browserStorage } from "../session/continuity";
import { guidanceApi } from "./api";
import { GuidanceEpisode } from "./episode";
import { ActionSection, PreviousStepSummary, SelectedAids, ServiceRequirements, SourceItems, SourceRegister } from "./rendering";
import { actionDomId, actionTitle } from "./scaffoldModel";
import { actionLabel, documentOf } from "./types";
import type { Standard } from "./types";
import type { Navigation } from "./types";
import { AdjustmentFlow, emptyFlow } from "../adjustments/flow";
import { AdjustmentControls, ManualViewFeedback } from "../adjustments/AdjustmentControls";

const noSubscription = () => () => {};
const emptySnapshot = () => emptyFlow;

function scrollToAction(id: string) {
  const action = document.getElementById(actionDomId(id));
  const visit = document.getElementById(actionDomId(id) + "-visit");
  (visit ?? action)?.scrollIntoView({ block: "start", behavior: "auto" });
  action?.focus({ preventScroll: true });
}

export default function GuidanceWorkspace({ active, procedure, disabled, onActivityChange, onSessionUpdate }: {
  active: ActiveIdentity; procedure: ProcedureSummary; disabled: boolean;
  onActivityChange: (locked: boolean) => void;
  onSessionUpdate: (session: GuestSession) => void;
}) {
  // Parent keys this component by session, procedure and personalization revision.
  const [episode] = useState(() => new GuidanceEpisode(guidanceApi, active, procedure.procedure_id, browserStorage(), API_BASE));
  const state = useSyncExternalStore(episode.subscribe, episode.getSnapshot);
  const [writingStyle, setWritingStyle] = useState<Standard["writing_style"]>("plain");
  const [feedbackLocked, setFeedbackLocked] = useState(false);
  const restoredScroll = useRef<string | null>(null);
  const enabled = active.kind === "profile" && active.profile.personalization_enabled;
  const { result } = state;
  const rootSpec = result?.mode === "adaptive" ? result.spec : null;
  const adjustments = useMemo(() => rootSpec ? new AdjustmentFlow(rootSpec, undefined, browserStorage(), API_BASE) : null, [rootSpec]);
  const views = useSyncExternalStore(adjustments?.subscribe ?? noSubscription, adjustments?.snapshot ?? emptySnapshot);
  useEffect(() => { if (adjustments) void adjustments.initialize(); }, [adjustments]);
  const manual = !!views.value?.ledger.views.length;
  const spec = manual ? views.value!.spec : rootSpec;
  const doc = manual ? spec : result ? documentOf(result) : null;
  const focus = manual ? views.focus : state.focus;
  const navigation: Navigation | null = manual && spec && views.value ? {
    schema_version: "c4-navigation-1.0", presentation_id: spec.presentation_id, exposure_id: spec.exposure_id,
    configuration_id: spec.configuration.configuration_id, graph_fingerprint: spec.graph_fingerprint,
    session_revision: views.value.ledger.revision, acknowledged: views.value.displayed_action_ids.length > 0,
    current_action_id: focus, displayed_action_ids: views.value.displayed_action_ids,
    events: views.value.ledger.displays.filter(d => d.view_id === views.value!.active_view_id).map((d, i, rows) => ({ event_id: d.event_id, action_id: d.action_id, is_revisit: rows.slice(0, i).some(previous => previous.action_id === d.action_id), sequence: i + 1 })),
  } : state.navigation;
  const guided = spec?.configuration.presentation_mode === "GUIDED";
  const index = doc?.pages.findIndex((page) => page.action_id === focus) ?? -1;
  const current = doc?.pages[index];
  const blocked = disabled || state.loading || state.busy || state.pending !== null || feedbackLocked || views.loading || views.busy || views.pending !== null;
  const archived = result?.mode === "adaptive" && result.stale_for_display;
  const browsingBlocked = blocked || archived || (!!rootSpec && !views.ready);
  const disclaimerInNotices = doc ? doc.global_items.some((ref) => ref.kind === "notice" &&
    doc.cards.some((card) => card.source.kind === "notice" && card.source.identifier === ref.identifier &&
      card.lines.includes(doc.explanation.source.graph.disclaimer))) : false;

  useEffect(() => { void episode.initialize(); }, [episode]);
  useEffect(() => {
    if (!state.restored || state.loading || !guided || !spec || !focus ||
        restoredScroll.current === spec.exposure_id) return;
    const id = focus;
    const exposure = spec.exposure_id;
    const frame = requestAnimationFrame(() => {
      scrollToAction(id);
      restoredScroll.current = exposure;
    });
    return () => cancelAnimationFrame(frame);
  }, [state.restored, state.loading, guided, spec, focus]);
  useEffect(() => {
    onActivityChange(state.loading || state.busy || state.pending !== null || feedbackLocked || views.loading || views.busy || views.pending !== null);
    return () => onActivityChange(false);
  }, [onActivityChange, state.loading, state.busy, state.pending, feedbackLocked, views.loading, views.busy, views.pending]);
  const onVisible = useCallback((id: string) => { if (manual) void adjustments?.visible(id); else void episode.visible(id); }, [episode, manual, adjustments]);
  const onPreferencesApplied = useCallback(async () => {
    episode.freezeForPreferences();
    const session = await api.getSession(active.session.session_id);
    onSessionUpdate(session);
  }, [episode, active.session.session_id, onSessionUpdate]);
  function move(id: string) {
    if (manual) adjustments?.move(id); else episode.move(id);
    requestAnimationFrame(() => scrollToAction(id));
  }

  return <section className="panel guidance-panel" aria-labelledby="guidance-title">
    <div className="section-heading"><div><p className="eyebrow">Your guidance</p>
      <h2 id="guidance-title">{enabled ? "Guidance with personalized support" : "Clear procedure steps"}</h2></div>
      <span className="tag">{enabled ? "Adaptive engine enabled" : "Standard guidance"}</span></div>
    <p className="muted">{procedure.title}</p>
    <div className="guidance-toolbar">
      {!enabled && <label className="field-label">Writing style for this request
        <select value={writingStyle} disabled={blocked} onChange={(event) => setWritingStyle(event.target.value as Standard["writing_style"])}>
          <option value="plain">Plain</option><option value="extra_plain">Extra plain</option><option value="concise">Concise</option>
        </select>
      </label>}
      <button className="button button-primary" disabled={blocked}
        onClick={() => void episode.select(enabled ? "plain" : writingStyle)}>
        {state.busy ? "Working…" : state.loading ? "Restoring guidance…" : result ? "Request fresh guidance" : "Show guidance"}
      </button>
    </div>
    {!enabled && <p className="helper-text">Writing style is a request setting. The original requirements remain intact; offline fallback may use the same supplied wording.</p>}
    {state.error && <div className="alert alert-error" role="alert"><strong>Guidance needs attention</strong><p>{state.error}</p></div>}
    {state.pending && <div className="alert" role="status"><p>A display request is unconfirmed. Navigation is paused to preserve attribution.</p>
      <button className="button button-outline" disabled={state.busy} onClick={() => void episode.retryDisplay()}>Retry original display request</button>
      <button className="text-button" disabled={state.busy} onClick={() => episode.close()}>Leave this episode without retrying</button>
      <p className="helper-text">Leaving does not undo records already accepted by the backend.</p>
    </div>}
    {state.notice && !manual && <p className="guidance-status" role="status">{state.notice}</p>}
    {adjustments && rootSpec && <AdjustmentControls key={rootSpec.exposure_id + ":" + (views.value?.active_view_id ?? "original")} flow={adjustments} state={views}
      disabled={disabled || state.loading || state.busy || state.pending !== null || feedbackLocked || !!archived}
      focus={focus ?? state.navigation?.current_action_id ?? rootSpec.pages[0].action_id} onPreferencesApplied={onPreferencesApplied} onActivityChange={setFeedbackLocked} />}
    {doc && <div className="guidance-output">
      <div className="guidance-metadata">
        <span className="tag">{guided ? "Guided" : "Overview"}</span>
        <span className="tag">{doc.prepared_wording?.items.some((item) => item.origin === "demo_mock") ? "Prepared demo wording · pending validation" : doc.prepared_wording?.artifact_digest ? "Reviewed wording · original sources retained" :
          doc.explanation.origin === "fallback" ? "Source-preserving fallback" : "Generated explanation · original sources retained"}</span>
        <span className="tag">{doc.explanation.source.graph.synthetic ? "Synthetic demonstration" : "Supplied sources · verification status below"}</span>
      </div>
      {!disclaimerInNotices && <p className="guidance-disclaimer">{doc.explanation.source.graph.disclaimer}</p>}
      <p className="helper-text">Browsing order is not a completion checklist or eligibility decision. Viewing guidance never means an action was completed.</p>
      <div className="source-notices">
        <SourceItems doc={doc} refs={doc.global_items.filter((ref) => ref.kind === "notice")} />
      </div>
      <ServiceRequirements doc={doc} />
      {archived && <p className="guidance-stale" role="status">{manual ? "This manually adjusted view is retained for reference. Request fresh guidance to use current settings." : "This is the original acknowledged presentation retained for reference and feedback. Request fresh guidance to use current settings."}</p>}
      {manual && <p className="notice">User-adjusted view · {views.value?.original_view ? "original layout restored" : "temporary settings"} · ratings saved separately from policy learning</p>}
      {spec && <SelectedAids spec={spec} currentActionId={guided ? focus : null} />}
      {guided && spec && current ? <>
        <nav className="guided-step-list" aria-label="Browse procedure actions">
          {doc.pages.map((page, pageIndex) => <button key={page.action_id}
            disabled={browsingBlocked || !navigation?.acknowledged}
            className={page.action_id === focus ? "active" : ""}
            aria-current={page.action_id === focus ? "step" : undefined}
            onClick={() => move(page.action_id)}>
            <span className="guided-position">Action {pageIndex + 1}</span>
            <strong className="guided-short-label" title={actionLabel(doc, page.action_id)}>{actionTitle(doc, page.action_id)}</strong>
            {navigation?.displayed_action_ids.includes(page.action_id) && <small>Previously displayed</small>}
          </button>)}
        </nav>
        <p className="helper-text">Action {index + 1} of {doc.pages.length}. {doc.explanation.source.graph.branch_groups.length > 0 ? "Alternative actions remain available for inspection." : "Browsing does not mark completion."}</p>
        <div id={actionDomId(current.action_id) + "-visit"}>
          <PreviousStepSummary spec={spec} navigation={navigation} currentActionId={focus} />
          <ActionSection key={current.action_id} doc={doc} page={current} index={index}
            disabled={browsingBlocked} observeToken={String(navigation?.session_revision ?? -1)} onVisible={onVisible} />
        </div>
        <nav className="guided-navigation" aria-label="Previous and next guidance">
          <button className="button button-outline" disabled={browsingBlocked || !navigation?.acknowledged || index <= 0}
            onClick={() => move(doc.pages[index - 1].action_id)}>← Back</button>
          <span>{index + 1} / {doc.pages.length}</span>
          <button className="button button-primary" disabled={browsingBlocked || !navigation?.acknowledged || index >= doc.pages.length - 1}
            onClick={() => move(doc.pages[index + 1].action_id)}>Next →</button>
        </nav>
      </> : <div className="overview-actions">
        {doc.pages.map((page, pageIndex) => <ActionSection key={page.action_id} doc={doc} page={page} index={pageIndex}
          disabled={browsingBlocked || !spec} observeToken={String(navigation?.session_revision ?? -1)} onVisible={onVisible} />)}
      </div>}
      {manual && adjustments ? <ManualViewFeedback flow={adjustments} state={views} disabled={blocked || !!archived} /> : spec && <FeedbackPanel key={spec.exposure_id} spec={spec} navigation={navigation}
        disabled={disabled || state.loading || state.busy || state.pending !== null || !views.ready || views.busy || views.loading}
        onActivityChange={setFeedbackLocked} onPreferencesApplied={onPreferencesApplied} />}
      <SourceRegister doc={doc} serviceFactsRendered />
      <div className="exposure-status" role="status">
        {spec ? <><strong>{navigation?.acknowledged ? "Display acknowledgment recorded" : "Awaiting a visible action"}</strong>
          <p>{navigation?.displayed_action_ids.length ?? 0} of {doc.pages.length} actions recorded as displayed. This does not measure comprehension or completion.</p>
          <p className="helper-text">Navigation events: {navigation?.events.length ?? 0}. No navigation event creates a learning reward.</p>
        </> : <><strong>Standard guidance</strong><p>No adaptive exposure acknowledgment or shared policy update is recorded.</p></>}
      </div>
      <details className="guidance-attribution"><summary>Guidance reference</summary>
        <dl><dt>Graph fingerprint</dt><dd>{doc.graph_fingerprint}</dd>
          <dt>Source status</dt><dd>{doc.explanation.source_status}</dd><dt>Assurance</dt><dd>{doc.explanation.assurance}</dd>
          {doc.prepared_wording && <><dt>Prepared wording</dt><dd>{doc.prepared_wording.items.some((item) => item.origin === "demo_mock") ? "Demo mock snapshot" : doc.prepared_wording.artifact_digest ? "Reviewed snapshot" : "Source fallback"}</dd>
            <dt>Wording origins</dt><dd>{[...new Set(doc.prepared_wording.items.map((item) => item.origin))].join(", ")}</dd>
            <dt>Wording reference</dt><dd>{doc.prepared_wording.request_key}</dd></>}
          {spec && <><dt>Presentation</dt><dd>{spec.presentation_id}</dd><dt>Exposure</dt><dd>{spec.exposure_id}</dd>
            <dt>Decision</dt><dd>{spec.decision_id}</dd><dt>{manual ? "Displayed manual configuration" : "Selected configuration"}</dt><dd>{spec.configuration.configuration_id}</dd>
            {manual && <><dt>Manual view</dt><dd>{views.value?.active_view_id}</dd><dt>Original policy configuration</dt><dd>{rootSpec?.configuration.configuration_id}</dd></>}
            <dt>Decision context revision</dt><dd>{spec.context_revision}</dd><dt>Current navigation revision</dt><dd>{navigation?.session_revision ?? "Not yet acknowledged"}</dd></>}
        </dl>
      </details>
    </div>}
  </section>;
}
