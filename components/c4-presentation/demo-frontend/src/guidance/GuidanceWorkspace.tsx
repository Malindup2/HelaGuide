import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { API_BASE } from "../api/client";
import type { ActiveIdentity, ProcedureSummary } from "../api/types";
import { browserStorage } from "../session/continuity";
import { guidanceApi } from "./api";
import { GuidanceEpisode } from "./episode";
import { ActionSection, SelectedAids, SourceItems } from "./rendering";
import { actionLabel, documentOf } from "./types";
import type { Standard } from "./types";

export default function GuidanceWorkspace({ active, procedure, disabled, onActivityChange }: {
  active: ActiveIdentity; procedure: ProcedureSummary; disabled: boolean;
  onActivityChange: (locked: boolean) => void;
}) {
  // Parent keys this component by session, procedure and personalization revision.
  const [episode] = useState(() => new GuidanceEpisode(guidanceApi, active, procedure.procedure_id, browserStorage(), API_BASE));
  const state = useSyncExternalStore(episode.subscribe, episode.getSnapshot);
  const [writingStyle, setWritingStyle] = useState<Standard["writing_style"]>("plain");
  const output = useRef<HTMLDivElement>(null);
  const enabled = active.kind === "profile" && active.profile.personalization_enabled;
  const { result, navigation } = state;
  const doc = result ? documentOf(result) : null;
  const spec = result?.mode === "adaptive" ? result.spec : null;
  const guided = spec?.configuration.presentation_mode === "GUIDED";
  const index = doc?.pages.findIndex((page) => page.action_id === state.focus) ?? -1;
  const current = doc?.pages[index];
  const blocked = disabled || state.loading || state.busy || state.pending !== null;

  useEffect(() => { void episode.initialize(); }, [episode]);
  useEffect(() => {
    onActivityChange(state.loading || state.busy || state.pending !== null);
    return () => onActivityChange(false);
  }, [onActivityChange, state.loading, state.busy, state.pending]);
  const onVisible = useCallback((id: string) => { void episode.visible(id); }, [episode]);
  function move(id: string) {
    episode.move(id);
    output.current?.scrollIntoView({ block: "start", behavior: "auto" });
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
    {state.notice && <p className="guidance-status" role="status">{state.notice}</p>}
    {doc && <div ref={output} className="guidance-output">
      <div className="guidance-metadata">
        <span className="tag">{guided ? "Guided" : "Overview"}</span>
        <span className="tag">{doc.explanation.origin === "fallback" ? "Source-preserving fallback" : "Generated explanation · original sources retained"}</span>
        <span className="tag">{doc.explanation.source.graph.synthetic ? "Synthetic demonstration" : "Supplied sources · verification status below"}</span>
      </div>
      <p className="guidance-disclaimer">{doc.explanation.source.graph.disclaimer}</p>
      <p className="helper-text">Browsing order is not a completion checklist or eligibility decision. Viewing guidance never means an action was completed.</p>
      <div className="source-notices">
        <SourceItems doc={doc} refs={doc.global_items.filter((ref) => ref.kind === "notice")} />
      </div>
      {spec && <SelectedAids spec={spec} />}
      {guided && spec && current ? <>
        <nav className="guided-step-list" aria-label="Browse procedure actions">
          {doc.pages.map((page, pageIndex) => <button key={page.action_id}
            disabled={blocked || !navigation?.acknowledged}
            className={page.action_id === state.focus ? "active" : ""}
            aria-current={page.action_id === state.focus ? "step" : undefined}
            onClick={() => move(page.action_id)}>
            <span>{pageIndex + 1}</span>{actionLabel(doc, page.action_id)}
            {navigation?.displayed_action_ids.includes(page.action_id) && <small>Previously displayed</small>}
          </button>)}
        </nav>
        <p className="helper-text">Action {index + 1} of {doc.pages.length}. Alternative actions remain available for inspection.</p>
        <ActionSection key={current.action_id} doc={doc} page={current} index={index}
          disabled={blocked} observeToken={String(navigation?.session_revision ?? -1)} onVisible={onVisible} />
        <nav className="guided-navigation" aria-label="Previous and next guidance">
          <button className="button button-outline" disabled={blocked || !navigation?.acknowledged || index <= 0}
            onClick={() => move(doc.pages[index - 1].action_id)}>← Back</button>
          <span>{index + 1} / {doc.pages.length}</span>
          <button className="button button-primary" disabled={blocked || !navigation?.acknowledged || index >= doc.pages.length - 1}
            onClick={() => move(doc.pages[index + 1].action_id)}>Next →</button>
        </nav>
      </> : <div className="overview-actions">
        {doc.pages.map((page, pageIndex) => <ActionSection key={page.action_id} doc={doc} page={page} index={pageIndex}
          disabled={blocked || !spec} observeToken={String(navigation?.session_revision ?? -1)} onVisible={onVisible} />)}
      </div>}
      <section className="source-register" aria-label="Procedure-wide requirements and source information">
        <div className="section-heading"><div><p className="eyebrow">Kept available throughout</p><h3>Requirements, relationships and sources</h3></div></div>
        <p className="helper-text">All supplied information remains available here, including facts that apply across actions. Only reviewed supplementary content may be collapsed.</p>
        <div className="source-register-grid"><SourceItems doc={doc} refs={doc.global_items.filter((ref) => ref.kind !== "notice")} /></div>
      </section>
      <div className="exposure-status" role="status">
        {spec ? <><strong>{navigation?.acknowledged ? "Display acknowledgment recorded" : "Awaiting a visible action"}</strong>
          <p>{navigation?.displayed_action_ids.length ?? 0} of {doc.pages.length} actions recorded as displayed. This does not measure comprehension or completion.</p>
          <p className="helper-text">Navigation events: {navigation?.events.length ?? 0}. No navigation event creates a learning reward.</p>
        </> : <><strong>Standard guidance</strong><p>No adaptive exposure acknowledgment or shared policy update is recorded.</p></>}
      </div>
      <details className="guidance-attribution"><summary>Guidance reference</summary>
        <dl><dt>Graph fingerprint</dt><dd>{doc.graph_fingerprint}</dd>
          <dt>Source status</dt><dd>{doc.explanation.source_status}</dd><dt>Assurance</dt><dd>{doc.explanation.assurance}</dd>
          {spec && <><dt>Presentation</dt><dd>{spec.presentation_id}</dd><dt>Exposure</dt><dd>{spec.exposure_id}</dd>
            <dt>Decision</dt><dd>{spec.decision_id}</dd><dt>Selected configuration</dt><dd>{spec.configuration.configuration_id}</dd>
            <dt>Decision context revision</dt><dd>{spec.context_revision}</dd><dt>Current navigation revision</dt><dd>{navigation?.session_revision ?? "Not yet acknowledged"}</dd></>}
        </dl>
      </details>
    </div>}
  </section>;
}
