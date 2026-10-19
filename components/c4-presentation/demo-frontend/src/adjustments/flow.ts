import { errorMessage } from "../api/client";
import { identifier } from "../profiles/profileDraft";
import { readStored, writeStored, removeStored } from "../session/continuity";
import type { StoragePort } from "../session/continuity";
import type { Configuration, Spec } from "../guidance/types";
import { AdjustmentApi, pendingAdjustment } from "./api";
import type { AdjustmentState, PendingAdjustment, ViewRating } from "./api";

export interface FlowState { loading: boolean; busy: boolean; ready: boolean; value: AdjustmentState | null;
  pending: PendingAdjustment | null; focus: string | null; error: string | null; notice: string | null; preferencesSaved: boolean }
export const emptyFlow: FlowState = { loading: false, busy: false, ready: false, value: null, pending: null, focus: null, error: null, notice: null, preferencesSaved: false };
export class AdjustmentFlow {
  private state: FlowState = emptyFlow;
  private listeners = new Set<() => void>();
  private initial: Promise<void> | null = null;
  private visit = 0;
  private recordedVisit = -1;
  private key: string;
  constructor(private root: Spec, private api = new AdjustmentApi(), private storage: StoragePort | null = null, base = "") {
    this.key = "helaguide:c4:view-retry:v1:" + JSON.stringify([base, root.session_id, root.exposure_id, root.presentation_id]);
  }
  snapshot = () => this.state;
  subscribe = (fn: () => void) => { this.listeners.add(fn); return () => { this.listeners.delete(fn); }; };
  private update(patch: Partial<FlowState>) { this.state = { ...this.state, ...patch }; this.listeners.forEach(fn => fn()); }
  initialize() { this.initial ??= this.restore(); return this.initial; }
  private async restore() {
    const raw = readStored(this.storage, this.key);
    if (raw) {
      try {
        const pending: unknown = JSON.parse(raw);
        if (!pendingAdjustment(pending)) throw new Error("Invalid saved adjustment retry. Request fresh guidance or clear the local retry.");
        this.update({ pending });
      } catch (e) { this.update({ error: errorMessage(e), pending: null }); removeStored(this.storage, this.key); }
    }
    await this.refresh();
  }
  async refresh() {
    if (this.state.busy || this.state.loading) return;
    this.update({ loading: true, ready: false, error: null });
    try {
      const value = await this.api.read(this.root);
      const focus = [...value.ledger.displays].reverse().find(d => d.view_id === value.active_view_id)?.action_id ?? value.focus_action_id;
      this.visit = 0; this.recordedVisit = value.displayed_action_ids.includes(focus) ? 0 : -1;
      this.update({ value, focus, ready: true });
    } catch (e) { this.update({ error: errorMessage(e) }); }
    finally { this.update({ loading: false }); }
  }
  private blocked() { return this.state.loading || this.state.busy || !!this.state.pending || !this.state.ready || !!this.state.value?.stale_for_display; }
  async adjust(configuration: Configuration | null, operation: "adjust" | "undo", focus: string) {
    const value = this.state.value;
    if (this.blocked() || !value) return;
    const fields = configuration ? { presentation_mode: configuration.presentation_mode, progressive_disclosure: configuration.progressive_disclosure,
      previous_context_recap: configuration.previous_context_recap, relationship_visual: configuration.relationship_visual, prerequisite_cue: configuration.prerequisite_cue } : null;
    await this.begin({ kind: "view", body: { request_id: identifier("event"), expected_revision: value.ledger.revision, parent_view_id: value.active_view_id, operation, configuration: fields, focus_action_id: focus } });
  }
  move(action: string) { if (!this.blocked() && action !== this.state.focus && this.state.value?.spec.pages.some(p => p.action_id === action)) { this.visit++; this.update({ focus: action }); } }
  async visible(action: string) {
    const value = this.state.value;
    if (this.blocked() || !value?.ledger.views.length) return;
    const guided = value.spec.configuration.presentation_mode === "GUIDED";
    if (guided ? this.state.focus !== action || this.recordedVisit === this.visit : value.displayed_action_ids.includes(action)) return;
    await this.begin({ kind: "display", body: { event_id: identifier("event"), expected_revision: value.ledger.revision, view_id: value.active_view_id, action_id: action } });
  }
  async rate(rating: ViewRating["rating"]) {
    const v = this.state.value;
    if (this.blocked() || !v || !v.displayed_action_ids.length) return;
    await this.begin({ kind: "rating", body: { event_id: identifier("event"), expected_revision: v.ledger.revision, view_id: v.active_view_id, rating } });
  }
  async savePreferences(revision: number) {
    const v = this.state.value;
    if (this.blocked() || !v?.ledger.views.length || !v.displayed_action_ids.length) return;
    await this.begin({ kind: "preferences", body: { request_id: identifier("event"), view_id: v.active_view_id, expected_session_revision: revision } });
  }
  private async begin(pending: PendingAdjustment) {
    this.update({ pending, notice: null });
    if (!writeStored(this.storage, this.key, JSON.stringify(pending))) this.update({ notice: "Browser storage is unavailable. Keep this tab open until this request is confirmed." });
    await this.retry();
  }
  async retry() {
    const pending = this.state.pending;
    if (!pending || this.state.busy || this.state.loading) return;
    this.update({ busy: true, ready: false, error: null });
    try {
      const value = await this.api.send(this.root, pending);
      const changedView = value.active_view_id !== this.state.value?.active_view_id;
      if (changedView) { this.visit = 0; this.recordedVisit = -1; }
      if (pending.kind === "display") this.recordedVisit = this.visit;
      removeStored(this.storage, this.key);
      this.update({ value, pending: null, ready: true, focus: changedView ? value.focus_action_id : this.state.focus ?? value.focus_action_id,
        preferencesSaved: pending.kind === "preferences" || this.state.preferencesSaved,
        notice: pending.kind === "view" ? "Presentation adjusted for this visit. No policy selection or learning update was made." : pending.kind === "rating" ? "Rating saved for this manual view. It does not update the original policy decision." : pending.kind === "preferences" ? "Future soft preferences saved. Request fresh guidance to use them." : this.state.notice });
    } catch (e) { this.update({ error: errorMessage(e) + " The request is unconfirmed. Retry it unchanged, or reload saved views before continuing." }); }
    finally { this.update({ busy: false }); }
  }
  async recover() {
    if (this.state.busy) return;
    removeStored(this.storage, this.key);
    this.update({ pending: null });
    await this.refresh();
  }
}
