import { useEffect, useState } from 'react';
import { API_BASE } from '../api/client';
import type { ActiveIdentity, ProcedureSummary } from '../api/types';
import { useWorkspace } from '../app/useWorkspace';
import { useResearchView } from '../app/research';
import ProfileOnboarding from '../profiles/ProfileOnboarding';
import { GuidanceError, guidanceApi } from './api';
import { guidanceIdentity } from './identity';
import { reasonText } from './model';
import { useJourney } from './useJourney';
import { useApiStatus } from './useApiStatus';
import GuidanceCard from './card/GuidanceCard';
import ProfileContext from './ProfileContext';
import { CompareSheet, EvidenceSheet, InspectorSheet, PreviewChooser } from './Research';
import { MenuIcon } from './ui';
import type { ApiStatus, Availability, Configuration } from './types';
import './citizen.css';

const split = (title: string): [string, string] => { const i = title.indexOf(': '); return i < 0 ? [title, ''] : [title.slice(0, i), title.slice(i + 2)]; };

function friendly(e: GuidanceError): string {
  switch (e.code) {
    case 'infeasible_configuration': return `That combination is not available. ${e.reasons.map(reasonText).join('; ')}`;
    case 'research_preview_disabled': return 'Research previews are turned off on this server.';
    case 'guidance_api_disabled': return 'The guidance service is turned off on this server.';
    case 'context_revision_changed': return 'Your saved settings changed. Request guidance again.';
    case 'unreachable': return e.message;
    default: return e.message;
  }
}

function Stage({ active, procedure, status, research, onSession }: { active: ActiveIdentity; procedure: ProcedureSummary; status: ApiStatus | null; research: boolean; onSession: Parameters<typeof ProfileContext>[0]['onSession'] }) {
  const sessionId = active.session.session_id, journey = useJourney({ sessionId, procedureId: procedure.procedure_id, status });
  const [compare, setCompare] = useState(false), [inspect, setInspect] = useState(false), [evidence, setEvidence] = useState(false), [fetched, setFetched] = useState<Availability | null>(null);
  const personalised = active.kind === 'profile' && active.profile.personalization_enabled;
  const { response } = journey, previewsOn = research && !!status?.research_previews_enabled;
  useEffect(() => {
    if (!previewsOn || response) return;
    let live = true;
    guidanceApi.availability(procedure.procedure_id, sessionId).then(a => { if (live) setFetched(a); }).catch(() => undefined);
    return () => { live = false; };
  }, [previewsOn, response, procedure.procedure_id, sessionId]);
  const availability = response?.availability ?? fetched;
  const lastConfig: Configuration | null = response && response.selection.kind !== 'standard' ? response.document.configuration : null;

  return <section className="cz-stage" aria-label="Guidance">
    <div className="cz-stagebar">
      <p className="cz-who">{active.kind === 'guest' ? 'Guest · standard guidance' : `${active.profile.display_name} · personalisation ${personalised ? 'on' : 'off'}`}</p>
      <button type="button" className="cz-btn" disabled={journey.busy} onClick={() => void journey.start({ kind: personalised ? 'personalized' : 'standard' })}>
        {journey.busy ? 'Preparing…' : response ? 'Request fresh guidance' : 'Show guidance'}</button>
    </div>
    {active.kind === 'profile' && <ProfileContext active={active} procedure={procedure} onSession={onSession} />}
    {journey.policyUnavailable && <div className="cz-notice" role="status">
      <p><b>Personalised selection is not available yet.</b> You can read the standard guidance for this procedure in the meantime.</p>
      {research && <p className="cz-fine">The revised selection model is not enabled for this runtime ({status?.encoder_status?.replaceAll('_', ' ') ?? 'status unknown'}). No personalised choice is shown or simulated.</p>}
      <button type="button" className="cz-btn cz-btn-quiet" onClick={() => void journey.start({ kind: 'standard' })}>Show standard guidance</button></div>}
    {journey.error && <p className="cz-alert" role="alert">{friendly(journey.error)}</p>}
    {!response && !journey.busy && !journey.policyUnavailable && !journey.error && <p className="cz-fine">Press “Show guidance” for {split(procedure.title)[0].toLowerCase()}. Viewing guidance never marks anything as done.</p>}
    {response && <GuidanceCard response={response} emit={journey.emit} adjust={c => void journey.adjust(c)} rate={journey.rate} busy={journey.busy} research={research} />}
    {previewsOn && <section className="cz-research" aria-label="Research view">
      <h2>Research view</h2>
      {response && <p className="cz-fine">Selection: {response.selection.label} · scoring {response.selection.scoring_status.replaceAll('_', ' ')} · learning eligible: {response.selection.learning_eligible ? 'yes' : 'no'} · personalised selection available: {status?.personalized_selection_available ? 'yes' : 'no'}.</p>}
      {status?.personalized_selection_available && <p className="cz-fine"><a href={`${API_BASE}/workspace/guidance/research/learning/report.html`} target="_blank" rel="noreferrer">Synthetic learning report and checkpoint comparisons</a></p>}
      <PreviewChooser availability={availability} busy={journey.busy} onStart={c => void journey.start({ kind: 'preview', configuration: c })} />
      <div className="cz-fbrow">
        <button type="button" className="cz-chip" disabled={!response || !response.controls.research_inspection} onClick={() => setInspect(true)}>Open inspector</button>
        <button type="button" className="cz-chip" onClick={() => setCompare(true)}>Compare standard and preview</button>
        <button type="button" className="cz-chip" onClick={() => setEvidence(true)}>Learning evidence</button></div>
    </section>}
    {inspect && response && journey.token() && <InspectorSheet journeyId={response.journey_id} token={journey.token()!} onClose={() => setInspect(false)} />}
    {evidence && <EvidenceSheet onClose={() => setEvidence(false)} />}
    {compare && <CompareSheet sessionId={sessionId} procedureId={procedure.procedure_id} previewConfig={lastConfig} onClose={() => setCompare(false)} />}
  </section>;
}

export default function Workspace() {
  const workspace = useWorkspace(guidanceIdentity), { state } = workspace, { status, error: statusError } = useApiStatus();
  const [research, setResearch] = useResearchView(), [menu, setMenu] = useState(false);
  const active = state.active, selected = state.procedures.find(p => p.procedure_id === state.selectedId);
  const personalised = active?.kind === 'profile' && active.profile.personalization_enabled;
  const busy = state.busy !== null || state.loading || state.pendingMode !== null;
  const official = state.procedures.filter(p => !p.synthetic), fictional = state.procedures.filter(p => p.synthetic);

  const procedureButton = (p: ProcedureSummary) => { const [first, rest] = split(p.title), fiction = first === 'Synthetic demo' && !!rest, main = fiction ? rest.charAt(0).toUpperCase() + rest.slice(1) : first, sub = fiction ? 'Fictional example' : rest;
    return <button type="button" key={p.procedure_id} className="cz-pick" aria-pressed={p.procedure_id === state.selectedId} disabled={busy}
      onClick={() => { workspace.selectProcedure(p.procedure_id); setMenu(false); }}><span>{main}</span>{sub && <small>{sub}</small>}</button>; };

  return <div className="cz-app">
    <a className="skip-link" href="#workspace-main">Skip to guidance</a>
    <header className="cz-bar">
      <div className="cz-brand"><span className="cz-mark-logo" aria-hidden="true">H</span><strong>HelaGuide</strong></div>
      <button type="button" className="cz-chip cz-menubtn" aria-expanded={menu} aria-controls="cz-side" onClick={() => setMenu(!menu)}><MenuIcon />Person and procedure</button>
      <span className={'cz-conn' + (state.health ? ' on' : '')} role="status"><i aria-hidden="true" />{state.loading ? 'Connecting' : state.health ? 'Connected' : 'Backend unavailable'}</span>
    </header>
    <div className="cz-shell">
      <aside id="cz-side" className="cz-side" data-open={menu} aria-label="Person and procedure">
        <section aria-labelledby="cz-who-h"><h2 id="cz-who-h">Who is this for</h2>
          <button type="button" className="cz-pick" aria-pressed={active?.kind === 'guest'} disabled={busy || !state.health} onClick={() => { void workspace.continueGuest(); }}>
            <span>Continue as guest</span><small>Standard guidance</small></button>
          {state.profiles.map(p => <button type="button" key={p.profile_id} className="cz-pick" disabled={busy} aria-pressed={active?.kind === 'profile' && active.profile.profile_id === p.profile_id}
            onClick={() => { void workspace.chooseProfile(p.profile_id); }}><span>{p.display_name}</span><small>Saved profile · personalisation {p.personalization_enabled ? 'on' : 'off'}</small></button>)}
          <button type="button" className="cz-link" disabled={busy || !state.health} onClick={workspace.openCreation}>Create demo profile</button>
          {state.pendingCreation && state.view !== 'create' && <button type="button" className="cz-link" disabled={busy} onClick={workspace.openCreation}>Resume unconfirmed profile request</button>}
          {active?.kind === 'profile' && <button type="button" role="switch" aria-checked={personalised} className={'cz-switch' + (personalised ? ' on' : '')} disabled={busy}
            onClick={() => void workspace.togglePersonalization()}><span className="cz-track" aria-hidden="true"><span /></span><span>Personalisation {personalised ? 'on' : 'off'}</span></button>}
        </section>
        <section aria-labelledby="cz-proc-h"><h2 id="cz-proc-h">Procedure</h2>
          <p className="cz-group">Official-source procedures</p>{official.map(procedureButton)}
          <p className="cz-group">Research examples (fictional)</p>{fictional.map(procedureButton)}
        </section>
        <p className="cz-fine">Demo profiles are saved for this demonstration only. They are not accounts or verified identities.</p>
      </aside>
      <main id="workspace-main" className="cz-main" tabIndex={-1}>
        <h1 className="sr-only">Procedure guidance</h1>
        {(state.error || statusError) && <div className="cz-alert" role="alert"><b>We could not complete that action.</b><p>{state.error ?? statusError}</p>
          {!state.health && <button type="button" className="cz-btn cz-btn-quiet" disabled={state.loading} onClick={workspace.retryConnection}>Retry connection</button>}</div>}
        {state.notice && <p className="cz-fine" role="status">{state.notice}</p>}
        {state.busy && <p className="cz-fine" role="status">{state.busy}…</p>}
        {state.pendingMode && <div className="cz-alert" role="status"><b>A personalisation change needs confirmation.</b>
          <button type="button" className="cz-btn cz-btn-quiet" disabled={state.busy !== null} onClick={() => void workspace.retryPendingMode()}>Retry original setting request</button></div>}
        {state.loading ? <p role="status" className="cz-fine">Opening your workspace…</p>
          : state.health && state.view === 'create' ? <ProfileOnboarding key={state.pendingCreation?.profile_id ?? 'new-profile'} procedures={state.procedures} pending={state.pendingCreation} busy={busy}
            onSubmit={draft => void workspace.submitProfile(draft)} onCancel={workspace.closeCreation} onDiscard={workspace.discardPendingCreation} />
          : state.health ? (active && selected
            ? <Stage key={`${active.session.session_id}:${selected.procedure_id}:${active.kind === 'profile' ? active.profile.revision : ''}`} active={active} procedure={selected} status={status} research={research} onSession={workspace.updateSession} />
            : <div className="cz-empty"><h2>What do you need to do?</h2><p>Choose who this is for and a procedure. Guests receive standard guidance; saved profiles keep their settings.</p>
              {!active && <button type="button" className="cz-btn" disabled={busy} onClick={() => { void workspace.continueGuest(); }}>Continue as guest</button>}</div>)
          : <div className="cz-empty"><h2>Start the C4 backend</h2><p>The workspace needs its API to load real procedures and saved profiles.</p><code>{API_BASE}</code></div>}
      </main>
    </div>
    <footer className="cz-foot"><span>{research ? 'HelaGuide C4 · independent research prototype' : 'HelaGuide · demonstration service. No application is made here.'}</span>
      <button type="button" className="cz-link" aria-pressed={research} onClick={() => setResearch(!research)}>Research view: {research ? 'on' : 'off'}</button></footer>
  </div>;
}
