import { ContractError, parseSession } from "../api/client";
import type { Spec } from "../guidance/types";
import { correctionCodes, correctionValues, ratings } from "./types";
import type { AcceptedFeedback, CorrectionOptions, CorrectionRecord, PendingFeedback, PolicyStatus } from "./types";
function check(value: unknown, message: string): asserts value {
  if (!value) throw new ContractError("Invalid feedback record: " + message);
}
function obj(value: unknown): asserts value is Record<string, unknown> {
  check(!!value && typeof value === "object" && !Array.isArray(value), "expected object");
}
function text(value: unknown): asserts value is string { check(typeof value === "string" && value.length > 0, "missing text"); }
function revision(value: unknown) { check(Number.isSafeInteger(value) && Number(value) >= 0, "invalid revision"); }
function time(value: unknown) { text(value); check(Number.isFinite(Date.parse(value)), "invalid timestamp"); }
export function parsePolicy(value: unknown): PolicyStatus {
  obj(value);
  for (const field of ["policy_run_id", "model_version", "feature_schema_version", "feature_schema_fingerprint", "posterior_fingerprint", "storage"]) text(value[field]);
  check(value.feature_dimension === 656, "unsupported policy feature dimension");
  check(value.feedback_mode === "simulation" || value.feedback_mode === "participant", "unknown feedback mode");
  revision(value.posterior_revision); revision(value.accepted_feedback_count);
  return value as unknown as PolicyStatus;
}
export function parseAccepted(value: unknown, spec: Spec): AcceptedFeedback {
  obj(value); time(value.accepted_at); obj(value.receipt);
  const r = value.receipt; obj(r.feedback);
  check(r.feedback.exposure_id === spec.exposure_id && r.decision_id === spec.decision_id, "wrong exposure or decision");
  check(ratings.includes(r.feedback.rating as never), "unknown rating");
  check(r.feedback.origin === "simulation" || r.feedback.origin === "participant_report", "unknown feedback origin");
  text(r.policy_run_id); text(r.acknowledgment_event_id);
  check(r.reward === (r.feedback.rating === "about_right" ? 1 : 0), "incorrect support-fit reward");
  check(r.procedure_synthetic === spec.explanation.source.graph.synthetic, "wrong source classification");
  revision(r.selection_posterior_revision); revision(r.resulting_posterior_revision);
  check(Number(r.resulting_posterior_revision) > Number(r.selection_posterior_revision), "invalid learning revision");
  return value as unknown as AcceptedFeedback;
}
export function parseOptions(value: unknown, spec: Spec): CorrectionOptions {
  obj(value); revision(value.session_revision); check(typeof value.feedback_eligible === "boolean", "invalid correction eligibility");
  check(Array.isArray(value.choices), "missing correction choices");
  const seen = new Set<string>();
  for (const choice of value.choices) {
    obj(choice);
    check(correctionCodes.includes(choice.code as never), "unknown correction code");
    const code = choice.code as keyof typeof correctionValues;
    const [dimension, setting] = correctionValues[code];
    check(choice.dimension === dimension && choice.value === setting && !seen.has(code), "incorrect or duplicate correction mapping");
    seen.add(code); text(choice.label);
    check(typeof choice.available_for_future === "boolean" && typeof choice.selected_in_original === "boolean", "missing availability");
    check(choice.selected_in_original === (spec.configuration[dimension as keyof typeof spec.configuration] === setting), "wrong original scaffold value");
    check(choice.unavailable_reason === null || typeof choice.unavailable_reason === "string", "invalid availability reason");
  }
  check(seen.size === correctionCodes.length, "incomplete correction catalogue");
  return value as unknown as CorrectionOptions;
}
export function parseCorrection(value: unknown, spec: Spec, feedback: AcceptedFeedback): CorrectionRecord {
  obj(value);
  check(value.schema_version === "c4-correction-1.0" && value.session_id === spec.session_id &&
    value.exposure_id === spec.exposure_id && value.presentation_id === spec.presentation_id &&
    value.configuration_id === spec.configuration.configuration_id && value.decision_id === spec.decision_id &&
    value.graph_fingerprint === spec.graph_fingerprint, "wrong correction attribution");
  const receipt = feedback.receipt;
  check(value.rating !== "about_right" && value.rating === receipt.feedback.rating && value.origin === receipt.feedback.origin &&
    value.acknowledgment_event_id === receipt.acknowledgment_event_id &&
    value.feedback_posterior_revision === receipt.resulting_posterior_revision, "correction differs from feedback");
  time(value.recorded_at); check(validReasons(value.reasons), "invalid correction reasons");
  check(JSON.stringify(value.reasons) === JSON.stringify([...value.reasons].sort()), "noncanonical correction reasons");
  if (value.application !== null) {
    obj(value.application); const a = value.application; revision(a.expected_revision); time(a.applied_at);
    const before = parseSession(a.before); const after = parseSession(a.after);
    check(before.session_id === spec.session_id && after.session_id === spec.session_id && a.expected_revision === before.revision, "wrong preference application context");
    const expected = structuredClone(before.settings);
    for (const code of value.reasons) {
      const [dimension, setting] = correctionValues[code];
      Object.assign(expected.preferences, { [dimension]: setting });
    }
    check(JSON.stringify(after.settings) === JSON.stringify(expected), "preference application changed unrelated settings");
    check(after.revision === before.revision || after.revision === before.revision + 1, "invalid context transition");
    check(a.preference_event_id === null || typeof a.preference_event_id === "string", "invalid preference event");
  }
  return value as unknown as CorrectionRecord;
}
export function validReasons(value: unknown): value is (keyof typeof correctionValues)[] {
  if (!Array.isArray(value) || value.length < 1 || value.length > 5) return false;
  const dimensions = new Set<string>();
  for (const code of value) {
    if (!correctionCodes.includes(code)) return false;
    const dimension = correctionValues[code as keyof typeof correctionValues][0];
    if (dimensions.has(dimension)) return false;
    dimensions.add(dimension);
  }
  return true;
}
export function parsePending(value: unknown, spec: Spec): PendingFeedback {
  obj(value); obj(value.request); const r = value.request;
  if (value.kind === "apply") revision(r.expected_revision);
  else {
    check(r.presentation_id === spec.presentation_id && r.configuration_id === spec.configuration.configuration_id &&
      r.decision_id === spec.decision_id, "wrong pending request attribution");
    if (value.kind === "rating") check(ratings.includes(r.rating as never), "unknown pending rating");
    else check(value.kind === "correction" && validReasons(r.reasons), "invalid pending correction");
  }
  return value as unknown as PendingFeedback;
}
