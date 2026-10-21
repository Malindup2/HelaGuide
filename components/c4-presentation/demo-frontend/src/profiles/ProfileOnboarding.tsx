import { useId, useState } from "react";
import type { FormEvent } from "react";
import type {
  AccessibilityConstraints, CreateDemoProfileRequest, FivePointRating,
  PresentationMode, ProcedureSummary,
} from "../api/types";
import { draftFromRequest, emptyDraft } from "./profileDraft";
import type { ProfileDraft } from "./profileDraft";

const levels: { value: FivePointRating; label: string }[] = [
  { value: 1, label: "1 - Not familiar" },
  { value: 2, label: "2 - Slightly familiar" },
  { value: 3, label: "3 - Somewhat familiar" },
  { value: 4, label: "4 - Familiar" },
  { value: 5, label: "5 - Very familiar" },
];

function rating(value: string): FivePointRating | null {
  return value === "" ? null : Number(value) as FivePointRating;
}

export default function ProfileOnboarding({
  procedures, pending, busy, onSubmit, onCancel, onDiscard,
}: {
  procedures: ProcedureSummary[];
  pending: CreateDemoProfileRequest | null;
  busy: boolean;
  onSubmit: (draft: ProfileDraft) => void;
  onCancel: () => void;
  onDiscard: () => void;
}) {
  const [draft, setDraft] = useState<ProfileDraft>(() =>
    pending ? draftFromRequest(pending) : emptyDraft(),
  );
  const prefix = useId();
  const services = [...new Map(
    procedures.map((procedure) => [procedure.requested_service_id, procedure]),
  ).values()];

  function toggleService(serviceId: string) {
    setDraft((old) => ({
      ...old,
      familiarity: Object.hasOwn(old.familiarity, serviceId)
        ? Object.fromEntries(Object.entries(old.familiarity).filter(([id]) => id !== serviceId))
        : { ...old.familiarity, [serviceId]: null },
    }));
  }

  function accessibility(name: keyof AccessibilityConstraints, checked: boolean) {
    setDraft((old) => ({
      ...old, accessibility: { ...old.accessibility, [name]: checked },
    }));
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    onSubmit(draft);
  }

  return (
    <form className="onboarding panel" onSubmit={submit}>
      <div className="section-heading">
        <div>
          <p className="eyebrow">Your starting point</p>
          <h2>Create a demo profile</h2>
          <p className="muted">Create a demo profile to use personalized guidance. Individual answers can remain unknown.</p>
        </div>
        <button className="button button-quiet" type="button" onClick={onCancel} disabled={busy}>
          Back
        </button>
      </div>

      {pending && (
        <div className="notice">
          This creation request has not been confirmed. Its original answers and identity are
          retained so retrying cannot create another profile.
        </div>
      )}

      <fieldset className="form-fields" disabled={busy || pending !== null}>
        <legend className="sr-only">Demo profile answers</legend>
        <div className="form-block">
          <label className="field-label" htmlFor={prefix + "-name"}>Demo profile label</label>
          <input id={prefix + "-name"} required maxLength={60}
            placeholder="For example, Demo citizen A" autoComplete="off"
            value={draft.displayName}
            onChange={(event) => setDraft({ ...draft, displayName: event.target.value })} />
          <p className="helper-text">Use an alias. Saved profiles are visible in this local research demonstration.</p>
        </div>

        <div className="form-block">
          <label className="field-label" htmlFor={prefix + "-navigation"}>
            How confident are you finding your way through procedural instructions?
          </label>
          <select id={prefix + "-navigation"}
            value={draft.navigationCapability ?? ""}
            onChange={(event) => setDraft({ ...draft, navigationCapability: rating(event.target.value) })}>
            <option value="">Not sure / skip</option>
            <option value="1">1 - Not confident</option>
            <option value="2">2 - Slightly confident</option>
            <option value="3">3 - Somewhat confident</option>
            <option value="4">4 - Confident</option>
            <option value="5">5 - Very confident</option>
          </select>
        </div>

        <div className="form-block">
          <span className="field-label">Which procedures would you like to report familiarity with?</span>
          <p className="helper-text">Select any service, then choose a level if you wish. Unanswered services stay unknown.</p>
          <div className="service-chips" aria-label="Services for familiarity answers">
            {services.map((procedure) => (
              <button type="button" className="service-chip"
                key={procedure.requested_service_id}
                aria-pressed={Object.hasOwn(draft.familiarity, procedure.requested_service_id)}
                onClick={() => toggleService(procedure.requested_service_id)}>
                <span aria-hidden="true">
                  {Object.hasOwn(draft.familiarity, procedure.requested_service_id) ? "✓" : "+"}
                </span>
                {procedure.title}
              </button>
            ))}
          </div>
          {services.filter((procedure) => Object.hasOwn(draft.familiarity, procedure.requested_service_id))
            .map((procedure, index) => (
              <div className="familiarity-row" key={procedure.requested_service_id}>
                <label htmlFor={prefix + "-familiarity-" + index}>{procedure.title}</label>
                <select id={prefix + "-familiarity-" + index}
                  value={draft.familiarity[procedure.requested_service_id] ?? ""}
                  onChange={(event) => setDraft({
                    ...draft,
                    familiarity: {
                      ...draft.familiarity,
                      [procedure.requested_service_id]: rating(event.target.value),
                    },
                  })}>
                  <option value="">Unknown / skip</option>
                  {levels.map((level) => (
                    <option key={level.value} value={level.value}>{level.label}</option>
                  ))}
                </select>
              </div>
            ))}
        </div>

        <div className="form-block">
          <label className="field-label" htmlFor={prefix + "-preference"}>Do you have a preferred guidance layout?</label>
          <select id={prefix + "-preference"} value={draft.presentationMode ?? ""}
            onChange={(event) => setDraft({
              ...draft, presentationMode: (event.target.value || null) as PresentationMode | null,
            })}>
            <option value="">Let the system choose</option>
            <option value="OVERVIEW">Prefer a full overview</option>
            <option value="GUIDED">Prefer step-by-step guidance</option>
          </select>
          <p className="helper-text">A preference informs the model. It does not lock or guarantee the selected layout.</p>
        </div>

        <details className="accessibility-options">
          <summary>Accessibility and display requirements <span>Optional</span></summary>
          <p className="helper-text">These control which presentation formats may be used.</p>
          <label className="check-row">
            <input type="checkbox" checked={draft.accessibility.allow_relationship_visuals}
              onChange={(event) => accessibility("allow_relationship_visuals", event.target.checked)} />
            <span>Allow optional relationship diagrams</span>
          </label>
          <label className="check-row">
            <input type="checkbox" checked={draft.accessibility.allow_collapsed_content}
              onChange={(event) => accessibility("allow_collapsed_content", event.target.checked)} />
            <span>Allow supplementary explanations to start collapsed</span>
          </label>
          <label className="check-row">
            <input type="checkbox" checked={draft.accessibility.allow_guided_navigation}
              onChange={(event) => accessibility("allow_guided_navigation", event.target.checked)} />
            <span>Allow focused step-by-step navigation</span>
          </label>
          <p className="helper-text">Required facts, warnings and sources remain available in every layout.</p>
        </details>

        <label className="personalization-consent">
          <input type="checkbox" checked={draft.personalizationEnabled}
            onChange={(event) => setDraft({ ...draft, personalizationEnabled: event.target.checked })} />
          <span>
            <strong>Enable personalized guidance</strong>
            <span>Use my stated context for adaptive presentation. Interaction evidence is retained separately for research.
              I can turn this off later.</span>
          </span>
        </label>
      </fieldset>

      <div className="form-footer">
        <p className="helper-text">
          Save your profile and explicitly enable personalization to use adaptive guidance. Unanswered questions stay unknown.
        </p>
        <div className="button-row">
          {pending && (
            <button type="button" className="button button-quiet" disabled={busy} onClick={onDiscard}>
              Cancel retry
            </button>
          )}
          <button type="submit" className="button button-primary" disabled={busy}>
            {busy ? "Saving…" : pending ? "Retry original request" : "Save demo profile"}
            <span aria-hidden="true">↗</span>
          </button>
        </div>
      </div>
    </form>
  );
}
