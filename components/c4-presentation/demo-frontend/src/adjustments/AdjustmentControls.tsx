import { useEffect, useRef, useState } from "react";
import type { Configuration } from "../guidance/types";
import { api } from "../api/client";
import type { AdjustmentFlow, FlowState } from "./flow";
import type { ViewRating } from "./api";
import "./adjustments.css";

const dimensions = [
  ["presentation_mode", "Navigation", [["OVERVIEW", "Overview"], ["GUIDED", "Guided"]]],
  ["relationship_visual", "Relationship diagram", [["NONE", "Hide diagram"], ["BRANCH_MAP", "Branch map"], ["DEPENDENCY_MAP", "Dependency map"], ["PARALLEL_MAP", "Parallel map"]]],
  ["progressive_disclosure", "Supplementary source context", [[false, "Keep expanded"], [true, "Collapse optional context"]]],
  ["previous_context_recap", "Previous-context recap", [[false, "Hide recap"], [true, "Show recap"]]],
  ["prerequisite_cue", "Prerequisite reminders", [[false, "Hide reminders"], [true, "Show reminders"]]],
] as const;
export function AdjustmentControls({ flow, state, disabled, focus, onPreferencesApplied, onActivityChange }: {
  flow: AdjustmentFlow; state: FlowState; disabled: boolean; focus: string; onPreferencesApplied: () => Promise<void>; onActivityChange?: (busy: boolean) => void;
}) {
  const value = state.value;
  const [draft, setDraft] = useState<Configuration | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const synced = useRef(false);
  useEffect(() => { onActivityChange?.(saving); return () => onActivityChange?.(false); }, [saving, onActivityChange]);
  useEffect(() => {
    if (state.preferencesSaved && !synced.current) { synced.current = true; void onPreferencesApplied().catch(e => setSaveError(String(e))); }
  }, [state.preferencesSaved, onPreferencesApplied]);
  const current = value?.spec.configuration;
  const chosen = draft ?? current;
  const candidate = value?.feasible_configurations.find(c => dimensions.every(([key]) => c[key] === chosen?.[key]));
  const blocked = disabled || !state.ready || state.loading || state.busy || !!state.pending || !!value?.stale_for_display || saving;
  return <section className="adjustment-panel" aria-labelledby="adjust-title"><h3 id="adjust-title">Adjust this presentation</h3>
    <p>Choose support for this visit. Required instructions, conditions, fees and documents stay visible. Unavailable choices are restricted by procedure structure, content review, accessibility or hard locks.</p>
    {state.loading && <p role="status">Loading saved view controls…</p>}
    {state.error && <div className="alert alert-error" role="alert"><p>{state.error}</p></div>}
    {saveError && <p role="alert">{saveError}</p>}
    {state.notice && <p role="status">{state.notice}</p>}
    {state.pending ? <div className="adjustment-actions"><button className="button button-primary" disabled={state.busy} onClick={() => void flow.retry()}>Retry original {state.pending.kind} request</button>
      <button className="button button-outline" disabled={state.busy} onClick={() => { setDraft(null); void flow.recover(); }}>Reload saved views and stop this retry</button><p>Reloading does not undo a request already accepted by the server.</p></div> : !state.ready && !state.loading && <button className="button button-outline" disabled={state.busy} onClick={() => void flow.refresh()}>Retry loading view controls</button>}
    {current && chosen && <>
      <div className="adjustment-fields">{dimensions.map(([key, label, options]) => <label key={key}>{label}<select value={String(chosen[key])} disabled={blocked} onChange={e => {
        const next = options.find(([v]) => String(v) === e.target.value)?.[0];
        setDraft({ ...chosen, [key]: next } as Configuration);
      }}>{options.map(([choice, text]) => {
        const available = value!.feasible_configurations.some(c => c[key] === choice);
        return <option key={String(choice)} value={String(choice)} disabled={!available}>{text}{available ? "" : " — unavailable"}</option>;
      })}</select></label>)}</div>
      {!candidate && <p role="status">These choices are not feasible together. Choose another combination.</p>}
      <div className="adjustment-actions"><button className="button button-primary" disabled={blocked || !candidate || candidate.configuration_id === current.configuration_id} onClick={() => {
        if (candidate) { setDraft(null); void flow.adjust(candidate, "adjust", focus); }
      }}>Apply for this visit</button><button className="button button-outline" disabled={blocked || !value?.can_undo} onClick={() => { setDraft(null); void flow.adjust(null, "undo", focus); }}>Undo latest adjustment</button>
        {draft && <button className="text-button" disabled={blocked} onClick={() => setDraft(null)}>Discard unapplied choices</button>}</div>
      {!!value?.ledger.views.length && <><p className="helper-text">This episode contains manual views. Ratings—including after Undo—are saved separately from policy learning. Request fresh guidance to rate a new policy selection.</p>
        <button className="button button-outline" disabled={blocked || !value.displayed_action_ids.length || state.preferencesSaved} onClick={() => {
          setSaving(true); setSaveError(null);
          void api.getSession(value.ledger.session_id).then(session => flow.savePreferences(session.revision)).catch(e => setSaveError(String(e))).finally(() => setSaving(false));
        }}>{state.preferencesSaved ? "Future preferences saved" : "Save these view settings as future preferences"}</button>
        <p className="helper-text">This separate action saves all five current view settings as soft preferences for future requests. It preserves familiarity, accessibility and hard locks.</p></>}
      <details className="adjustment-history"><summary>View history ({value?.ledger.views.length ?? 0} changes)</summary><p>Original policy view → manual changes. Undo restores a layout with a new display identity; it does not delete history or ratings.</p>
        <ol>{value?.ledger.views.map(v => <li key={v.view_id}><strong>{v.operation === "undo" ? "Undo" : "Adjustment"}</strong> · {v.configuration.presentation_mode} · {v.configuration.relationship_visual}<br /><code>{v.view_id}</code>{v.view_id === value.active_view_id && " · Current view"}</li>)}</ol></details>
    </>}
  </section>;
}
const ratingLabels: Record<ViewRating["rating"], string> = { about_right: "About right", need_more: "I needed more guidance", too_much: "There was too much guidance" };
export function ManualViewFeedback({ flow, state, disabled }: { flow: AdjustmentFlow; state: FlowState; disabled: boolean }) {
  const v = state.value;
  const saved = v?.ledger.ratings.find(r => r.view_id === v.active_view_id);
  const blocked = disabled || state.busy || state.loading || !state.ready || !!state.pending || !!v?.stale_for_display || !v?.displayed_action_ids.length;
  return <section className="adjustment-panel" aria-labelledby="manual-rating-title"><h3 id="manual-rating-title">How was this adjusted view?</h3>
    <p>Optional feedback for the manually controlled presentation. It is recorded against this view and does not train the original bandit decision.</p>
    {!v?.displayed_action_ids.length && <p>View an action first so its display can be confirmed for this view.</p>}
    {saved ? <p role="status"><strong>Saved: {ratingLabels[saved.rating]}</strong> · {saved.origin === "simulation" ? "Simulation record" : "Participant report"} · No policy update</p> : <div className="adjustment-actions">{(Object.keys(ratingLabels) as ViewRating["rating"][]).map(r => <button key={r} className="button button-outline" disabled={blocked} onClick={() => void flow.rate(r)}>{ratingLabels[r]}</button>)}</div>}
  </section>;
}
