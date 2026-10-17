import { ApiError, ContractError, errorMessage } from "../api/client";
import type { Navigation, Spec } from "../guidance/types";
import { readStored, removeStored, writeStored } from "../session/continuity";
import type { StoragePort } from "../session/continuity";
import type { FeedbackApi } from "./api";
import { parsePending, parsePolicy, validReasons } from "./contracts";
import { attribution } from "./types";
import type { AcceptedFeedback, CorrectionCode, CorrectionOptions, CorrectionRecord, DecisionSummary, PendingFeedback, PolicyStatus, Rating } from "./types";

export interface FeedbackState {
  loading: boolean; busy: boolean; ready: boolean; error: string | null; notice: string | null;
  accepted: AcceptedFeedback | null; correction: CorrectionRecord | null; options: CorrectionOptions | null;
  decision: DecisionSummary | null; policy: PolicyStatus | null; before: PolicyStatus | null; pending: PendingFeedback | null;
}
const initial: FeedbackState = {
  loading: true, busy: false, ready: false, error: null, notice: null,
  accepted: null, correction: null, options: null, decision: null, policy: null, before: null, pending: null,
};
export function feedbackStorageKey(base: string, spec: Spec) {
  return "helaguide:c4:feedback:v1:" + JSON.stringify([base, spec.session_id, spec.exposure_id, spec.decision_id]);
}
/** Only explicit submissions mutate the backend. Initialization and refresh are GET-only. */
export class FeedbackFlow {
  private state: FeedbackState = initial;
  private listeners = new Set<() => void>();
  private initialization: Promise<void> | null = null;
  private key: string;
  constructor(private readonly api: FeedbackApi, private readonly spec: Spec,
    private readonly storage: StoragePort | null, base: string) { this.key = feedbackStorageKey(base, spec); }
  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener); return () => { this.listeners.delete(listener); };
  };
  private update(patch: Partial<FeedbackState>) {
    this.state = { ...this.state, ...patch }; this.listeners.forEach((listener) => listener());
  }
  private save() {
    if (!writeStored(this.storage, this.key, JSON.stringify({ pending: this.state.pending, before: this.state.before }))) {
      this.update({ notice: "Browser storage is unavailable. Keep this page open to retain the exact unconfirmed request." });
    }
  }
  private async records() {
    const accepted = await this.api.accepted(this.spec);
    const correction = accepted ? await this.api.correction(this.spec, accepted) : null;
    const options = accepted && accepted.receipt.feedback.rating !== "about_right" ? await this.api.options(this.spec) : null;
    if (options && !options.feedback_eligible) throw new ContractError("Correction availability does not match the accepted feedback.");
    const decision = await this.api.decision(this.spec);
    const policy = await this.api.policy();
    if (decision.policy_run_id !== policy.policy_run_id || decision.feature_schema_fingerprint !== policy.feature_schema_fingerprint || decision.posterior_revision > policy.posterior_revision ||
        (accepted && accepted.receipt.selection_posterior_revision !== decision.posterior_revision)) {
      throw new ContractError("The decision, feedback and current policy schema or run differ.");
    }
    if (accepted && (accepted.receipt.policy_run_id !== policy.policy_run_id ||
        policy.posterior_revision < accepted.receipt.resulting_posterior_revision)) {
      throw new ContractError("Feedback and current shared policy state do not match.");
    }
    this.update({ accepted, correction, options, decision, policy, ready: true });
  }
  private reconcile() {
    const { pending, accepted, correction } = this.state;
    if (!pending) return;
    if (pending.kind === "rating" && accepted) {
      if (pending.request.rating !== accepted.receipt.feedback.rating) this.update({ error: "A different rating is already saved for this presentation. The saved rating was retained; no replacement was made." });
      this.update({ pending: null }); this.save();
    } else if (pending.kind === "correction" && correction) {
      if (JSON.stringify([...pending.request.reasons].sort()) !== JSON.stringify(correction.reasons)) this.update({ error: "Different correction reasons are already saved. The stored diagnostic was retained." });
      this.update({ pending: null }); this.save();
    } else if (pending.kind === "apply" && correction?.application) {
      if (pending.request.expected_revision !== correction.application.expected_revision) this.update({ error: "These preferences were already applied from another context revision. They were not applied again." });
      this.update({ pending: null }); this.save();
    }
  }
  initialize() { this.initialization ??= this.restore(); return this.initialization; }
  private async restore() {
    try {
      const raw = readStored(this.storage, this.key);
      if (raw) {
        try {
          const saved: unknown = JSON.parse(raw);
          if (!saved || typeof saved !== "object" || !("pending" in saved) || !("before" in saved)) throw new ContractError("Invalid saved feedback request.");
          this.update({ pending: saved.pending === null ? null : parsePending(saved.pending, this.spec),
            before: saved.before === null ? null : parsePolicy(saved.before) });
        } catch (error) {
          removeStored(this.storage, this.key);
          throw new Error("The saved feedback journal is invalid. Check saved records before submitting again.", { cause: error });
        }
      }
      await this.records(); this.reconcile();
    } catch (error) {
      this.update({ error: errorMessage(error), ready: false });
    } finally { this.update({ loading: false }); }
  }
  async refresh() {
    if (this.state.busy || this.state.loading) return;
    this.update({ busy: true, error: null });
    try { await this.records(); this.reconcile(); }
    catch (error) { this.update({ error: errorMessage(error), ready: false }); }
    finally { this.update({ busy: false }); }
  }
  async rate(rating: Rating, nav: Navigation | null) {
    if (!this.available() || this.state.accepted || !nav?.acknowledged || !nav.displayed_action_ids.length ||
        nav.exposure_id !== this.spec.exposure_id || nav.presentation_id !== this.spec.presentation_id ||
        nav.configuration_id !== this.spec.configuration.configuration_id || nav.graph_fingerprint !== this.spec.graph_fingerprint) return;
    // Lock before the pre-submission GET so double clicks cannot start two requests.
    this.update({ busy: true, error: null });
    try {
      const before = await this.api.policy();
      this.update({ before, pending: { kind: "rating", request: { ...attribution(this.spec), rating } } });
      this.save();
    } catch (error) { this.update({ error: errorMessage(error) }); }
    finally { this.update({ busy: false }); }
    if (this.state.pending) await this.retry();
  }
  async record(reasons: CorrectionCode[]) {
    if (!this.available() || !this.state.accepted || this.state.accepted.receipt.feedback.rating === "about_right" ||
        this.state.correction || !validReasons(reasons)) return;
    this.update({ pending: { kind: "correction", request: { ...attribution(this.spec), reasons: [...reasons].sort() } }, error: null });
    this.save(); await this.retry();
  }
  async apply() {
    if (!this.available() || !this.state.correction || this.state.correction.application) return;
    this.update({ busy: true, error: null });
    try {
      const options = await this.api.options(this.spec);
      this.update({ options, pending: { kind: "apply", request: { expected_revision: options.session_revision } } });
      this.save();
    } catch (error) { this.update({ error: errorMessage(error) }); }
    finally { this.update({ busy: false }); }
    if (this.state.pending) await this.retry();
  }
  private available() { return this.state.ready && !this.state.loading && !this.state.busy && !this.state.pending; }
  async retry() {
    const pending = this.state.pending;
    if (!pending || this.state.busy || this.state.loading || !this.state.ready) return;
    this.update({ busy: true, error: null });
    try {
      if (pending.kind === "rating") {
        this.update({ accepted: await this.api.rate(this.spec, pending.request) });
      } else {
        const accepted = this.state.accepted;
        if (!accepted) throw new ContractError("Accepted feedback must be loaded before correcting it.");
        const correction = pending.kind === "correction"
          ? await this.api.record(this.spec, accepted, pending.request)
          : await this.api.apply(this.spec, accepted, pending.request);
        this.update({ correction });
      }
      // Keep the request until read-back confirms attribution and model state.
      await this.records(); this.reconcile();
      if (this.state.pending) throw new ContractError("The submitted record was not confirmed by read-back.");
      this.update({ notice: "Saved records confirmed. Ratings, diagnostics and preference application remain separate." });
    } catch (error) {
      this.update({ error: errorMessage(error) + " The original request is retained for a safe retry." });
      if (error instanceof ApiError && error.status === 409) {
        try {
          await this.records(); this.reconcile();
          if (this.state.pending) { this.update({ pending: null }); this.save(); }
          this.update({ error: errorMessage(error) + " Current records are loaded. Review them before another explicit action; no conflicting value was substituted." });
        } catch { this.update({ ready: false }); }
      }
    } finally { this.update({ busy: false }); }
  }
  stopRetrying() {
    if (this.state.busy || this.state.loading) return;
    this.update({ pending: null, ready: false,
      notice: "Retry stopped locally. The server may already have saved the request. Check saved records before submitting again." });
    this.save();
  }
}
