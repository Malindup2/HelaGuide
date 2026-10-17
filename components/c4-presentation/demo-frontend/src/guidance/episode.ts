import { ApiError, errorMessage } from "../api/client";
import type { ActiveIdentity } from "../api/types";
import { identifier } from "../profiles/profileDraft";
import { readStored, removeStored, writeStored } from "../session/continuity";
import type { StoragePort } from "../session/continuity";
import type { GuidanceApi } from "./api";
import type { Guidance, Navigation, PendingDisplay, Spec, Standard } from "./types";

interface Saved {
  exposure_id: string;
  pending: PendingDisplay | null;
}
export interface EpisodeState {
  loading: boolean; busy: boolean; result: Guidance | null; navigation: Navigation | null;
  focus: string | null; pending: PendingDisplay | null; error: string | null; notice: string | null;
}
const initial: EpisodeState = {
  loading: false, busy: false, result: null, navigation: null, focus: null,
  pending: null, error: null, notice: null,
};
export function episodeStorageKey(base: string, active: ActiveIdentity, procedureId: string) {
  return "helaguide:c4:episode:v1:" + JSON.stringify([
    base, active.session.session_id, procedureId,
    active.kind === "profile" ? active.profile.revision : null,
  ]);
}
function pendingMatches(value: unknown, spec: Spec): value is PendingDisplay {
  if (!value || typeof value !== "object" || !("kind" in value) || !("request" in value)) return false;
  const request = value.request;
  if (!request || typeof request !== "object" || !("presentation_id" in request) ||
      !("configuration_id" in request) || request.presentation_id !== spec.presentation_id ||
      request.configuration_id !== spec.configuration.configuration_id) return false;
  if (value.kind === "ack" && "displayed_action_ids" in request) {
    const ids = request.displayed_action_ids;
    return Array.isArray(ids) && ids.length > 0 && new Set(ids).size === ids.length &&
      ids.every((id) => typeof id === "string" && spec.acknowledgment_action_ids.includes(id));
  }
  return value.kind === "navigation" && "action_id" in request && "event_id" in request &&
    typeof request.event_id === "string" && /^event:[0-9a-f]{32}$/.test(request.event_id) &&
    "expected_revision" in request && Number.isSafeInteger(request.expected_revision) && Number(request.expected_revision) >= 0 &&
    spec.pages.some((page) => page.action_id === request.action_id);
}

/** One backend offer, stable across browsing. Navigation is never a policy reward. */
export class GuidanceEpisode {
  private state: EpisodeState = initial;
  private listeners = new Set<() => void>();
  private initialization: Promise<void> | null = null;
  private visit = 0;
  private recordedVisit = -1;
  private key: string;
  constructor(
    private readonly api: GuidanceApi,
    private readonly active: ActiveIdentity,
    private readonly procedureId: string,
    private readonly storage: StoragePort | null,
    base: string,
  ) { this.key = episodeStorageKey(base, active, procedureId); }
  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };
  private update(patch: Partial<EpisodeState>) {
    this.state = { ...this.state, ...patch };
    this.listeners.forEach((listener) => listener());
  }
  private save(spec: Spec, pending: PendingDisplay | null) {
    if (!writeStored(this.storage, this.key, JSON.stringify({ exposure_id: spec.exposure_id, pending } satisfies Saved))) {
      this.update({ notice: "Browser storage is unavailable. Keep this page open to retain the current episode and any retry." });
    }
  }
  private async currentStatus() {
    const status = await this.api.status(this.active.session.session_id);
    const profile = this.active.kind === "profile" ? this.active.profile : null;
    if (status.profile_id !== (profile?.profile_id ?? null) ||
        status.profile_revision !== (profile?.revision ?? null) ||
        status.personalization_enabled !== (profile?.personalization_enabled ?? false)) {
      throw new Error("Profile settings changed. Reopen your profile from the sidebar before requesting guidance.");
    }
    return status;
  }
  initialize() {
    // React StrictMode may attach twice: initialization performs GETs only, once.
    this.initialization ??= this.restore();
    return this.initialization;
  }
  private async restore() {
    const raw = readStored(this.storage, this.key);
    if (!raw || this.active.kind !== "profile" || !this.active.profile.personalization_enabled) return;
    this.update({ loading: true, error: null });
    try {
      const saved: unknown = JSON.parse(raw);
      if (!saved || typeof saved !== "object" || !("exposure_id" in saved) ||
          typeof saved.exposure_id !== "string" || !/^exposure:[0-9a-f]{32}$/.test(saved.exposure_id) || !("pending" in saved)) {
        removeStored(this.storage, this.key);
        throw new Error("The saved episode reference is invalid. Request fresh guidance.");
      }
      const status = await this.currentStatus();
      const response = await this.api.presentation(status.session_id, saved.exposure_id, this.procedureId);
      const spec = response.spec;
      const navigation = await this.api.navigation(spec);
      if (response.stale_for_display && !navigation.acknowledged) {
        removeStored(this.storage, this.key);
        throw new Error("The saved presentation is no longer current. Request fresh guidance.");
      }
      if (saved.pending !== null && !pendingMatches(saved.pending, spec)) {
        removeStored(this.storage, this.key);
        throw new Error("The saved display retry is invalid. Request fresh guidance.");
      }
      const pending = saved.pending;
      this.recordedVisit = navigation.acknowledged ? 0 : -1;
      this.update({
        result: { ...status, mode: "adaptive", spec, stale_for_display: response.stale_for_display }, navigation, pending,
        focus: pending?.kind === "navigation" ? pending.request.action_id :
          navigation.current_action_id ?? spec.initial_action_id,
        notice: pending ? "A display request needs confirmation. Retry it unchanged." :
          response.stale_for_display ? "The original acknowledged presentation was restored for reference and feedback. Request fresh guidance to use current settings." :
          "The existing presentation was restored without selecting a new configuration.",
      });
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) removeStored(this.storage, this.key);
      this.update({ error: errorMessage(error) });
    } finally { this.update({ loading: false }); }
  }
  async select(writingStyle: Standard["writing_style"] = "plain") {
    if (this.state.busy || this.state.loading || this.state.pending) return;
    this.update({ busy: true, error: null, notice: null, result: null, navigation: null, focus: null });
    try {
      const status = await this.currentStatus();
      const result = await this.api.select(status.session_id, {
        procedure_id: this.procedureId, expected_revision: status.session_revision,
        expected_profile_revision: status.profile_revision, standard_writing_style: writingStyle,
      });
      if (result.mode === "adaptive" && result.stale_for_display) throw new Error("This presentation is stale. Reopen your profile and request fresh guidance.");
      this.visit = 0; this.recordedVisit = -1;
      if (result.mode === "adaptive") this.save(result.spec, null);
      else removeStored(this.storage, this.key);
      this.update({
        result, focus: result.mode === "adaptive" ? result.spec.initial_action_id : null,
        notice: result.mode === "standard" ? "Standard guidance: no policy decision or learning exposure." :
          "Configuration selected. Display is recorded only when an action enters the visible viewport.",
      });
    } catch (error) {
      this.update({ error: errorMessage(error) + " Guidance requests are never retried automatically. A lost response may have saved an unused offer; requesting fresh guidance is an explicit new decision." });
    } finally { this.update({ busy: false }); }
  }
  close() {
    if (this.state.busy || this.state.loading) return;
    removeStored(this.storage, this.key);
    this.visit = 0; this.recordedVisit = -1;
    this.update({ ...initial, notice: "Guidance closed. Already accepted backend display records remain stored; no learning update was made." });
  }
  freezeForPreferences() {
    const result = this.state.result;
    if (result?.mode !== "adaptive") return;
    this.update({ result: { ...result, stale_for_display: true },
      notice: "Preferences applied. The original presentation is retained for reference and feedback. Request fresh guidance to use current settings." });
  }
  move(actionId: string) {
    const result = this.state.result;
    if (this.state.busy || this.state.pending || result?.mode !== "adaptive" || result.stale_for_display ||
        result.spec.configuration.presentation_mode !== "GUIDED" ||
        !this.state.navigation?.acknowledged || actionId === this.state.focus ||
        !result.spec.pages.some((page) => page.action_id === actionId)) return;
    this.visit += 1;
    this.update({ focus: actionId, error: null });
  }
  async visible(actionId: string) {
    const result = this.state.result;
    if (this.state.busy || this.state.pending || result?.mode !== "adaptive" || result.stale_for_display ||
        !result.spec.pages.some((page) => page.action_id === actionId)) return;
    const spec = result.spec;
    const guided = spec.configuration.presentation_mode === "GUIDED";
    if (guided && (actionId !== this.state.focus || this.recordedVisit === this.visit)) return;
    if (!guided && this.state.navigation?.displayed_action_ids.includes(actionId)) return;
    const pending: PendingDisplay = this.state.navigation?.acknowledged
      ? { kind: "navigation", request: {
          event_id: identifier("event"), expected_revision: this.state.navigation.session_revision,
          presentation_id: spec.presentation_id, configuration_id: spec.configuration.configuration_id,
          action_id: actionId,
        } }
      : { kind: "ack", request: {
          presentation_id: spec.presentation_id, configuration_id: spec.configuration.configuration_id,
          displayed_action_ids: [actionId],
        } };
    if (!pendingMatches(pending, spec)) return;
    this.update({ pending });
    this.save(spec, pending);
    await this.retryDisplay();
  }
  async retryDisplay() {
    const { result, pending } = this.state;
    if (this.state.busy || !pending || result?.mode !== "adaptive") return;
    this.update({ busy: true, error: null });
    try {
      if (pending.kind === "ack") await this.api.acknowledge(result.spec, pending.request);
      else await this.api.display(result.spec, pending.request);
      const navigation = await this.api.navigation(result.spec);
      this.recordedVisit = this.visit;
      this.save(result.spec, null);
      this.update({ navigation, pending: null });
    } catch (error) {
      this.update({ error: errorMessage(error) + " Display attribution is unconfirmed. Retry the same request; no reward has been created." });
    } finally { this.update({ busy: false }); }
  }
}
