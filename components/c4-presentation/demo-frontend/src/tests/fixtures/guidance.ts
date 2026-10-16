import type { Spec } from "../../guidance/types";

const sid = "guest:" + "a".repeat(32);
const fp = "c".repeat(64);

export const configuration = {
  presentation_mode: "GUIDED" as const, progressive_disclosure: false,
  previous_context_recap: false, relationship_visual: "NONE" as const, prerequisite_cue: false,
  configuration_id: "c4-scaffold-v1:GUIDED:pd0:recap0:NONE:cue0",
};
export function specFixture(): Spec {
  const actions = ["one", "two"].map((name) => ({
    action_id: "action:" + name, service_id: "svc:demo",
    required_content_ids: ["content:" + name], supplementary_content_ids: [],
  }));
  const content = actions.map((action, index) => ({
    content_id: action.required_content_ids[0], text: "Required instruction " + (index + 1), role: "required" as const,
  }));
  const cards = [
    ...actions.map((action) => ({ source: { kind: "action", identifier: action.action_id }, title: "Procedure action", lines: [action.action_id], collapsed: false })),
    ...content.map((row) => ({ source: { kind: "content", identifier: row.content_id }, title: "Required source text", lines: [row.text], collapsed: false })),
    { source: { kind: "fact", identifier: "fee:one" }, title: "Supplied fee", lines: ["LKR 50"], collapsed: false },
    { source: { kind: "notice", identifier: "notice:synthetic" }, title: "Important source information", lines: ["Synthetic fixture only."], collapsed: false },
  ];
  const graph = {
    synthetic: true, disclaimer: "Synthetic fixture only.",
    stages: [{ service_id: "svc:demo", name: "Demo service", agency: "Fictional agency", fee_fact_id: "fee:one", document_fact_ids: [] }],
    actions, content, conditions: [], branch_groups: [], parallel_groups: [],
    stage_dependencies: [], action_prerequisites: [],
  };
  return {
    schema_version: "c4-presentation-1.0", text_format: "plain_text",
    presentation_id: "presentation:" + "d".repeat(64), session_id: sid,
    exposure_id: "exposure:" + "e".repeat(32), decision_id: "decision:" + "f".repeat(32),
    graph_fingerprint: fp, context_revision: 0, configuration: { ...configuration },
    explanation: {
      graph_fingerprint: fp, origin: "fallback", source_status: "synthetic", assurance: "source_preserving_copy",
      source: { graph, preservation: { always_visible: cards.map((card) => card.source), collapsible_content_ids: [] } },
      explanations: [],
      ...{ exposure_id: "exposure:" + "e".repeat(32), decision_id: "decision:" + "f".repeat(32), configuration: { ...configuration } },
    },
    cards, global_items: cards.filter((card) => ["fact", "notice"].includes(card.source.kind)).map((card) => card.source),
    pages: actions.map((action) => ({
      action_id: action.action_id, service_id: action.service_id,
      items: [{ kind: "action", identifier: action.action_id }, { kind: "content", identifier: action.required_content_ids[0] }],
      condition_ids: [], branch_group_id: null, branch_option_id: null, prerequisite_cues: [],
    })),
    visibility: { visible: cards.map((card) => card.source), collapsed: [] },
    initial_action_id: actions[0].action_id, acknowledgment_action_ids: [actions[0].action_id],
    diagram: { kind: "NONE", stages: [], actions: [], stage_dependencies: [], action_prerequisites: [], branch_groups: [], parallel_groups: [] },
    recap: null, navigation_semantics: "browsing_order_not_completion_or_eligibility",
  };
}
