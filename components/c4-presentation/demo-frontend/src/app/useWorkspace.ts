import { useEffect, useRef, useState } from "react";
import { API_BASE, ApiError, api, errorMessage } from "../api/client";
import type {
  ActiveIdentity, BackendHealth, CreateDemoProfileRequest, DemoProfile,
  DemoProfileResponse, PersonalizationRequest, ProcedureSummary,
} from "../api/types";
import { browserStorage, readStored, removeStored, storageKey, writeStored } from "../session/continuity";
import { rememberIdentity, restoreIdentity } from "../session/identity";
import { buildProfileRequest, identifier, parseCreationRequest } from "../profiles/profileDraft";
import type { ProfileDraft } from "../profiles/profileDraft";

interface PendingMode {
  profile_id: string;
  request: PersonalizationRequest;
}
interface State {
  loading: boolean;
  health: BackendHealth | null;
  procedures: ProcedureSummary[];
  profiles: DemoProfile[];
  active: ActiveIdentity | null;
  selectedId: string;
  view: "workspace" | "create";
  busy: string | null;
  error: string | null;
  notice: string | null;
  pendingCreation: CreateDemoProfileRequest | null;
  pendingMode: PendingMode | null;
}
const initial: State = {
  loading: true, health: null, procedures: [], profiles: [], active: null,
  selectedId: "", view: "workspace", busy: null, error: null, notice: null,
  pendingCreation: null, pendingMode: null,
};

function loadPendingMode(): PendingMode | null {
  const key = storageKey(API_BASE, "pending-mode");
  const text = readStored(browserStorage(), key);
  if (!text) return null;
  try {
    const value = JSON.parse(text);
    if (typeof value.profile_id === "string" &&
        /^profile:[0-9a-f]{32}$/.test(value.profile_id) &&
        typeof value.request?.request_id === "string" &&
        /^event:[0-9a-f]{32}$/.test(value.request.request_id) &&
        Number.isInteger(value.request.expected_revision) &&
        value.request.expected_revision >= 0 &&
        typeof value.request.enabled === "boolean") return value;
  } catch { /* Invalid browser state is never sent to the server. */ }
  removeStored(browserStorage(), key);
  return null;
}

export function useWorkspace() {
  const [state, setState] = useState<State>(initial);
  const [attempt, setAttempt] = useState(0);
  const mutation = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    async function initialize() {
      try {
        const [health, procedures, profiles] = await Promise.all([
          api.health(controller.signal),
          api.procedures(controller.signal),
          api.profiles(controller.signal),
        ]);
        const storage = browserStorage();
        const restored = await restoreIdentity(api, storage, API_BASE, controller.signal);
        const savedProcedure = readStored(storage, storageKey(API_BASE, "procedure"));
        let pendingCreation: CreateDemoProfileRequest | null = null;
        const pendingText = readStored(storage, storageKey(API_BASE, "pending-profile"));
        if (pendingText) {
          try { pendingCreation = parseCreationRequest(JSON.parse(pendingText)); }
          catch { removeStored(storage, storageKey(API_BASE, "pending-profile")); }
        }
        if (controller.signal.aborted) return;
        setState({
          ...initial, loading: false, health, procedures, profiles,
          active: restored.active,
          selectedId: procedures.some((item) => item.procedure_id === savedProcedure)
            ? savedProcedure! : "",
          notice: restored.notice,
          pendingCreation,
          pendingMode: loadPendingMode(),
        });
      } catch (error) {
        if (!controller.signal.aborted) {
          setState((old) => ({ ...old, loading: false, error: errorMessage(error) }));
        }
      }
    }
    void initialize();
    return () => controller.abort();
  }, [attempt]);

  function activate(result: ActiveIdentity, notice: string) {
    const remembered = rememberIdentity(browserStorage(), API_BASE, result);
    setState((old) => ({
      ...old,
      active: result,
      view: "workspace",
      notice: remembered ? notice : notice + " Browser reload storage is unavailable.",
      profiles: result.kind === "profile"
        ? [...old.profiles.filter((item) => item.profile_id !== result.profile.profile_id), result.profile]
            .sort((a, b) => a.display_name.localeCompare(b.display_name))
        : old.profiles,
    }));
  }

  async function perform(label: string, operation: () => Promise<void>) {
    if (mutation.current || state.loading) return;
    mutation.current = true;
    setState((old) => ({ ...old, busy: label, error: null }));
    try { await operation(); }
    catch (error) { setState((old) => ({ ...old, error: errorMessage(error) })); }
    finally {
      mutation.current = false;
      setState((old) => ({ ...old, busy: null }));
    }
  }

  function acceptProfile(result: DemoProfileResponse, notice: string) {
    activate({ kind: "profile", ...result }, notice);
  }

  function selectProcedure(id: string) {
    if (mutation.current || !state.procedures.some((item) => item.procedure_id === id)) return;
    const saved = writeStored(browserStorage(), storageKey(API_BASE, "procedure"), id);
    setState((old) => ({
      ...old, selectedId: id,
      notice: saved ? old.notice : "Selection updated. Browser reload storage is unavailable.",
    }));
  }

  function retryConnection() {
    if (mutation.current) return;
    setState((old) => ({ ...old, loading: true, error: null }));
    setAttempt((old) => old + 1);
  }

  function continueGuest() {
    if (state.pendingMode) return;
    return perform("Opening guest workspace", async () => {
      const storage = browserStorage();
      const savedId = readStored(storage, storageKey(API_BASE, "session"));
      if (savedId && /^guest:[0-9a-f]{32}$/.test(savedId)) {
        try {
          const session = await api.getSession(savedId);
          activate({ kind: "guest", session }, "Guest workspace restored. Personalization is off.");
          return;
        } catch (error) {
          if (!(error instanceof ApiError && error.status === 404)) throw error;
          removeStored(storage, storageKey(API_BASE, "session"));
        }
      }
      try {
        const session = await api.createSession();
        activate({ kind: "guest", session }, "Guest workspace ready. Personalization is off.");
      } catch (error) {
        throw new Error(
          errorMessage(error) + " No automatic retry was made; a lost response may have created an unused guest session.",
          { cause: error },
        );
      }
    });
  }

  function chooseProfile(id: string) {
    if (state.pendingMode) return;
    return perform("Opening profile", async () => {
      acceptProfile(await api.getProfile(id), "Saved profile and current context loaded.");
    });
  }

  function openCreation() {
    if (mutation.current || state.pendingMode) return;
    setState((old) => ({ ...old, view: "create", error: null }));
  }

  function closeCreation() {
    if (mutation.current) return;
    setState((old) => ({ ...old, view: "workspace", error: null }));
  }

  function submitProfile(draft: ProfileDraft) {
    if (state.pendingMode) return;
    return perform("Saving profile", async () => {
      const request = state.pendingCreation ?? buildProfileRequest(draft, state.procedures);
      // Retain the original request for explicit retries, including after reload.
      writeStored(browserStorage(), storageKey(API_BASE, "pending-profile"), JSON.stringify(request));
      setState((old) => ({ ...old, pendingCreation: request }));
      const result = await api.createProfile(request);
      removeStored(browserStorage(), storageKey(API_BASE, "pending-profile"));
      setState((old) => ({ ...old, pendingCreation: null }));
      acceptProfile(result, "Demo profile saved. Your answers remain editable context, not inferred knowledge.");
    });
  }

  function discardPendingCreation() {
    if (mutation.current) return;
    removeStored(browserStorage(), storageKey(API_BASE, "pending-profile"));
    setState((old) => ({
      ...old, pendingCreation: null, view: "workspace", error: null,
      notice: "Retry cancelled. If the server saved that profile, it remains in Saved profiles. Refresh the list to check.",
    }));
  }

  function togglePersonalization() {
    if (state.active?.kind !== "profile") return;
    const active = state.active;
    return perform("Updating personalization", async () => {
      const pending: PendingMode = state.pendingMode ?? {
        profile_id: active.profile.profile_id,
        request: {
          request_id: identifier("event"),
          expected_revision: active.profile.revision,
          enabled: !active.profile.personalization_enabled,
        },
      };
      writeStored(browserStorage(), storageKey(API_BASE, "pending-mode"), JSON.stringify(pending));
      setState((old) => ({ ...old, pendingMode: pending }));
      try {
        const result = await api.setPersonalization(pending.profile_id, pending.request);
        removeStored(browserStorage(), storageKey(API_BASE, "pending-mode"));
        setState((old) => ({ ...old, pendingMode: null }));
        acceptProfile(result, result.profile.personalization_enabled
          ? "Personalization enabled for future guidance requests."
          : "Personalization disabled. Future requests will use standard guidance.");
      } catch (error) {
        if (error instanceof ApiError && error.status === 409) {
          const current = await api.getProfile(pending.profile_id);
          removeStored(browserStorage(), storageKey(API_BASE, "pending-mode"));
          setState((old) => ({ ...old, pendingMode: null }));
          acceptProfile(current, "The profile changed elsewhere. Current settings have been loaded; review them before trying again.");
        }
        throw error;
      }
    });
  }

  function refreshProfiles() {
    return perform("Refreshing profiles", async () => {
      const profiles = await api.profiles();
      setState((old) => ({ ...old, profiles, notice: "Saved profile list refreshed." }));
    });
  }

  function retryPendingMode() {
    const pending = state.pendingMode;
    if (!pending) return;
    return perform("Retrying personalization request", async () => {
      try {
        const result = await api.setPersonalization(pending.profile_id, pending.request);
        removeStored(browserStorage(), storageKey(API_BASE, "pending-mode"));
        setState((old) => ({ ...old, pendingMode: null }));
        acceptProfile(result, "Original setting request resolved. Current profile state loaded.");
      } catch (error) {
        if (error instanceof ApiError && error.status === 409) {
          const current = await api.getProfile(pending.profile_id);
          removeStored(browserStorage(), storageKey(API_BASE, "pending-mode"));
          setState((old) => ({ ...old, pendingMode: null }));
          acceptProfile(current, "The original setting request conflicted with newer changes. Current settings are loaded; review them before submitting another change.");
        }
        throw error;
      }
    });
  }

  return {
    state, selectProcedure, retryConnection, continueGuest, chooseProfile,
    openCreation, closeCreation, submitProfile, discardPendingCreation,
    togglePersonalization, refreshProfiles, retryPendingMode,
  };
}
