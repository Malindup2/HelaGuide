import type { GuestSession } from "../api/types";
import type { Spec } from "../guidance/types";

export const ratings = ["about_right", "need_more", "too_much"] as const;
export type Rating = typeof ratings[number];
export const correctionCodes = [
  "prefer_overview", "prefer_guided", "expand_supplementary", "collapse_supplementary",
  "show_recap", "hide_recap", "show_branch_map", "show_dependency_map", "show_parallel_map",
  "hide_diagram", "show_prerequisite_cues", "hide_prerequisite_cues",
] as const;
export type CorrectionCode = typeof correctionCodes[number];
export interface Attribution { presentation_id: string; configuration_id: string; decision_id: string }
export interface RatingRequest extends Attribution { rating: Rating }
export interface CorrectionRequest extends Attribution { reasons: CorrectionCode[] }
export interface PolicyStatus {
  policy_run_id: string; model_version: string; feedback_mode: "simulation" | "participant";
  feature_schema_version: string; feature_schema_fingerprint: string; feature_dimension: number;
  posterior_revision: number; posterior_fingerprint: string; accepted_feedback_count: number; storage: string;
}
export interface AcceptedFeedback {
  accepted_at: string;
  receipt: {
    feedback: { exposure_id: string; rating: Rating; origin: "simulation" | "participant_report" };
    policy_run_id: string; decision_id: string; acknowledgment_event_id: string;
    reward: 0 | 1; procedure_synthetic: boolean; selection_posterior_revision: number; resulting_posterior_revision: number;
  };
}
export interface CorrectionOption {
  code: CorrectionCode; label: string; dimension: string; value: string | boolean;
  selected_in_original: boolean; available_for_future: boolean; unavailable_reason: string | null;
}
export interface CorrectionOptions { session_revision: number; feedback_eligible: boolean; choices: CorrectionOption[] }
export interface CorrectionRecord extends Attribution {
  schema_version: "c4-correction-1.0"; session_id: string; exposure_id: string; graph_fingerprint: string;
  rating: "need_more" | "too_much"; origin: "simulation" | "participant_report";
  acknowledgment_event_id: string; feedback_posterior_revision: number; recorded_at: string; reasons: CorrectionCode[];
  application: {
    expected_revision: number; applied_at: string; before: GuestSession; after: GuestSession;
    preference_event_id: string | null;
  } | null;
}
export type PendingFeedback =
  | { kind: "rating"; request: RatingRequest }
  | { kind: "correction"; request: CorrectionRequest }
  | { kind: "apply"; request: { expected_revision: number } };

export const correctionValues: Record<CorrectionCode, [string, string | boolean]> = {
  prefer_overview: ["presentation_mode", "OVERVIEW"], prefer_guided: ["presentation_mode", "GUIDED"],
  expand_supplementary: ["progressive_disclosure", false], collapse_supplementary: ["progressive_disclosure", true],
  show_recap: ["previous_context_recap", true], hide_recap: ["previous_context_recap", false],
  show_branch_map: ["relationship_visual", "BRANCH_MAP"], show_dependency_map: ["relationship_visual", "DEPENDENCY_MAP"],
  show_parallel_map: ["relationship_visual", "PARALLEL_MAP"], hide_diagram: ["relationship_visual", "NONE"],
  show_prerequisite_cues: ["prerequisite_cue", true], hide_prerequisite_cues: ["prerequisite_cue", false],
};
export function attribution(spec: Spec): Attribution {
  return { presentation_id: spec.presentation_id, configuration_id: spec.configuration.configuration_id, decision_id: spec.decision_id };
}

export interface DecisionSummary {
  decision_id: string; policy_run_id: string; posterior_revision: number;
  selection_mode: "cold_start_baseline" | "thompson" | "forced";
  feature_dimension: number; feature_schema_version: string; feature_schema_fingerprint: string;
}
