import { useEffect, useState, useSyncExternalStore } from "react";
import { API_BASE } from "../api/client";
import { InspectorController, inspectorTarget } from "./controller";
import { TraceView, ConfigurationLabel } from "./TraceView";
import "./inspector.css";

export default function PipelineInspector() {
  const [controller] = useState(() => new InspectorController(undefined, hash => window.history.replaceState(null, "", hash)));
  const state = useSyncExternalStore(controller.subscribe, controller.snapshot, controller.snapshot);
  const [sessionInput, setSessionInput] = useState(() => inspectorTarget(window.location.hash).session);
  useEffect(() => {
    const target = inspectorTarget(window.location.hash);
    void controller.profiles();
    if (target.session) void controller.open(target.session, target.exposure);
    return () => controller.dispose();
  }, [controller]);
  return <div className="pipeline-inspector">
    <a className="skip-link" href="#inspector-main" onClick={e => { e.preventDefault(); document.getElementById("inspector-main")?.focus(); }}>Skip to Inspector</a>
    <header className="inspector-header"><div><p className="eyebrow">HelaGuide · C4 research tools</p><h1>Pipeline Inspector</h1><p>Read-only inspection of saved adaptive decisions</p></div>
      <a className="button button-outline" href="/" target="_blank" rel="noreferrer">Open citizen workspace ↗</a></header>
    <main id="inspector-main" tabIndex={-1}>
      <div className="inspector-notice"><strong>Research view · GET requests only</strong><p>Opening or refreshing this page does not select guidance, record display, submit feedback or train the model. Demo profiles are local records, not authenticated accounts.</p><code>{API_BASE}</code></div>
      <section className="inspector-panel" aria-labelledby="inspect-choose"><h2 id="inspect-choose">Choose saved records</h2>
        <div className="inspector-controls"><label>Saved demo profile<select value={state.profiles.some(p => p.session_id === state.session) ? state.session : ""} onChange={e => { if (e.target.value) { setSessionInput(e.target.value); void controller.open(e.target.value); } }}>
          <option value="">Select a profile…</option>{state.profiles.map(p => <option key={p.profile_id} value={p.session_id}>{p.display_name} · {p.personalization_enabled ? "Adaptive routing" : "Standard routing"} · {p.profile_id.slice(-6)}</option>)}</select></label>
          <button className="button button-outline" onClick={() => void controller.profiles()}>Reload profiles</button></div>
        <form className="inspector-controls" onSubmit={e => { e.preventDefault(); void controller.open(sessionInput.trim()); }}><label>Or inspect an existing session ID<input value={sessionInput} onChange={e => setSessionInput(e.target.value)} placeholder="guest:…" autoComplete="off" spellCheck={false} /></label><button className="button button-primary" type="submit">Load saved history</button></form>
        <p>Guest and other existing sessions can be entered directly. No new session is created here.</p>
        {state.session && <p>Inspecting session: <code>{state.session}</code></p>}
      </section>
      {state.loading && <p role="status" className="inspector-notice">Loading {state.loading}…</p>}
      {state.error && <div role="alert" className="alert alert-error"><strong>Could not load these records.</strong><p>{state.error}</p><p>For a missing record, reload history or choose another session. If C4 reports unavailable or incompatible state, check the backend terminal; this page will not repair or reset it.</p>{state.session && <button className="button button-outline" onClick={() => void controller.refresh()}>Retry saved history</button>}</div>}
      {state.index && <section className="inspector-panel" aria-labelledby="inspect-history"><h2 id="inspect-history">Saved adaptive presentations</h2>
        <p>Current request routing: <strong>{state.index.current_request_routing}</strong>. This is separate from historical adaptive decisions.</p>
        <p>{state.index.explanation}</p>
        {state.index.presentations.length === 0 ? <p className="notice">No saved adaptive presentations for this session. Request adaptive guidance in the citizen workspace to create one. Standard guidance has no persisted policy or learning trace.</p> : <>
          <label>Presentation<select value={state.exposure} onChange={e => void controller.select(e.target.value)}>{state.index.presentations.map((p, i) => <option key={p.exposure_id} value={p.exposure_id}>{i + 1}. {new Date(p.offered_at).toLocaleString()} · revision {p.selection_posterior_revision} · {p.acknowledged ? "display acknowledged" : "not acknowledged"} · {p.feedback_accepted ? "feedback accepted" : "no accepted feedback"} · {p.exposure_id.slice(-8)}</option>)}</select></label>
          {state.index.presentations.filter(p => p.exposure_id === state.exposure).map(p => <p key={p.exposure_id}><ConfigurationLabel value={p.configuration} /></p>)}
        </>}
        <button className="button button-outline" disabled={state.loading !== null} onClick={() => void controller.refresh()}>Refresh saved records</button>
        <p className="helper-text">The address preserves session and presentation selection across a browser refresh. Refresh reads current records; it does not replay any action.</p>
      </section>}
      {state.trace && <TraceView key={state.trace.records.presentation.exposure_id} trace={state.trace} />}
      {!state.session && <p className="inspector-empty">Select a saved profile or enter an existing session to inspect its pipeline.</p>}
    </main>
    <footer className="inspector-footer">C4 Pipeline Inspector · Local research prototype · No polling or background learning</footer>
  </div>;
}
