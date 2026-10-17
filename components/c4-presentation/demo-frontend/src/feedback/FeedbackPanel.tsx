import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { API_BASE, errorMessage } from "../api/client";
import type { Navigation, Spec } from "../guidance/types";
import { browserStorage } from "../session/continuity";
import { feedbackApi } from "./api";
import { FeedbackFlow } from "./flow";
import type { CorrectionCode, Rating } from "./types";
const labels: Record<Rating, string> = {
  about_right: "About right", need_more: "I needed more guidance", too_much: "There was too much guidance",
};
const groups = [
  ["presentation_mode", "Navigation style"], ["progressive_disclosure", "Supplementary explanations"],
  ["previous_context_recap", "Previous-context recap"], ["relationship_visual", "Relationship diagram"],
  ["prerequisite_cue", "Prerequisite reminders"],
] as const;
const strategies = { cold_start_baseline: "Cold-start baseline", thompson: "Shared LinTS · Thompson Sampling", forced: "Only one feasible configuration" };

export default function FeedbackPanel({ spec, navigation, disabled, onActivityChange, onPreferencesApplied }: {
  spec: Spec; navigation: Navigation | null; disabled: boolean;
  onActivityChange: (locked: boolean) => void; onPreferencesApplied: () => Promise<void>;
}) {
  const [flow] = useState(() => new FeedbackFlow(feedbackApi, spec, browserStorage(), API_BASE));
  const state = useSyncExternalStore(flow.subscribe, flow.getSnapshot);
  const [rating, setRating] = useState<Rating | null>(null);
  const [reasons, setReasons] = useState<CorrectionCode[]>([]);
  const [skipped, setSkipped] = useState(false);
  const [skipReasons, setSkipReasons] = useState(false);
  const [syncError, setSyncError] = useState<string | null>(null);
  const synced = useRef<string | null>(null);
  const application = state.correction?.application;
  const applicationKey = application ? application.expected_revision + ":" + application.applied_at : null;
  const busy = disabled || state.loading || state.busy;
  const blocked = busy || !state.ready || state.pending !== null;
  const receipt = state.accepted?.receipt;
  const canRate = navigation?.acknowledged && navigation.displayed_action_ids.length > 0;
  const selectedReasons = state.correction?.reasons ?? reasons;
  const canApply = !!state.correction && !application && !!state.options &&
    state.correction.reasons.every((code) => state.options!.choices.some((choice) => choice.code === code && choice.available_for_future));
  useEffect(() => { void flow.initialize(); }, [flow]);
  useEffect(() => {
    onActivityChange(state.loading || state.busy || state.pending !== null);
    return () => onActivityChange(false);
  }, [onActivityChange, state.loading, state.busy, state.pending]);
  useEffect(() => {
    if (!applicationKey || synced.current === applicationKey) return;
    synced.current = applicationKey;
    void onPreferencesApplied().catch((error) => setSyncError(errorMessage(error) + " Reopen your profile to load its current settings."));
  }, [applicationKey, onPreferencesApplied]);

  function chooseReason(code: CorrectionCode, dimension: string) {
    const sameDimension = state.options?.choices.filter((option) => option.dimension === dimension).map((option) => option.code) ?? [];
    setReasons((old) => old.includes(code) ? old.filter((item) => item !== code) : [...old.filter((item) => !sameDimension.includes(item)), code]);
  }
  return <section className="feedback-panel" aria-labelledby="support-fit-title">
    <div className="feedback-heading"><div><p className="eyebrow">Help shape future support</p>
      <h3 id="support-fit-title">Was this the right amount of guidance for what you needed?</h3></div>
      <span className="tag">{receipt ? receipt.feedback.origin === "simulation" ? "Simulation feedback" : "Participant-report mode" :
        state.policy?.feedback_mode === "simulation" ? "Simulation mode" : state.policy?.feedback_mode === "participant" ? "Participant-report mode" : "Loading feedback records"}</span></div>
    <p className="helper-text">Optional. Rate the presentation you viewed, not whether you completed the procedure. No response produces no reward.</p>
    {state.error && <div className="alert alert-error" role="alert"><p>{state.error}</p></div>}
    {syncError && <div className="alert" role="alert"><p>{syncError}</p></div>}
    {state.notice && <p className="helper-text" role="status">{state.notice}</p>}
    <div className="feedback-tools"><button className="text-button" disabled={busy} onClick={() => void flow.refresh()}>Check saved records</button></div>
    {state.pending && <div className="feedback-pending" role="status">
      <strong>{state.pending.kind === "rating" ? "Rating" : state.pending.kind === "correction" ? "Diagnostic reasons" : "Preference application"} awaiting confirmation</strong>
      <p>Retrying sends the original request unchanged. A lost response does not mean it failed to save.</p>
      <button className="button button-outline" disabled={busy || !state.ready} onClick={() => void flow.retry()}>Retry original request</button>
      <button className="text-button" disabled={busy} onClick={() => flow.stopRetrying()}>Stop retrying locally</button>
    </div>}
    {!receipt && !skipped && <form onSubmit={(event) => {
      event.preventDefault(); if (rating) void flow.rate(rating, navigation);
    }}>
      {!canRate && <p className="feedback-wait">View a procedural action first. Its display acknowledgment must be confirmed before feedback can be accepted.</p>}
      <fieldset className="rating-choices" disabled={blocked || !canRate}><legend className="sr-only">Amount of presentation support</legend>
        {(Object.keys(labels) as Rating[]).map((value) => <label key={value}
          className={"rating-choice " + ((state.pending?.kind === "rating" ? state.pending.request.rating : rating) === value ? "selected" : "")}>
          <input type="radio" name="support-fit" value={value}
            checked={(state.pending?.kind === "rating" ? state.pending.request.rating : rating) === value}
            onChange={() => setRating(value)} /><span>{labels[value]}</span>
        </label>)}
      </fieldset>
      <div className="feedback-actions"><button className="button button-primary" disabled={blocked || !canRate || !rating}>
        {state.busy ? "Saving…" : "Submit rating"}</button>
        <button type="button" className="text-button" disabled={busy || state.pending !== null} onClick={() => setSkipped(true)}>Not now</button></div>
    </form>}
    {!receipt && skipped && <p className="helper-text">You have not submitted a rating here. <button className="text-button" onClick={() => setSkipped(false)}>Give feedback</button></p>}
    {receipt && <div className="feedback-receipt" role="status">
      <strong>Saved: {labels[receipt.feedback.rating]}</strong>
      <p>Accepted reward: {receipt.reward}. This feedback was attributed to the original displayed configuration and decision.</p>
      {receipt.feedback.origin === "simulation" && <p className="helper-text">This is a simulation/demo record, not participant research evidence.</p>}
      <div className="learning-revisions">
        <div><span>Decision used model revision</span><strong>{receipt.selection_posterior_revision}</strong></div>
        <span aria-hidden="true">→</span>
        <div><span>Feedback accepted at revision</span><strong>{receipt.resulting_posterior_revision}</strong></div>
        <div><span>Latest confirmed shared revision</span><strong>{state.policy && state.policy.posterior_revision >= receipt.resulting_posterior_revision ? state.policy.posterior_revision : "Awaiting read-back"}</strong></div>
      </div>
      {state.before && state.policy && state.before.policy_run_id === state.policy.policy_run_id &&
        state.before.posterior_revision < receipt.resulting_posterior_revision &&
        state.before.posterior_fingerprint !== state.policy.posterior_fingerprint &&
        <p className="learning-confirmed">Shared posterior change confirmed against the observed pre-submission state.</p>}
      <p className="helper-text">Request fresh guidance above for the next selection. Its configuration may stay the same; the decision's model revision is the evidence of updated-model use.</p>
    </div>}
    {receipt && receipt.feedback.rating !== "about_right" && <>
      <div className="correction-heading"><h4>{receipt.feedback.rating === "need_more" ? "What support would have helped?" : "What would have felt lighter?"}</h4>
        <p className="helper-text">Optional diagnostic reasons. Saving them is not another reward and does not change your preferences.</p></div>
      {!state.correction && skipReasons ? <button className="text-button" disabled={busy} onClick={() => setSkipReasons(false)}>Add optional reasons</button> :
        <form onSubmit={(event) => { event.preventDefault(); void flow.record(reasons); }}>
          <div className="correction-groups">{groups.map(([dimension, title]) => <fieldset key={dimension}
            disabled={blocked || !!state.correction} className="correction-group">
            <legend>{title}</legend>
            {state.options?.choices.filter((choice) => choice.dimension === dimension).map((choice) => <label key={choice.code}
              className={"correction-choice " + (selectedReasons.includes(choice.code) ? "selected" : "")}>
              <input type="checkbox" checked={selectedReasons.includes(choice.code)} onChange={() => chooseReason(choice.code, dimension)} />
              <span><strong>{choice.label}</strong>
                {choice.selected_in_original && <small>Already enabled in the original configuration</small>}
                {!choice.available_for_future && <small>Can be recorded as a reason; currently unavailable for future use. {choice.unavailable_reason}</small>}
              </span>
            </label>)}
          </fieldset>)}</div>
          {!state.correction && <div className="feedback-actions">
            <button className="button button-outline" disabled={blocked || reasons.length === 0}>Save reasons only</button>
            <button type="button" className="text-button" disabled={busy || state.pending !== null} onClick={() => setSkipReasons(true)}>Skip reasons</button>
          </div>}
        </form>}
      {state.correction && <div className="preference-application">
        {application ? <><strong>Future soft preferences applied</strong><p>Context revision {application.before.revision} → {application.after.revision}.
          Explicit locks, accessibility settings and the original feedback attribution were preserved.</p>
          <p className="helper-text">Your current presentation remains its original configuration. Request fresh guidance to use the updated preferences.</p></> :
          <><strong>Reasons saved as diagnostics</strong><p>Use them as soft preferences for future guidance only if you choose to.</p>
            <button className="button button-primary" disabled={blocked || !canApply} onClick={() => void flow.apply()}>Apply these future preferences</button>
            {!canApply && <p className="helper-text">One or more choices are currently unavailable. The backend also checks whether all choices are feasible together.</p>}
            <p className="helper-text">This does not lock a layout, change your familiarity or create another learning reward.</p></>}
      </div>}
    </>}
    {state.decision && <details className="feedback-diagnostics"><summary>Learning reference</summary><dl>
      <dt>This decision's strategy</dt><dd>{strategies[state.decision.selection_mode]}</dd>
      <dt>This decision's model revision</dt><dd>{state.decision.posterior_revision}</dd>
      <dt>Shared feature dimension</dt><dd>{state.decision.feature_dimension}</dd>
      <dt>Decision</dt><dd>{spec.decision_id}</dd>
      <dt>Exposure</dt><dd>{spec.exposure_id}</dd>
      {state.before && <><dt>Posterior fingerprint observed before submission</dt><dd>{state.before.posterior_fingerprint}</dd></>}
      {state.policy && <><dt>Current posterior fingerprint</dt><dd>{state.policy.posterior_fingerprint}</dd></>}
    </dl><p className="helper-text">These are stored backend records. Current shared revisions can also include feedback from other sessions.</p></details>}
  </section>;
}
