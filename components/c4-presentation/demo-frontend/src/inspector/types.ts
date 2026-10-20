import type { Configuration, GuidanceStatus, Spec } from "../guidance/types";
import type { AdjustmentState } from "../adjustments/api";

export type RawRecord = Record<string, unknown>;
export interface TraceEntry {
  exposure_id: string; presentation_id: string; decision_id: string; graph_fingerprint: string;
  offered_at: string; configuration: Configuration; selection_posterior_revision: number;
  acknowledged: boolean; feedback_accepted: boolean;
}
export interface TraceIndex {
  schema_version: "c4-pipeline-trace-index-1.0"; current_guidance: GuidanceStatus;
  current_request_routing: "standard" | "adaptive";
  standard_guidance_history: "not_persisted_no_policy_or_learning_record";
  presentations: TraceEntry[]; explanation: string;
}
export interface TraceCandidate {
  configuration: Configuration; feasible: boolean; selected: boolean;
  satisfied: { code: string; message: string }[]; rejections: { code: string; message: string }[];
  score_status: "not_scored" | "recorded_moments_not_sampled" | "recorded_thompson_score";
  score: { configuration: Configuration; posterior_mean: number; posterior_std: number;
    sampling_std: number; sampled_score: number | null } | null;
}
export interface PipelineTrace {
  adjustments?: AdjustmentState | null;
  schema_version: "c4-pipeline-trace-1.0"; scope: "saved_adaptive_presentation";
  records: { presentation: Spec; policy_offer: { decision: RawRecord; offer: RawRecord };
    wording: RawRecord | null; wording_artifact: RawRecord | null; wording_style: "plain" | "extra_plain" | "concise" | null;
    acknowledgment: RawRecord | null; navigation_events: RawRecord[];
    feedback: RawRecord | null; correction: RawRecord | null };
  input: { graph_fingerprint: string; fingerprint_matches_saved_graph: boolean;
    graph_counts: Record<string, number>; raw_plan_payload: "not_stored";
    raw_enrichment_payload: "not_stored"; historical_validation_event: "not_recorded";
    source_authenticity: "synthetic" | "supplied_sources_unverified" };
  structural_features: { name: string; measurement: { observed: number;
    completeness: "complete" | "partial" | "unknown"; scale: number;
    exact_value: number | null; normalized_observed: number; normalized_exact: number | null } }[];
  content: { explanation_origin: "generated" | "fallback"; assurance: string;
    recorded_cache_hit: boolean; diagnostics: string[]; generated_item_count: number;
    source_copy_item_count: number; wording_status: "snapshot_not_available" | "snapshot_source_fallback" | "reviewed_snapshot" | "demo_mock_snapshot";
    wording_origins: string[]; wording_diagnostics: string[]; wording_digest: string | null };
  candidates: TraceCandidate[];
  selection: { policy_run_id: string; prior_version: string; prior_status: string;
    prior_digest: string | null; selection_mode: "cold_start_baseline" | "thompson" | "forced";
    selection_reason: string; selection_posterior_revision: number; feasible_count: number;
    rejected_count: number; sampled_candidate_count: number; feature_names: string[];
    context_encoding: [string, number][]; score_interpretation: "linear_surrogate_not_probability" };
  display: { status: "not_acknowledged" | "acknowledged"; displayed_action_ids: string[];
    current_action_id: string | null; navigation_event_count: number; interpretation: string };
  learning: { status: "awaiting_display_acknowledgment" | "no_accepted_feedback" | "accepted";
    reward: 0 | 1 | null; selection_posterior_revision: number;
    revision_immediately_before_update: number | null; resulting_posterior_revision: number | null;
    precision_rank_one_scale: number | null; centered_reward: number | null;
    linear_delta_b: number[] | null; effect_basis: string; historical_post_update_parameters: string;
    diagnostics_are_another_reward: false };
  current: { guidance: GuidanceStatus; user_settings: RawRecord; shared_policy_run_id: string;
    shared_posterior_revision: number; shared_posterior_fingerprint: string;
    accepted_feedback_count: number; stale_for_display: boolean };
  evidence_boundaries: { section: string; kind: "recorded" | "derived" | "unavailable";
    location: string; explanation: string }[];
}
