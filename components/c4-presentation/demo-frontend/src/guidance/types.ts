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
  content: { content_id: string; text: string; role: "required" | "supplementary"; fact_ids?: string[] }[];
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
export interface PreparedWording {
  request_key: string; graph_fingerprint: string; artifact_digest: string | null;
  diagnostics: string[];
  items: { slot_id: string; text: string; source_references: { kind: string; reference_id: string }[];
    origin: "human_prepared" | "provider_generated" | "demo_mock" | "source_fallback" }[];
}
export interface Document {
  graph_fingerprint: string; cards: Card[]; global_items: Item[]; pages: Page[];
  explanation: Explanation; visibility: { visible: Item[]; collapsed: Item[] };
  navigation_semantics: "browsing_order_not_completion_or_eligibility";
  /** Client-side attachment from the response envelope; not a new policy spec. */
  prepared_wording?: PreparedWording | null;
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
  const graph = doc.explanation.source.graph;
  const action = graph.actions.find((row) => row.action_id === id);
  const content = action?.required_content_ids.map((key) => graph.content.find((row) => row.content_id === key))
    .find((row) => row && row.text !== graph.disclaimer && !contentCoveredByNotice(doc, row.content_id));
  return content?.text ?? id;
}

/** Only omit a duplicate paragraph when the complete text is already visible. */
export function contentCoveredByNotice(doc: Document, contentId: string): boolean {
  const content = doc.explanation.source.graph.content.find((row) => row.content_id === contentId);
  if (!content) return false;
  const notices = new Set(doc.global_items.filter((ref) => ref.kind === "notice").map((ref) => ref.identifier));
  return doc.cards.some((card) => card.source.kind === "notice" && notices.has(card.source.identifier) &&
    !card.collapsed && card.lines.includes(content.text));
}

export function serviceFactItems(doc: Document): Item[] {
  const identifiers = new Set(doc.explanation.source.graph.stages.flatMap((stage) => [stage.fee_fact_id, ...stage.document_fact_ids]));
  return doc.cards.filter((card) => card.source.kind === "fact" && identifiers.has(card.source.identifier)).map((card) => card.source);
}

/** Only explicit action-content fact links. Shared scope and parent-service
 * membership alone do not establish which action uses a document or fee. */
export function actionFactItems(doc: Document, actionId: string): Item[] {
  const graph = doc.explanation.source.graph;
  const action = graph.actions.find((row) => row.action_id === actionId);
  if (!action) return [];
  const ids = new Set(graph.content.filter((content) => action.required_content_ids.includes(content.content_id)
    && content.text !== graph.disclaimer).flatMap((content) => content.fact_ids ?? []));
  return doc.cards.filter((card) => card.source.kind === "fact" && ids.has(card.source.identifier)).map((card) => card.source);
}
