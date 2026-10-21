import { useState } from "react";
import { useResearchView } from "./app/research";
import WorkspaceGuidance from "./guidance-v2/WorkspaceGuidance";
import ProfileSettings from "./profiles/ProfileSettings";
import { API_BASE } from "./api/client";
import { useWorkspace } from "./app/useWorkspace";
import ContextSummary from "./profiles/ContextSummary";
import ProfileOnboarding from "./profiles/ProfileOnboarding";

function Mark({ small = false }: { small?: boolean }) {
  return <span className={small ? "brand-mark brand-mark-small" : "brand-mark"} aria-hidden="true">H</span>;
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

  return (
    <div className="demo-app">
      <a className="skip-link" href="#workspace-main">Skip to workspace</a>
      <header className="app-header">
        <div className="brand"><Mark /><div><strong>HelaGuide</strong><span>Clear procedure guidance</span></div></div>
        <div className="header-status">
          {research && <a className="tag" href="#c4-v2-inspector">Research Inspector ↗</a>}
          {research && <span className="tag">C4 Research Demo</span>}
          <span className={"connection " + (state.health ? "connected" : "")}>
            <i aria-hidden="true" />
            {state.loading ? "Connecting" : state.health ? "Backend connected" : "Backend unavailable"}
          </span>
        </div>
      </header>

      <div className="workspace-layout">
        <aside className="identity-sidebar" aria-label="Guest and demonstration profiles">
          <div className="sidebar-heading"><span className="eyebrow">Your workspace</span><span className="sidebar-index">01</span></div>
          <button className={"identity-choice " + (active?.kind === "guest" ? "active" : "")}
            aria-pressed={active?.kind === "guest"} disabled={identityLocked || !state.health}
            onClick={() => void workspace.continueGuest()}>
            <span className="identity-avatar" aria-hidden="true">G</span>
            <span><strong>Continue as guest</strong><small>Standard guidance · no profile</small></span>
            <span className="choice-arrow" aria-hidden="true">{active?.kind === "guest" ? "✓" : "↗"}</span>
          </button>

          <div className="saved-heading">
            <span className="eyebrow">Saved demo profiles</span>
            <button className="text-button" disabled={locked || !state.health}
              onClick={() => void workspace.refreshProfiles()}>Refresh</button>
          </div>
          <div className="saved-profiles">
            {!state.loading && state.profiles.length === 0 && (
              <p className="sidebar-empty">No saved profiles yet. Create one to explore returning-user personalization.</p>
            )}
            {state.profiles.map((profile) => {
              const isActive = active?.kind === "profile" && active.profile.profile_id === profile.profile_id;
              return (
                <button key={profile.profile_id}
                  className={"profile-choice " + (isActive ? "active" : "")}
                  disabled={identityLocked} aria-pressed={isActive}
                  onClick={() => void workspace.chooseProfile(profile.profile_id)}>
                  <span className="identity-avatar" aria-hidden="true">{profile.display_name[0].toUpperCase()}</span>
                  <span className="profile-choice-copy">
                    <strong>{profile.display_name}</strong>
                    <small>{profile.personalization_enabled ? "Personalization on" : "Standard guidance"} · {profile.profile_id.slice(-6)}</small>
                  </span>
                  {isActive && <span aria-hidden="true">✓</span>}
                </button>
              );
            })}
          </div>
          <button className="button button-outline new-profile" disabled={identityLocked || !state.health}
            onClick={workspace.openCreation}>
            <span aria-hidden="true">+</span> Create demo profile
          </button>
          {state.pendingCreation && state.view !== "create" && (
            <button className="text-button pending-link" disabled={identityLocked} onClick={workspace.openCreation}>
              Resume unconfirmed profile request
            </button>
          )}
          <div className="sidebar-footnote">
            <span className="eyebrow">Local demonstration</span>
            <p>Demo profiles restore saved context. They are not secure accounts or verified identities.</p>
          </div>
        </aside>

        <main id="workspace-main" className="workspace-main" tabIndex={-1}>
          <div className="workspace-heading">
            <div><p className="eyebrow">Procedure guidance</p><h1>What do you need to do?</h1>
              <p className="muted">Choose a procedure to see what to prepare and what to do next.</p></div>
          </div>

          {state.error && (
            <div className="alert alert-error" role="alert">
              <strong>We could not complete that action.</strong><p>{state.error}</p>
              {!state.health && <button className="button button-outline" disabled={state.loading} onClick={workspace.retryConnection}>Retry connection</button>}
            </div>
          )}
          {state.notice && <div className="notice" role="status">{state.notice}</div>}
          {state.busy && <div className="busy-status" role="status"><i className="status-pulse" aria-hidden="true" />{state.busy}…</div>}
          {state.pendingMode && (
            <div className="alert" role="status">
              <strong>A personalization change needs confirmation.</strong>
              <p>Retry the original request before switching workspaces. Retrying preserves its identity.</p>
              <button className="button button-outline" disabled={locked} onClick={() => void workspace.retryPendingMode()}>Retry original setting request</button>
            </div>
          )}

          {state.loading ? (
            <div className="panel loading-panel" role="status"><div className="skeleton" /><h2>Opening your workspace</h2><p className="muted">Connecting to C4 and retrieving available procedures and saved profiles.</p></div>
          ) : state.health && state.view === "create" ? (
            <ProfileOnboarding key={state.pendingCreation?.profile_id ?? "new-profile"}
              procedures={state.procedures} pending={state.pendingCreation} busy={locked}
              onSubmit={(draft) => void workspace.submitProfile(draft)}
              onCancel={workspace.closeCreation} onDiscard={workspace.discardPendingCreation} />
          ) : state.health ? (
            <>
              <section className="panel procedure-panel picker" aria-label="Procedure">
                <div className="picker-row">
                  <label htmlFor="procedure-select" className="field-label">Procedure</label>
                  <select id="procedure-select" value={selected?.procedure_id ?? ""} disabled={identityLocked}
                    onChange={(event) => workspace.selectProcedure(event.target.value)}>
                    {!selected && <option value="">Choose a procedure…</option>}
                    {state.procedures.map((procedure) => <option key={procedure.procedure_id} value={procedure.procedure_id}>{procedure.title}</option>)}
                  </select>
                  {selected && <p className="picker-meta"><span className="v2-chip">{selected.synthetic ? "Practice example" : "Information snapshot"}</span><span>{selected.action_ids.length} actions</span></p>}
                </div>
                {state.procedures.length === 0 && <p className="empty-state">No procedures are registered in this backend.</p>}
              </section>

              <section className="panel entry-panel" aria-labelledby="entry-title">
                <div className="entry-copy">
                  <p className="eyebrow">Who is this for</p>
                  <h2 id="entry-title">{active ? active.kind === "profile" ? active.profile.display_name : "Guest workspace" : "Choose how to continue"}</h2>
                  <p className="muted">{active
                    ? enabled
                      ? "Your saved profile informs how guidance is laid out. It does not guarantee a particular layout."
                      : "Personalization is off. Guidance uses the standard layout."
                    : "Use standard guidance as a guest, or create a demo profile to try a personalised layout."}</p>
                </div>
                {active?.kind === "profile" ? (
                  <div className="personalization-control">
                    <span className="field-label">Personalization</span>
                    <button type="button" role="switch" aria-checked={enabled}
                      aria-label="Personalized guidance"
                      className={"switch-button " + (enabled ? "on" : "")}
                      disabled={identityLocked}
                      onClick={() => void workspace.togglePersonalization()}>
                      <span className="switch-track" aria-hidden="true"><span /></span>
                      <strong>{enabled ? "On" : "Off"}</strong>
                    </button>
                    <span className="helper-text">Applies to future guidance requests.</span>
                  </div>
                ) : !active ? (
                  <div className="button-stack">
                    <button className="button button-primary" disabled={identityLocked} onClick={() => void workspace.continueGuest()}>Continue as guest <span aria-hidden="true">↗</span></button>
                    <button className="button button-outline" disabled={identityLocked} onClick={workspace.openCreation}>Create demo profile</button>
                  </div>
                ) : <span className="mode-badge">Standard guidance</span>}
              </section>

              {active && selected && (
                <WorkspaceGuidance
                  key={JSON.stringify([active.session.session_id, selected.procedure_id, active.kind === "profile" ? active.profile.revision : null])}
                  active={active} procedure={selected}
                  disabled={locked || state.pendingMode !== null} research={research}
                  onActivityChange={setGuidanceLocked}
                />
              )}
              {!active || !selected ? <p className="helper-text">Choose a procedure, then continue as a guest or open a demo profile.</p> : null}

              {active && <div className="panel"><ContextSummary active={active} procedures={state.procedures} /><ProfileSettings key={active.session.session_id} active={active} procedures={state.procedures} onSession={workspace.updateSession}/></div>}

              {research && <div className="source-note"><span aria-hidden="true">◇</span><div><strong>Research examples, not official instructions</strong><p>{selected?.disclaimer ?? "The catalogue contains research examples. No government transaction, eligibility decision or application submission occurs here."}</p></div></div>}
            </>
          ) : (
            <div className="panel"><h2>Start the C4 development backend</h2><p className="muted">The workspace needs its independent API to load real procedures and saved profiles.</p><code>{API_BASE}</code></div>
          )}
        </main>
      </div>
      <footer className="app-footer"><span>{research ? "HelaGuide C4 · Independent research prototype" : "HelaGuide · Demonstration service. No application is made here."}</span>
        <span>{research && (state.health ? state.health.storage + " storage · Real backend records" : API_BASE)}
          <button type="button" className="text-button" aria-pressed={research} onClick={() => setResearch(!research)}>Research view: {research ? "on" : "off"}</button></span></footer>
    </div>
  );
}
