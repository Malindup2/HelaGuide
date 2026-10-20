import { useState } from "react";
import GuidanceWorkspace from "./guidance/GuidanceWorkspace";
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
  const [search, setSearch] = useState("");
  const [guidanceLocked, setGuidanceLocked] = useState(false);
  const selected = state.procedures.find((item) => item.procedure_id === state.selectedId);
  const active = state.active;
  const enabled = active?.kind === "profile" && active.profile.personalization_enabled;
  const locked = state.busy !== null || state.loading;
  const identityLocked = locked || guidanceLocked || state.pendingMode !== null;
  const visibleProcedures = state.procedures.filter((item) =>
    item.title.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()),
  );

  return (
    <div className="demo-app">
      <a className="skip-link" href="#workspace-main">Skip to workspace</a>
      <header className="app-header">
        <div className="brand"><Mark /><div><strong>HelaGuide</strong><span>Adaptive guidance workspace</span></div></div>
        <div className="header-status">
          <a className="tag" href="/#pipeline-inspector" target="_blank" rel="noreferrer">Pipeline Inspector ↗</a>
          <span className="tag">C4 Research Demo</span>
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
            <div><p className="eyebrow">Guidance, at your pace</p><h1>A clearer next step.</h1>
              <p className="muted">Choose a procedure and the support experience you want to explore.</p></div>
            <span className="tag source-tag">Procedure examples</span>
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
              <section className="panel procedure-panel" aria-labelledby="procedure-title">
                <div className="section-heading">
                  <div><p className="eyebrow">Procedure</p><h2 id="procedure-title">What would you like guidance with?</h2></div>
                  <span className="count-label">{state.procedures.length} registered</span>
                </div>
                <label className="search-field">
                  <span aria-hidden="true">⌕</span><span className="sr-only">Search registered procedures</span>
                  <input type="search" placeholder="Find a procedure…" value={search} onChange={(event) => setSearch(event.target.value)} />
                </label>
                <div className="procedure-grid">
                  {visibleProcedures.map((procedure, index) => (
                    <button key={procedure.procedure_id} disabled={identityLocked}
                      className={"procedure-choice " + (selected?.procedure_id === procedure.procedure_id ? "selected" : "")}
                      aria-pressed={selected?.procedure_id === procedure.procedure_id}
                      onClick={() => workspace.selectProcedure(procedure.procedure_id)}>
                      <span className="procedure-top"><span className="eyebrow">{procedure.synthetic ? "Synthetic scenario" : "Official-source snapshot"}</span><span aria-hidden="true">{selected?.procedure_id === procedure.procedure_id ? "✓" : String(index + 1).padStart(2, "0")}</span></span>
                      <strong>{procedure.title}</strong>
                      <span className="procedure-meta">{procedure.action_ids.length} actions<span aria-hidden="true">↗</span></span>
                    </button>
                  ))}
                </div>
                {visibleProcedures.length === 0 && <p className="empty-state">{state.procedures.length ? "No registered procedures match that search." : "No procedures are registered in this backend."}</p>}
                <p className="helper-text">Search selects registered procedure examples. Free-text government-service intent is not connected here.</p>
              </section>

              <section className="panel entry-panel" aria-labelledby="entry-title">
                <div className="entry-copy">
                  <p className="eyebrow">Guidance experience</p>
                  <h2 id="entry-title">{active ? active.kind === "profile" ? active.profile.display_name : "Guest workspace" : "Choose how to continue"}</h2>
                  <p className="muted">{active
                    ? enabled
                      ? "Your saved context is available to the adaptive engine. Preferences inform the selection; they do not guarantee a particular layout."
                      : "Personalization is off. Future requests use a standard presentation of the supplied procedure."
                    : "Use standard guidance as a guest, or create a demo profile to explore personalized support over time."}</p>
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
                <GuidanceWorkspace
                  key={JSON.stringify([active.session.session_id, selected.procedure_id, active.kind === "profile" ? active.profile.revision : null])}
                  active={active} procedure={selected}
                  disabled={locked || state.pendingMode !== null}
                  onActivityChange={setGuidanceLocked}
                  onSessionUpdate={workspace.updateSession}
                />
              )}
              {!active || !selected ? <p className="helper-text">Select a procedure and open a guest workspace or demo profile to show guidance.</p> : null}

              {active && <div className="panel"><ContextSummary active={active} procedures={state.procedures} /></div>}

              <div className="source-note"><span aria-hidden="true">◇</span><div><strong>Research examples, not official instructions</strong><p>{selected?.disclaimer ?? "The catalogue contains research examples. No government transaction, eligibility decision or application submission occurs here."}</p></div></div>
            </>
          ) : (
            <div className="panel"><h2>Start the C4 development backend</h2><p className="muted">The workspace needs its independent API to load real procedures and saved profiles.</p><code>{API_BASE}</code></div>
          )}
        </main>
      </div>
      <footer className="app-footer"><span>HelaGuide C4 · Independent research prototype</span><span>{state.health ? state.health.storage + " storage · Real backend records" : API_BASE}</span></footer>
    </div>
  );
}
