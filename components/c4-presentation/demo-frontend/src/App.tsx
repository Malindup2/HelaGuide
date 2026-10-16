import { useEffect, useRef, useState } from "react";
import { API_BASE, api, errorMessage } from "./api/client";
import type {
  BackendHealth,
  GuestSession,
  ProcedureSummary,
} from "./api/types";
import {
  browserStorage,
  readStored,
  resumeGuest,
  storageKey,
  writeStored,
} from "./session/continuity";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; health: BackendHealth; procedures: ProcedureSummary[] };

const sessionKey = storageKey(API_BASE, "session");
const procedureKey = storageKey(API_BASE, "procedure");

function ProcedureCard({
  procedure,
  selected,
  onSelect,
}: {
  procedure: ProcedureSummary;
  selected: boolean;
  onSelect: () => void;
}) {
  const actionCount = procedure.action_ids.length;

  return (
    <button
      type="button"
      className={`procedure-card ${selected ? "is-selected" : ""}`}
      aria-pressed={selected}
      onClick={onSelect}
    >
      <span className="card-top">
        <span className="eyebrow">
          {procedure.synthetic ? "Synthetic example" : "Supplied procedure"}
        </span>
        <span className="selection-marker" aria-hidden="true">
          {selected ? "✓" : "↗"}
        </span>
      </span>

      <span className="procedure-title">{procedure.title}</span>

      <span className="procedure-description">
        {procedure.disclaimer ||
          "Explore the procedural information registered by the C4 backend."}
      </span>

      <span className="card-bottom">
        <span>
          {actionCount} {actionCount === 1 ? "action" : "actions"}
        </span>
        <span>{selected ? "Selected" : "Select procedure"}</span>
      </span>
    </button>
  );
}

function ConnectionBadge({ state }: { state: LoadState }) {
  const label =
    state.status === "ready"
      ? "Backend connected"
      : state.status === "loading"
        ? "Connecting"
        : "Connection needs attention";

  return (
    <span className={`connection-badge connection-${state.status}`}>
      <span className="status-dot" aria-hidden="true" />
      {label}
    </span>
  );
}

export default function App() {
  const [load, setLoad] = useState<LoadState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [session, setSession] = useState<GuestSession | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const creatingRef = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    setLoad({ status: "loading" });
    setSessionError(null);

    async function initialize() {
      try {
        const health = await api.health(controller.signal);
        const procedures = await api.procedures(controller.signal);
        const storage = browserStorage();
        const resumed = await resumeGuest(
          api,
          storage,
          sessionKey,
          controller.signal,
        );

        if (controller.signal.aborted) return;

        const storedProcedure = readStored(storage, procedureKey);
        const validSelection = procedures.some(
          (procedure) => procedure.procedure_id === storedProcedure,
        );

        setSelectedId(validSelection ? storedProcedure : null);
        setSession(resumed.session);
        setNotice(
          resumed.notice ??
            (storage
              ? null
              : "Browser storage is unavailable. This session may not survive a reload."),
        );
        setLoad({ status: "ready", health, procedures });
      } catch (error) {
        if (!controller.signal.aborted) {
          setLoad({ status: "error", message: errorMessage(error) });
        }
      }
    }

    void initialize();
    return () => controller.abort();
  }, [attempt]);

  const procedures = load.status === "ready" ? load.procedures : [];
  const selected =
    procedures.find((procedure) => procedure.procedure_id === selectedId) ??
    null;

  function selectProcedure(procedure: ProcedureSummary) {
    setSelectedId(procedure.procedure_id);

    if (
      !writeStored(
        browserStorage(),
        procedureKey,
        procedure.procedure_id,
      )
    ) {
      setNotice(
        "Your selection is available now, but browser storage could not save it for reload.",
      );
    }
  }

  async function startGuestSession() {
    if (creatingRef.current || !selected || load.status !== "ready") return;

    creatingRef.current = true;
    setCreating(true);
    setSessionError(null);

    try {
      const created = await api.createSession();
      setSession(created);

      const saved = writeStored(
        browserStorage(),
        sessionKey,
        created.session_id,
      );

      setNotice(
        saved
          ? "Guest session created. Reloading this tab will resume it."
          : "Guest session created, but browser storage is unavailable. Reload continuity is not guaranteed.",
      );
    } catch (error) {
      setSessionError(
        `${errorMessage(error)} If the connection failed after submission, the server may have created a session. No automatic retry was made.`,
      );
    } finally {
      creatingRef.current = false;
      setCreating(false);
    }
  }

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>

      <header className="site-header">
        <div className="brand" aria-label="HelaGuide C4">
          <span className="brand-mark" aria-hidden="true">
            H
          </span>
          <div>
            <span className="brand-name">HelaGuide</span>
            <span className="brand-caption">Adaptive guidance</span>
          </div>
        </div>

        <div className="header-meta">
          <span className="research-label">C4 Research Prototype</span>
          <ConnectionBadge state={load} />
        </div>
      </header>

      <main id="main-content" className="main-content">
        <section className="hero" aria-labelledby="page-title">
          <div>
            <p className="eyebrow">Guidance, at your pace</p>
            <h1 id="page-title">
              A clearer way
              <br />
              through the process.
            </h1>
            <p className="hero-description">
              Choose a procedure to begin. HelaGuide explores how procedural
              information can be presented with the right level of support.
            </p>
          </div>

          <aside className="research-note" aria-label="Research demonstration">
            <span className="note-symbol" aria-hidden="true">
              ◇
            </span>
            <h2>A research space</h2>
            <p>
              Registered synthetic examples support this demonstration.
              They are not official application instructions.
            </p>
            <span className="small-label">No account required</span>
          </aside>
        </section>

        {notice && (
          <div className="notice" role="status">
            {notice}
          </div>
        )}

        {load.status === "loading" && (
          <section className="state-panel" role="status" aria-live="polite">
            <span className="loading-line" />
            <h2>Connecting to your guidance workspace</h2>
            <p>Loading registered procedures and checking your saved session.</p>
          </section>
        )}

        {load.status === "error" && (
          <section className="state-panel error-panel" role="alert">
            <p className="eyebrow">Connection unavailable</p>
            <h2>Your guidance workspace could not load</h2>
            <p>{load.message}</p>
            <p className="technical-address">{API_BASE}</p>
            <button
              className="button button-primary"
              onClick={() => setAttempt((value) => value + 1)}
              type="button"
            >
              Retry connection
            </button>
          </section>
        )}

        {load.status === "ready" && (
          <>
            <section aria-labelledby="procedures-heading">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">01 / Choose a procedure</p>
                  <h2 id="procedures-heading">Where would you like to begin?</h2>
                </div>
                <span className="count-label">
                  {procedures.length} registered{" "}
                  {procedures.length === 1 ? "procedure" : "procedures"}
                </span>
              </div>

              {procedures.length === 0 ? (
                <div className="state-panel">
                  <h3>No procedures are registered</h3>
                  <p>
                    The backend is connected, but its procedure catalogue is
                    empty.
                  </p>
                </div>
              ) : (
                <div className="procedure-grid">
                  {procedures.map((procedure) => (
                    <ProcedureCard
                      key={procedure.procedure_id}
                      procedure={procedure}
                      selected={procedure.procedure_id === selectedId}
                      onSelect={() => selectProcedure(procedure)}
                    />
                  ))}
                </div>
              )}
            </section>

            <section className="session-panel" aria-labelledby="session-heading">
              <div className="session-copy">
                <p className="eyebrow">02 / Your guest workspace</p>
                <h2 id="session-heading">
                  {session ? "Your session is ready." : "Start without an account."}
                </h2>
                <p>
                  {session
                    ? "Your existing backend session is available. Choosing a procedure here does not generate a presentation or record exposure."
                    : "A guest session keeps your context together. No name, email address or account is required."}
                </p>

                {selected && (
                  <p className="selected-summary">
                    <span>Selected procedure</span>
                    <strong>{selected.title}</strong>
                  </p>
                )}

                {session && (
                  <div className="session-details">
                    <span className="session-pill">Guest session active</span>
                    <span>Context revision {session.revision}</span>
                    <details>
                      <summary>Session reference</summary>
                      <code>{session.session_id}</code>
                    </details>
                  </div>
                )}
              </div>

              <div className="session-action">
                {!session ? (
                  <>
                    <button
                      type="button"
                      className="button button-primary"
                      disabled={!selected || creating}
                      onClick={() => void startGuestSession()}
                    >
                      {creating ? "Creating session…" : "Start guest session"}
                      {!creating && <span aria-hidden="true">→</span>}
                    </button>
                    <p className="helper-text">
                      {selected
                        ? "This creates a real session in the C4 backend."
                        : "Select a procedure above first."}
                    </p>
                  </>
                ) : (
                  <div className="next-stage">
                    <span className="small-label">Foundation connected</span>
                    <p>
                      Onboarding and adaptive guidance will be connected in the
                      next implementation slice.
                    </p>
                  </div>
                )}
              </div>

              {sessionError && (
                <div className="inline-error" role="alert">
                  {sessionError}
                </div>
              )}
            </section>
          </>
        )}
      </main>

      <footer className="site-footer">
        <span>HelaGuide · Context-Aware Adaptive Guidance</span>
        <span>
          {load.status === "ready"
            ? `Connected · ${load.health.storage} storage`
            : "Independent C4 demonstration"}
        </span>
      </footer>
    </div>
  );
}