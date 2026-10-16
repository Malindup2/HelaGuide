import type { ActiveIdentity, ProcedureSummary } from "../api/types";

export default function ContextSummary({
  active, procedures,
}: {
  active: ActiveIdentity;
  procedures: ProcedureSummary[];
}) {
  const settings = active.session.settings;
  const familiarity = new Map(settings.familiarity.map((entry) => [entry.service_id, entry.score]));
  const services = [...new Map(
    procedures.map((procedure) => [procedure.requested_service_id, procedure]),
  ).values()];
  const mode = settings.preferences.presentation_mode;
  const locks = Object.entries(settings.locks).filter(([, value]) => value !== null);
  return (
    <section className="context-summary" aria-labelledby="context-title">
      <div className="section-heading compact">
        <div>
          <p className="eyebrow">Available context</p>
          <h3 id="context-title">{active.kind === "profile" ? "Your saved starting point" : "Your guest workspace"}</h3>
        </div>
        <span className="tag">{active.kind === "profile" ? "Self-reported" : "Session only"}</span>
      </div>
      {active.kind === "guest" ? (
        <p className="muted">
          Personalization is off. Standard guidance uses the supplied procedure;
          no familiarity or ability is inferred from your visits.
        </p>
      ) : (
        <>
          <dl className="context-grid">
            <div>
              <dt>Navigation confidence</dt>
              <dd>{settings.navigation_capability === null ? "Unknown" : settings.navigation_capability + " / 5"}</dd>
            </div>
            <div>
              <dt>Soft layout preference</dt>
              <dd>{mode === "GUIDED" ? "Step-by-step" : mode === "OVERVIEW" ? "Overview" : "Let the system choose"}</dd>
            </div>
            <div>
              <dt>Relationship visuals</dt>
              <dd>{settings.accessibility.allow_relationship_visuals ? "Allowed" : "Disabled"}</dd>
            </div>
            <div>
              <dt>Collapsed supplementary text</dt>
              <dd>{settings.accessibility.allow_collapsed_content ? "Allowed" : "Disabled"}</dd>
            </div>
            <div>
              <dt>Focused step-by-step navigation</dt>
              <dd>{settings.accessibility.allow_guided_navigation ? "Allowed" : "Disabled"}</dd>
            </div>
          </dl>
          <details className="familiarity-summary">
            <summary>Service-specific familiarity</summary>
            <dl>
              {services.map((procedure) => (
                <div key={procedure.requested_service_id}>
                  <dt>{procedure.title}</dt>
                  <dd>{familiarity.get(procedure.requested_service_id) == null
                    ? "Unknown" : familiarity.get(procedure.requested_service_id) + " / 5"}</dd>
                </div>
              ))}
            </dl>
          </details>
          {locks.length > 0 && (
            <p className="helper-text">
              Existing explicit locks are retained: {locks.map(([name, value]) =>
                name.replaceAll("_", " ") + " = " + String(value),
              ).join("; ")}.
            </p>
          )}
        </>
      )}
      <details className="technical-details">
        <summary>Workspace reference</summary>
        <dl>
          {active.kind === "profile" && (
            <div><dt>Demo profile</dt><dd><code>{active.profile.profile_id}</code></dd></div>
          )}
          <div><dt>Context session</dt><dd><code>{active.session.session_id}</code></dd></div>
          <div><dt>Context revision</dt><dd>{active.session.revision}</dd></div>
          {active.kind === "profile" && (
            <div><dt>Personalization-setting revision</dt><dd>{active.profile.revision}</dd></div>
          )}
        </dl>
      </details>
    </section>
  );
}
