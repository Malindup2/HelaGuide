import { useState } from "react";
import { useResearchView } from "./app/research";
import WorkspaceGuidance from "./guidance-v2/WorkspaceGuidance";
import ProfileSettings from "./profiles/ProfileSettings";
import { API_BASE } from "./api/client";
import { useWorkspace } from "./app/useWorkspace";
import ContextSummary from "./profiles/ContextSummary";
import ProfileOnboarding from "./profiles/ProfileOnboarding";
import "./shell/shell.css";

function Brand() {
  return <div className="sh-brand"><span className="sh-mark" aria-hidden="true">H</span><strong>HelaGuide</strong></div>;
}

export default function App() {
  const workspace = useWorkspace();
  const { state } = workspace;
  const [research, setResearch] = useResearchView();
  const [guidanceLocked, setGuidanceLocked] = useState(false);
  const selected = state.procedures.find((item) => item.procedure_id === state.selectedId);
  const active = state.active;
  const enabled = active?.kind === "profile" && active.profile.personalization_enabled;
  const locked = state.busy !== null || state.loading;
  const identityLocked = locked || guidanceLocked || state.pendingMode !== null;
  const identityValue = active ? (active.kind === "guest" ? "guest" : active.profile.profile_id) : "";

  const chooseIdentity = (value: string) => {
    if (value === "guest") void workspace.continueGuest();
    else if (value) void workspace.chooseProfile(value);
  };

  return (
    <div className="sh">
      <a className="skip-link" href="#workspace-main">Skip to guidance</a>
      <header className="sh-bar">
        <Brand />
        <div className="sh-bar-right">
          {research && <span className="sh-tag">Research view</span>}
          <span className={"sh-conn " + (state.health ? "on" : "")} role="status">
            <i aria-hidden="true" />{state.loading ? "Connecting" : state.health ? "Connected" : "Backend unavailable"}
          </span>
        </div>
      </header>

      <main id="workspace-main" className="sh-main" tabIndex={-1}>
        {state.error && (
          <div className="sh-alert" role="alert">
            <b>We could not complete that action.</b><p>{state.error}</p>
            {!state.health && <button className="gc-btn gc-btn-quiet" disabled={state.loading} onClick={workspace.retryConnection}>Retry connection</button>}
          </div>
        )}
        {state.notice && <div className="sh-notice" role="status">{state.notice}</div>}
        {state.busy && <div className="sh-busy" role="status">{state.busy}…</div>}
        {state.pendingMode && (
          <div className="sh-alert" role="status">
            <b>A personalization change needs confirmation.</b>
            <p>Retry the original request before switching. Retrying preserves its identity.</p>
            <button className="gc-btn gc-btn-quiet" disabled={locked} onClick={() => void workspace.retryPendingMode()}>Retry original setting request</button>
          </div>
        )}

        {state.loading ? (
          <div className="sh-panel" role="status"><h1 className="sh-h1">Opening your workspace</h1><p className="gc-fine">Connecting and loading procedures and saved profiles.</p>
            <div className="sh-controls" aria-hidden="true">
              <label className="sh-field"><span>Who is this for</span><select disabled><option>Continue as guest</option></select></label>
              <button className="gc-btn gc-btn-quiet" disabled>Create demo profile</button>
            </div></div>
        ) : state.health && state.view === "create" ? (
          <ProfileOnboarding key={state.pendingCreation?.profile_id ?? "new-profile"}
            procedures={state.procedures} pending={state.pendingCreation} busy={locked}
            onSubmit={(draft) => void workspace.submitProfile(draft)}
            onCancel={workspace.closeCreation} onDiscard={workspace.discardPendingCreation} />
        ) : state.health ? (
          <>
            <h1 className="sh-h1">What do you need to do?</h1>
            <section className="sh-controls" aria-label="Choose who this is for and the procedure">
              <label className="sh-field"><span>Who is this for</span>
                <select value={identityValue} disabled={identityLocked}
                  onChange={(event) => chooseIdentity(event.target.value)}>
                  {!active && <option value="">Choose…</option>}
                  <option value="guest">Continue as guest</option>
                  {state.profiles.map((profile) => (
                    <option key={profile.profile_id} value={profile.profile_id}>
                      {profile.display_name}{profile.personalization_enabled ? " (personalised)" : " (standard)"}
                    </option>
                  ))}
                </select></label>
              <button className="gc-btn gc-btn-quiet" disabled={identityLocked || !state.health} onClick={workspace.openCreation}>Create demo profile</button>
              <label className="sh-field"><span>Procedure</span>
                <select id="procedure-select" value={selected?.procedure_id ?? ""} disabled={identityLocked}
                  onChange={(event) => workspace.selectProcedure(event.target.value)}>
                  {!selected && <option value="">Choose a procedure…</option>}
                  {state.procedures.map((procedure) => <option key={procedure.procedure_id} value={procedure.procedure_id}>{procedure.title}</option>)}
                </select></label>
              {active?.kind === "profile" && (
                <button type="button" role="switch" aria-checked={enabled} aria-label="Personalized guidance"
                  className={"sh-switch " + (enabled ? "on" : "")} disabled={identityLocked}
                  onClick={() => void workspace.togglePersonalization()}>
                  <span className="sh-track" aria-hidden="true"><span /></span>
                  <span>Personalised {enabled ? "on" : "off"}</span>
                </button>
              )}
            </section>
            {state.pendingCreation && (
              <button className="sh-linkbtn" disabled={identityLocked} onClick={workspace.openCreation}>Resume unconfirmed profile request</button>
            )}

            {active && selected ? (
              <WorkspaceGuidance
                key={JSON.stringify([active.session.session_id, selected.procedure_id, active.kind === "profile" ? active.profile.revision : null])}
                active={active} procedure={selected}
                disabled={locked || state.pendingMode !== null} research={research}
                onActivityChange={setGuidanceLocked}
              />
            ) : <p className="gc-fine">Choose who this is for and a procedure to see guidance.</p>}

            {active && (
              <details className="sh-settings"><summary>Saved context and settings</summary>
                <ContextSummary active={active} procedures={state.procedures} />
                <ProfileSettings key={active.session.session_id} active={active} procedures={state.procedures} onSession={workspace.updateSession} />
              </details>
            )}
            {research && <p className="gc-fine">{selected?.disclaimer ?? "Research examples, not official instructions."}</p>}
          </>
        ) : (
          <div className="sh-panel"><h1 className="sh-h1">Start the C4 development backend</h1><p className="gc-fine">The workspace needs its API to load real procedures and saved profiles.</p><code>{API_BASE}</code></div>
        )}
      </main>
      <footer className="sh-footer">
        <span>{research ? "HelaGuide C4 · independent research prototype" + (state.health ? " · " + state.health.storage + " storage" : "") : "HelaGuide · demonstration service. No application is made here."}</span>
        <button type="button" className="sh-linkbtn" aria-pressed={research} onClick={() => setResearch(!research)}>Research view: {research ? "on" : "off"}</button>
      </footer>
    </div>
  );
}
