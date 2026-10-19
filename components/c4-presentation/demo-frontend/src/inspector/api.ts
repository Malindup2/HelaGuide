import { C4Api, ContractError } from "../api/client";
import { parseSpec, parseStatus } from "../guidance/contracts";
import type { Configuration } from "../guidance/types";
import type { PipelineTrace, TraceIndex } from "./types";

type Obj = Record<string, unknown>;
const object = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const finite = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const count = (v: unknown) => finite(v) && Number.isInteger(v) && v >= 0;
const strings = (v: unknown): v is string[] => Array.isArray(v) && v.every(x => typeof x === "string");
const nullableNumber = (v: unknown) => v === null || finite(v);
const nullableText = (v: unknown) => v === null || typeof v === "string";
function check(v: unknown, message: string): asserts v {
  if (!v) throw new ContractError("Invalid pipeline trace: " + message);
}
function config(v: unknown): Configuration {
  check(object(v), "configuration missing");
  check(["OVERVIEW", "GUIDED"].includes(String(v.presentation_mode)) &&
    ["NONE", "BRANCH_MAP", "DEPENDENCY_MAP", "PARALLEL_MAP"].includes(String(v.relationship_visual)) &&
    [v.progressive_disclosure, v.previous_context_recap, v.prerequisite_cue].every(x => typeof x === "boolean"), "configuration fields");
  const expected = `c4-scaffold-v1:${v.presentation_mode}:pd${Number(v.progressive_disclosure)}:recap${Number(v.previous_context_recap)}:${v.relationship_visual}:cue${Number(v.prerequisite_cue)}`;
  check(v.configuration_id === expected, "configuration identity");
  return v as unknown as Configuration;
}
export function parseTraceIndex(value: unknown, sid: string): TraceIndex {
  check(object(value) && value.schema_version === "c4-pipeline-trace-index-1.0", "index version");
  const status = parseStatus(value.current_guidance);
  check(status.session_id === sid && value.current_request_routing === (status.personalization_enabled ? "adaptive" : "standard") &&
    value.standard_guidance_history === "not_persisted_no_policy_or_learning_record" && typeof value.explanation === "string", "index scope");
  check(Array.isArray(value.presentations), "presentation list");
  for (const entry of value.presentations) {
    check(object(entry) && [entry.exposure_id, entry.presentation_id, entry.decision_id, entry.graph_fingerprint].every(x => typeof x === "string") &&
      typeof entry.offered_at === "string" && Number.isFinite(Date.parse(entry.offered_at)) &&
      count(entry.selection_posterior_revision) && typeof entry.acknowledged === "boolean" && typeof entry.feedback_accepted === "boolean", "index entry");
    config(entry.configuration);
  }
  check(new Set(value.presentations.map(x => x.exposure_id)).size === value.presentations.length, "duplicate presentations");
  return value as unknown as TraceIndex;
}
export function parseTrace(value: unknown, sid: string, eid: string): PipelineTrace {
  check(object(value) && value.schema_version === "c4-pipeline-trace-1.0" && value.scope === "saved_adaptive_presentation", "version or scope");
  check(object(value.records), "records missing");
  const r = value.records;
  const spec = parseSpec(r.presentation);
  check(spec.session_id === sid && spec.exposure_id === eid, "presentation belongs to another session or exposure");
  check(object(r.policy_offer) && object(r.policy_offer.decision) && object(r.policy_offer.offer), "policy records");
  check(r.policy_offer.decision.decision_id === spec.decision_id && r.policy_offer.offer.exposure_id === eid && r.policy_offer.offer.session_id === sid, "decision attribution");
  for (const key of ["wording", "wording_artifact", "acknowledgment", "feedback", "correction"]) check(r[key] === null || object(r[key]), key);
  check(r.wording_style === null || ["plain", "extra_plain", "concise"].includes(String(r.wording_style)), "wording style");
  check(Array.isArray(r.navigation_events) && r.navigation_events.every(object), "navigation events");
  check(object(value.input) && value.input.graph_fingerprint === spec.graph_fingerprint && value.input.fingerprint_matches_saved_graph === true &&
    object(value.input.graph_counts) && Object.values(value.input.graph_counts).every(count) &&
    ["synthetic", "supplied_sources_unverified"].includes(String(value.input.source_authenticity)) &&
    value.input.raw_plan_payload === "not_stored" && value.input.raw_enrichment_payload === "not_stored" && value.input.historical_validation_event === "not_recorded", "input");
  const featureNames = ["step_count", "information_volume", "branch_count", "condition_count", "dependency_count", "dependency_depth", "parallel_group_count"];
  check(Array.isArray(value.structural_features) && value.structural_features.length === 7, "seven structural measurements");
  for (const [i, f] of value.structural_features.entries()) {
    check(object(f) && f.name === featureNames[i] && object(f.measurement), "feature name");
    const m = f.measurement;
    check(count(m.observed) && finite(m.scale) && m.scale > 0 && ["complete", "partial", "unknown"].includes(String(m.completeness)) &&
      finite(m.normalized_observed) && (m.completeness === "complete" ? m.exact_value === m.observed && finite(m.normalized_exact) : m.exact_value === null && m.normalized_exact === null), "feature completeness");
  }
  check(object(value.content), "content");
  const c = value.content;
  check(["generated", "fallback"].includes(String(c.explanation_origin)) && typeof c.assurance === "string" && typeof c.recorded_cache_hit === "boolean" &&
    count(c.generated_item_count) && count(c.source_copy_item_count) && strings(c.diagnostics) && strings(c.wording_origins) && strings(c.wording_diagnostics) &&
    ["snapshot_not_available", "snapshot_source_fallback", "reviewed_snapshot"].includes(String(c.wording_status)) && nullableText(c.wording_digest), "content provenance");
  check(object(value.selection), "selection");
  const s = value.selection;
  check(["thompson", "forced", "cold_start_baseline"].includes(String(s.selection_mode)) &&
    [s.policy_run_id, s.prior_version, s.prior_status, s.selection_reason].every(x => typeof x === "string") && nullableText(s.prior_digest) &&
    [s.selection_posterior_revision, s.feasible_count, s.rejected_count, s.sampled_candidate_count].every(count) && strings(s.feature_names) && s.feature_names.length === 656 &&
    Array.isArray(s.context_encoding) && s.context_encoding.length === 81 && s.context_encoding.every(x => Array.isArray(x) && x.length === 2 && typeof x[0] === "string" && finite(x[1])) &&
    s.score_interpretation === "linear_surrogate_not_probability" && r.policy_offer.decision.policy_run_id === s.policy_run_id && r.policy_offer.decision.posterior_revision === s.selection_posterior_revision, "selection metadata");
  check(Array.isArray(value.candidates) && value.candidates.length === 64, "64 candidates");
  for (const candidate of value.candidates) {
    check(object(candidate) && typeof candidate.feasible === "boolean" && typeof candidate.selected === "boolean", "candidate");
    const cfg = config(candidate.configuration);
    for (const key of ["satisfied", "rejections"]) check(Array.isArray(candidate[key]) && candidate[key].every(x => object(x) && typeof x.code === "string" && typeof x.message === "string"), "candidate reasons");
    check(candidate.feasible === ((candidate.rejections as unknown[]).length === 0), "candidate feasibility");
    check(candidate.selected === (cfg.configuration_id === spec.configuration.configuration_id), "selected configuration");
    if (!candidate.feasible) check(candidate.score === null && candidate.score_status === "not_scored" && !candidate.selected, "rejected candidate must be unscored");
    else {
      const score = candidate.score;
      check(object(score) && config(score.configuration).configuration_id === cfg.configuration_id && finite(score.posterior_mean) && finite(score.posterior_std) && score.posterior_std >= 0 && finite(score.sampling_std) && score.sampling_std >= 0 && nullableNumber(score.sampled_score), "candidate score");
      check(candidate.score_status === (score.sampled_score === null ? "recorded_moments_not_sampled" : "recorded_thompson_score"), "score availability");
    }
  }
  check(new Set(value.candidates.map(x => config(x.configuration).configuration_id)).size === 64 && value.candidates.filter(x => x.selected).length === 1 &&
    value.candidates.filter(x => x.feasible).length === s.feasible_count && 64 - Number(s.feasible_count) === s.rejected_count &&
    value.candidates.filter(x => object(x.score) && x.score.sampled_score !== null).length === s.sampled_candidate_count, "candidate totals");
  check(object(value.display) && ["not_acknowledged", "acknowledged"].includes(String(value.display.status)) && strings(value.display.displayed_action_ids) &&
    nullableText(value.display.current_action_id) && count(value.display.navigation_event_count) && value.display.interpretation === "client_display_acknowledgment_not_reading_or_completion", "display");
  check(object(value.learning), "learning");
  const l = value.learning;
  check(["awaiting_display_acknowledgment", "no_accepted_feedback", "accepted"].includes(String(l.status)) && l.selection_posterior_revision === s.selection_posterior_revision && l.diagnostics_are_another_reward === false &&
    l.effect_basis === "derived_from_original_phi_and_recorded_receipt" && l.historical_post_update_parameters === "not_separately_stored", "learning interpretation");
  if (l.status === "accepted") check((l.reward === 0 || l.reward === 1) && count(l.revision_immediately_before_update) && count(l.resulting_posterior_revision) &&
    Number(l.resulting_posterior_revision) === Number(l.revision_immediately_before_update) + 1 && finite(l.centered_reward) && finite(l.precision_rank_one_scale) &&
    Array.isArray(l.linear_delta_b) && l.linear_delta_b.length === 656 && l.linear_delta_b.every(finite) && object(r.feedback), "accepted reward update");
  else check([l.reward, l.revision_immediately_before_update, l.resulting_posterior_revision, l.centered_reward, l.precision_rank_one_scale, l.linear_delta_b, r.feedback].every(x => x === null), "absent reward is not zero");
  check(object(value.current) && object(value.current.user_settings) && typeof value.current.stale_for_display === "boolean" &&
    typeof value.current.shared_policy_run_id === "string" && typeof value.current.shared_posterior_fingerprint === "string" && count(value.current.shared_posterior_revision) && count(value.current.accepted_feedback_count), "current model");
  check(parseStatus(value.current.guidance).session_id === sid, "current session");
  check(Array.isArray(value.evidence_boundaries) && value.evidence_boundaries.length > 0 && value.evidence_boundaries.every(x => object(x) &&
    ["recorded", "derived", "unavailable"].includes(String(x.kind)) && [x.section, x.location, x.explanation].every(v => typeof v === "string")), "evidence boundaries");
  return value as unknown as PipelineTrace;
}

/** Deliberately exposes only GET operations. No citizen episode controller is used. */
export class InspectorApi {
  constructor(private readonly client = new C4Api()) {}
  profiles() { return this.client.profiles(); }
  async index(sid: string) {
    return parseTraceIndex(await this.client.request(`/dev/v1/sessions/${encodeURIComponent(sid)}/pipeline-traces`, "GET"), sid);
  }
  async trace(sid: string, eid: string) {
    return parseTrace(await this.client.request(`/dev/v1/sessions/${encodeURIComponent(sid)}/presentations/${encodeURIComponent(eid)}/pipeline-trace`, "GET"), sid, eid);
  }
}
