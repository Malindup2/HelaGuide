import type { PresentationMode, RelationshipVisual } from "../api/types";

export interface Item { kind: string; identifier: string }
export interface Card { source: Item; title: string; lines: string[]; collapsed: boolean }
export interface Page {
  action_id: string; service_id: string; items: Item[]; condition_ids: string[];
  branch_group_id: string | null; branch_option_id: string | null; prerequisite_cues: Item[];
}
export interface Stage { service_id: string; name: string; agency: string; fee_fact_id: string; document_fact_ids: string[] }
export interface Action { action_id: string; service_id: string; required_content_ids: string[]; supplementary_content_ids: string[] }
export interface Edge { edge_id: string; source_id: string; target_id: string }
export interface Branch {
  group_id: string; service_id: string; selection: "AND" | "OR" | "XOR";
  options: { option_id: string; action_ids: string[]; condition_ids: string[] }[];
}
export interface Parallel { group_id: string; service_id: string; action_ids: string[] }
export interface Graph {
  synthetic: boolean; disclaimer: string; stages: Stage[]; actions: Action[];
  content: { content_id: string; text: string; role: "required" | "supplementary" }[];
  conditions: { condition_id: string; text: string }[];
  stage_dependencies: Edge[]; action_prerequisites: Edge[];
  branch_groups: Branch[]; parallel_groups: Parallel[];
}
export interface Diagram {
  kind: RelationshipVisual; stages: Stage[]; actions: Action[];
  stage_dependencies: Edge[]; action_prerequisites: Edge[];
  branch_groups: Branch[]; parallel_groups: Parallel[];
}
export interface Explanation {
  graph_fingerprint: string; origin: "generated" | "fallback"; source_status: string; assurance: string;
  source: {
    graph: Graph;
    preservation: { always_visible: Item[]; collapsible_content_ids: string[] };
  };
  explanations: {
    unit_id: string; action_id: string; content_id: string; origin: "generated" | "source_copy";
    text: string; fact_ids: string[]; evidence_ids: string[];
    citations: { evidence_id: string; quote: string }[];
  }[];
}
export interface Document {
  graph_fingerprint: string; cards: Card[]; global_items: Item[]; pages: Page[];
  explanation: Explanation; visibility: { visible: Item[]; collapsed: Item[] };
  navigation_semantics: "browsing_order_not_completion_or_eligibility";
}
export interface Configuration {
  presentation_mode: PresentationMode; progressive_disclosure: boolean;
  previous_context_recap: boolean; relationship_visual: RelationshipVisual;
  prerequisite_cue: boolean; configuration_id: string;
}
export interface Spec extends Document {
  schema_version: "c4-presentation-1.0"; presentation_id: string; session_id: string;
  exposure_id: string; decision_id: string; context_revision: number; configuration: Configuration;
  initial_action_id: string | null; acknowledgment_action_ids: string[]; diagram: Diagram;
  recap: { action_ids: string[]; exposure_ids: string[]; meaning: "previously_displayed_not_completed" } | null;
  text_format: "plain_text";
}
export interface Standard extends Document {
  schema_version: "c4-standard-guidance-1.0"; standard_id: string; presentation_mode: "OVERVIEW";
  personalization_applied: false; exposure_acknowledgment_required: false; learning_eligible: false;
  writing_style: "plain" | "extra_plain" | "concise";
}
export interface GuidanceStatus {
  session_id: string; session_revision: number; profile_id: string | null;
  profile_revision: number | null; personalization_enabled: boolean;
}
export type Guidance =
  | (GuidanceStatus & { mode: "standard"; guidance: Standard })
  | (GuidanceStatus & { mode: "adaptive"; spec: Spec; stale_for_display: boolean });
export interface GuidanceRequest {
  procedure_id: string; expected_revision: number; expected_profile_revision: number | null;
  standard_writing_style: "plain" | "extra_plain" | "concise";
}
export interface AckRequest {
  presentation_id: string; configuration_id: string; displayed_action_ids: string[];
}
export interface DisplayRequest {
  event_id: string; expected_revision: number; presentation_id: string; configuration_id: string; action_id: string;
}
export interface Navigation {
  schema_version: "c4-navigation-1.0"; presentation_id: string; exposure_id: string;
  configuration_id: string; graph_fingerprint: string; session_revision: number;
  acknowledged: boolean; current_action_id: string | null; displayed_action_ids: string[];
  events: { event_id: string; action_id: string; is_revisit: boolean; sequence: number }[];
}
export type PendingDisplay =
  | { kind: "ack"; request: AckRequest }
  | { kind: "navigation"; request: DisplayRequest };

export function itemKey(item: Item): string { return JSON.stringify([item.kind, item.identifier]); }
export function documentOf(result: Guidance): Document {
  return result.mode === "standard" ? result.guidance : result.spec;
}

export function actionLabel(doc: Document, id: string) {
  const action = doc.explanation.source.graph.actions.find((row) => row.action_id === id);
  const content = doc.explanation.source.graph.content.find((row) => row.content_id === action?.required_content_ids[0]);
  return content?.text ?? id;
}
