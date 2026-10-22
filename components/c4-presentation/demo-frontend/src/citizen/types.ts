/** Typed view of the documented c4-guidance-api-1.0 contract (docs/FRONTEND-API-CHECKPOINT.md). */

export type Navigation = 'overview' | 'guided';
export interface Configuration {
  navigation: Navigation; explanation: 'concise' | 'detailed'; disclosure: 'off' | 'on';
  relationships: 'none' | 'inline' | 'map'; recap: 'off' | 'on'; segmentation: 'off' | 'on';
}
export type Dimension = keyof Configuration;
export type SelectionKind = 'standard' | 'constraint_standard' | 'research_preview' | 'manual_adjustment' | 'shared_gaussian_lints';

export interface PolicyEvidence {
  algorithm: string; action_schema: string; encoder_schema: string; model_manifest_fingerprint: string;
  policy_run_id: string; posterior_revision: number; decision_id: string; training_provenance: string;
}
export interface Selection {
  kind: SelectionKind; configuration: Configuration; action_schema: string; label: string;
  scoring_status: 'not_run' | 'executed'; policy: PolicyEvidence | null; learning_eligible: boolean; explanation: string;
}
export interface SourceReview { reviewer: string; reviewed_at: string; scope_note: string; independent_government_validation: boolean }
export interface Preparation {
  content_state: string; preparation_state: string; job_state: string | null; job_id: string | null; error_code: string | null;
  generation_enabled: boolean; mode: string; language: string; fallback_language: string | null; content_schema: string;
  artifact_id: string | null; review_kind: string | null; source_kind: string; content_origin: string; source_review: SourceReview | null;
}

export interface FactBody { kind: 'fee' | 'document'; fact_id: string; name?: string; value?: number; currency?: string }
export interface SourcePassage { content_id: string; text: string; evidence_ids: string[] }
export interface ScopedFact {
  id: string; fact_id: string; fact: FactBody; scope: 'action' | 'route' | 'stage' | 'service';
  action_id: string | null; stage_id: string | null; service_id: string | null; branch_id: string | null;
  option_ids: string[]; condition_ids: string[]; claim_ids: string[]; evidence_ids: string[];
  qualification: string | null; role?: string | null; conditions: string[]; status: 'draft' | 'reviewed' | 'source_fallback';
  source_context?: SourcePassage[]; applicability_status?: 'structured_conditions' | 'consult_source_context';
}
export interface RenderedAction {
  id: string; heading: string; essential: string; conditions: string[]; actor: string | null; destination: string | null;
  facts: ScopedFact[]; explanation_visible: string | null; explanation_hidden: string | null; recap: null;
  branch: string | null; option: string | null; service_id: string; agency: string; condition_ids: string[];
  source_content_ids: string[]; disclosure_available: boolean; wording_status: string;
  /** Content 3.1 only: the exact source text kept alongside the primary explanation, and the role of the separate supplement. */
  source_wording?: string | null; supplement_role?: string | null;
}
export interface RouteOption { option_id: string; action_ids: string[]; condition_ids: string[]; conditions: string[]; label: string }
export interface Route { branch_id: string; selection: 'AND' | 'OR' | 'XOR'; evidence_ids: string[]; choice_is_not_eligibility_or_completion: true; options: RouteOption[] }
export interface Text { text: string; status?: string; claim_ids?: string[]; evidence_ids?: string[] }
export interface Phase { id: string; label: Text; action_ids: string[]; basis: string; why_grouped: string; adds_orientation?: boolean; evidence_ids: string[]; branch_split_note?: string | null }
export interface Expression { kind: 'action' | 'all_of' | 'any_of' | 'selected_option_of'; ref: string | null; children: Expression[] }
export interface RelationCue { kind: string; text: string; evidence_ids: string[]; relation_id: string }
export interface Edge { edge_id?: string; kind?: string; source_id: string; target_id: string; evidence_ids?: string[] }
export interface ProcessMap {
  labels: Record<string, string>; edges: Edge[]; joins: { target: string; requirement: Expression; evidence_ids: string[] }[];
  branches: { group_id: string; selection: string; options: { option_id: string; action_ids: string[]; condition_ids: string[] }[] }[];
  parallel: { group_id: string; action_ids: string[] }[]; parallel_areas: Expression[][];
  stages: { service_id: string; name: string; agency: string }[]; text_equivalent: string[];
}
export interface RelationshipAid {
  mode: Configuration['relationships']; inline_by_action: Record<string, RelationCue[]>; map: ProcessMap | null;
  essential_relationships_remain_in_instructions: true;
}
export interface NavigationEntry {
  action_id: string; layer: number | null; label: string | null; branch_id: string | null; option_id: string | null;
  route_layer: number | null; available_for_navigation: boolean; orientation_only: true;
}
export interface NavigationState {
  mode: Navigation; entries: NavigationEntry[]; active_action_id: string | null; browsing_action_ids: string[];
  previous_action_id: string | null; next_action_id: string | null; browsing_position: number | null; browsing_count: number;
  unresolved_route_ids: string[]; numbering_enabled: boolean; order_semantics: string;
}
export interface RecapItem {
  action_id: string; text: string; viewed_not_completed: true;
  evidence: { event_id: string; kind: 'navigate' | 'step_open' | 'step_visible'; view_id: string; sequence: number };
}
export interface RecapState { enabled: boolean; items: RecapItem[]; empty_reason: string | null; label: string }
export interface Interaction {
  navigation: NavigationState; route_choices: Record<string, string[]>; map_visible: boolean;
  explanation_open_action_ids: string[]; display_acknowledged_view_ids: string[]; recap: RecapState;
  event_count: number; completion_tracked: false;
}
export interface Requirements { documents: ScopedFact[]; fees: ScopedFact[]; total: null; no_total_reason: string; placement: string }
export interface Doc {
  schema: string; content_schema?: string; configuration: Configuration; synthetic: boolean; source_kind: string; source_limit: string;
  actions: RenderedAction[]; facts: ScopedFact[]; branches: unknown[];
  stages: { service_id: string; display_order: number; name: string; agency: string; fee_fact_id: string; document_fact_ids: string[] }[];
  completeness: Record<string, string>; sources: { evidence_id: string; kind: string; source_url: string; text: string; retrieved_at: string | null }[];
  conditions: { condition_id: string; text: string }[]; map_labels: Record<string, string>; phases: Phase[]; phase_order: string[];
  supplementary: unknown[]; required_source_notes: string[]; relationship_aid: RelationshipAid; navigation: NavigationState;
  routes: Route[]; requirements: Requirements;
}
export interface Candidate { id: string; configuration: Configuration; feasible: boolean; reasons: string[]; disclosable_action_ids: string[] }
export interface Availability { action_schema: string; nominal_count: number; feasible_count: number; candidates: Candidate[]; feasibility_fingerprint?: string | null }
export interface EffectiveContext {
  schema_version: string; session_id: string; profile_id: string | null; personalization_enabled: boolean; service_id: string;
  familiarity: number | null; confidence: number | null; preferences: Record<string, string>;
  constraints: { locks: Record<string, string>; no_guided: boolean; no_map: boolean; no_disclosure: boolean };
  revision: { identity: number; revised: number }; sources: Record<string, string>; scoring_use: string;
  legacy: { hard_requirements_unresolved: boolean; preferences_not_imported: Record<string, unknown>; pending_preference_review: Record<string, unknown> };
}
export interface Controls { configuration_adjustment: boolean; feedback: boolean; research_inspection: boolean }
export interface GuidanceResponse {
  schema_version: string; journey_id: string; view_id: string; parent_view_id: string | null; session_id: string; procedure_id: string;
  procedure_title: string; created_at: string; selection: Selection; preparation: Preparation; effective_context: EffectiveContext;
  availability: Availability; document: Doc; interaction: Interaction; controls: Controls;
}
export interface Receipt { event_id: string; sequence: number; server_timestamp: string; reward: 0 | 1 | null; policy_updated: boolean; learning_eligible: boolean }
export interface ApiStatus {
  /** Procedures that have DEMO-ONLY provisional wording available in research previews (empty unless the server enables the mode). */
  demo_provisional_content?: string[];
  /** Procedures whose cached wording the project owner accepted for this local demonstration (ordinary journeys use it). */
  demo_accepted_content?: string[];
  schema_version: string; action_schema: string; nominal_configuration_count: number; standard_guidance_available: boolean;
  research_previews_enabled: boolean; personalized_selection_available: boolean; encoder_status: string; policy: unknown;
  history_adjustment: string; pp1_remaining_requirements: string[];
  visibility_policy: { version: string; min_visible_ratio: number; min_dwell_ms: number } | null;
}
export interface ProcedureInfo {
  procedure_id: string; service_id: string; title: string; synthetic: boolean; source_origin: string; source_limit: string;
  graph_fingerprint: string; completeness: Record<string, string>;
}
export type EventType = 'view_displayed' | 'step_visible' | 'navigate' | 'step_open' | 'viewport_changed' | 'explanation_open'
  | 'explanation_close' | 'route_focus' | 'map_show' | 'map_hide' | 'map_expand' | 'map_collapse' | 'recap_open' | 'recap_close'
  | 'overview_peek' | 'source_open';
export interface EventBody {
  type: EventType; action_id?: string | null; action_ids?: string[]; branch_id?: string | null; option_ids?: string[]; source_id?: string | null;
  visible_ratio?: number | null; dwell_ms?: number | null; instrumentation_version?: string | null;
}
export type RatingReason = 'too_much_explanation' | 'not_enough_explanation' | 'navigation_difficult' | 'diagram_confusing' | 'requirements_hard_to_find' | 'other';
export interface InspectorRecord {
  schema_version: string; record_kind: string; journey_id: string; created_at: string; source_graph_fingerprint: string; content_fingerprint: string;
  effective_context: EffectiveContext; measurements: Record<string, unknown>; availability: Availability;
  views: { id: string; parent_view_id: string | null; created_at: string; selection: Selection }[];
  events: { type: string; view_id: string; sequence?: number; server_timestamp?: string; payload?: Record<string, unknown>; qualifies_for_recap?: boolean; rating?: string; reasons?: string[] }[];
  features: unknown; sampled_scores: unknown; policy: unknown; posterior_updates: number; scoring_status: string;
  pp2_history_adjustment: string; visibility_policy: unknown; note: string;
}

export interface Interval { mean: number; ci95_half_width: number | null; n_seeds: number; min: number; max: number }
export type RewardBlock = Record<'reward' | 'regret' | 'standard' | 'minimal' | 'maximal' | 'fixed_best' | 'random' | 'oracle', Interval> & { greedy?: Interval };
export interface LearningAggregate {
  variant: string; training_assumption: string; episode: number; n_seeds: number;
  dev: Record<string, RewardBlock | Interval | number> & { balanced: RewardBlock }; test: Record<string, RewardBlock | Interval | number> & { balanced: RewardBlock };
}
/** Completed synthetic study (c4-pp1-experiment-3.1). Synthetic evaluation only; never real-citizen evidence. */
export interface LearningReport {
  schema: string; label: string; feature_schema: string; seeds: number[]; budgets_per_independent_run: number[]; limitations: string[];
  splits: { train_procedures: string[]; dev_procedures: string[]; test_unseen_procedures: string[]; dev_cases: number; test_cases: number };
  simulator: { schema: string; assumptions: Record<string, { note: string }> }; aggregates: LearningAggregate[];
}
