import { api, ApiError, ContractError } from "../api/client";
import type { C4Api } from "../api/client";
import type { Spec } from "../guidance/types";
import { parseAccepted, parseCorrection, parseOptions, parsePolicy } from "./contracts";
import type { AcceptedFeedback, CorrectionRequest, DecisionSummary, RatingRequest } from "./types";
export class FeedbackApi {
  constructor(private readonly transport: Pick<C4Api, "request"> = api) {}
  private path(spec: Spec) {
    return "/dev/v1/sessions/" + encodeURIComponent(spec.session_id) + "/presentations/" + encodeURIComponent(spec.exposure_id);
  }
  async decision(spec: Spec): Promise<DecisionSummary> {
    const value = await this.transport.request(this.path(spec) + "/inspector", "GET");
    if (!value || typeof value !== "object" || !("decision" in value) || !("offer" in value)) throw new ContractError("Missing decision attribution.");
    const d = value.decision; const o = value.offer;
    if (!d || typeof d !== "object" || !o || typeof o !== "object" ||
      !("decision_id" in d) || d.decision_id !== spec.decision_id ||
      !("session_id" in o) || o.session_id !== spec.session_id ||
      !("exposure_id" in o) || o.exposure_id !== spec.exposure_id ||
      !("graph_fingerprint" in o) || o.graph_fingerprint !== spec.graph_fingerprint ||
      !("configuration" in d) || !d.configuration || typeof d.configuration !== "object" ||
      !("configuration_id" in d.configuration) || d.configuration.configuration_id !== spec.configuration.configuration_id ||
      !("posterior_revision" in d) || !Number.isSafeInteger(d.posterior_revision) || Number(d.posterior_revision) < 0 ||
      !("policy_run_id" in d) || typeof d.policy_run_id !== "string" ||
      !("feature_dimension" in d) || d.feature_dimension !== 656 ||
      !("feature_schema_version" in d) || typeof d.feature_schema_version !== "string" ||
      !("feature_schema_fingerprint" in d) || typeof d.feature_schema_fingerprint !== "string" ||
      !("selection_mode" in d) || !["cold_start_baseline", "thompson", "forced"].includes(String(d.selection_mode))) {
      throw new ContractError("Decision diagnostics do not match this presentation.");
    }
    return d as unknown as DecisionSummary;
  }
  async policy() { return parsePolicy(await this.transport.request("/dev/v1/policy", "GET")); }
  async accepted(spec: Spec) {
    try { return parseAccepted(await this.transport.request(this.path(spec) + "/feedback", "GET"), spec); }
    catch (error) { if (error instanceof ApiError && error.status === 404) return null; throw error; }
  }
  async rate(spec: Spec, request: RatingRequest) {
    return parseAccepted(await this.transport.request(this.path(spec) + "/feedback", "POST", undefined, request), spec);
  }
  async options(spec: Spec) { return parseOptions(await this.transport.request(this.path(spec) + "/correction-options", "GET"), spec); }
  async correction(spec: Spec, accepted: AcceptedFeedback) {
    try { return parseCorrection(await this.transport.request(this.path(spec) + "/correction", "GET"), spec, accepted); }
    catch (error) { if (error instanceof ApiError && error.status === 404) return null; throw error; }
  }
  async record(spec: Spec, accepted: AcceptedFeedback, request: CorrectionRequest) {
    return parseCorrection(await this.transport.request(this.path(spec) + "/correction", "POST", undefined, request), spec, accepted);
  }
  async apply(spec: Spec, accepted: AcceptedFeedback, request: { expected_revision: number }) {
    return parseCorrection(await this.transport.request(this.path(spec) + "/correction/apply", "POST", undefined, request), spec, accepted);
  }
}
export const feedbackApi = new FeedbackApi();
