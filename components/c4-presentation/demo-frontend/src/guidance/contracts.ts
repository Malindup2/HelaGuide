import { ContractError } from "../api/client";
import type { Document, Guidance, GuidanceStatus, Navigation, Spec, PreparedWording } from "./types";
import { documentOf, itemKey } from "./types";
import { validateSelectedDiagram } from "./scaffoldModel";

function check(value: unknown, message: string): asserts value {
  if (!value) throw new ContractError("Invalid guidance response: " + message);
}
function object(value: unknown): asserts value is Record<string, unknown> {
  check(value !== null && typeof value === "object" && !Array.isArray(value), "expected an object");
}
function array(value: unknown): asserts value is unknown[] { check(Array.isArray(value), "expected an array"); }
function text(value: unknown): asserts value is string { check(typeof value === "string" && value.length > 0, "missing text"); }
function strings(value: unknown): asserts value is string[] { array(value); value.forEach(text); }
function integer(value: unknown) { check(Number.isSafeInteger(value) && Number(value) >= 0, "invalid revision"); }
function unique(values: string[], label: string) { check(new Set(values).size === values.length, "duplicate " + label); }
function items(value: unknown) {
  array(value);
  value.forEach((item) => { object(item); text(item.kind); text(item.identifier); });
}
const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

export function attachWording<T extends Document>(doc: T, value: unknown): T {
  if (value === undefined || value === null) return { ...doc, prepared_wording: null };
  object(value);
  check(value.graph_fingerprint === doc.graph_fingerprint, "wording graph attribution differs");
  text(value.request_key); check(/^[a-f0-9]{64}$/.test(value.request_key), "invalid wording key");
  check(value.artifact_digest === null || (typeof value.artifact_digest === "string" && /^[a-f0-9]{64}$/.test(value.artifact_digest)), "invalid wording artifact digest");
  strings(value.diagnostics); array(value.items);
  const graph = doc.explanation.source.graph;
  const known = new Set(doc.cards.map((card) => JSON.stringify([card.source.kind, card.source.identifier])));
  for (const action of graph.actions) known.add(JSON.stringify(["action", action.action_id]));
  for (const stage of graph.stages) known.add(JSON.stringify(["stage", stage.service_id]));
  for (const group of graph.branch_groups) for (const option of group.options) known.add(JSON.stringify(["branch_option", option.option_id]));
  const ids: string[] = []; const origins = new Set<string>();
  const limits: Record<string, number> = { action_heading: 120, action_explanation: 1800, action_summary: 400, diagram_label: 100, prerequisite_explanation: 800 };
  for (const item of value.items) {
    object(item); text(item.slot_id); text(item.text); array(item.source_references);
    const match = /^(action_heading|action_explanation|action_summary|diagram_label|prerequisite_explanation)\/([^/]+)\/(.+)$/.exec(item.slot_id);
    check(match, "unknown wording slot");
    const [, kind, subjectKind, id] = match;
    check(kind === "diagram_label" ? ["action", "stage", "branch_group", "branch_option", "parallel_group"].includes(subjectKind) :
      kind === "prerequisite_explanation" ? ["action_prerequisite", "stage_dependency"].includes(subjectKind) : subjectKind === "action", "wording slot subject differs");
    check(known.has(JSON.stringify([subjectKind, id])), "unknown wording subject");
    const references: string[] = [];
    for (const reference of item.source_references) {
      object(reference); text(reference.kind); text(reference.reference_id);
      const key = JSON.stringify([reference.kind, reference.reference_id]);
      check(known.has(key), "unknown wording source reference"); references.push(key);
    }
    unique(references, "wording reference");
    check(references.includes(JSON.stringify([subjectKind, id])), "wording subject source missing");
    check(["human_prepared", "provider_generated", "source_fallback"].includes(String(item.origin)), "unknown wording origin");
    if (item.origin !== "source_fallback") {
      check(value.artifact_digest !== null && item.text.trim().length > 0 && item.text.length <= limits[kind], "unreviewed or oversized wording");
      check(!/https?:\/\/|www\.|javascript:|```|<[^>]+>|\[[^\]]+\]\(/i.test(item.text), "unsafe wording format");
      origins.add(String(item.origin));
    }
    ids.push(item.slot_id);
  }
  unique(ids, "wording slot"); check(origins.size <= 1, "mixed wording provenance");
  return { ...doc, prepared_wording: value as unknown as PreparedWording };
}

export function parseStatus(value: unknown): GuidanceStatus {
  object(value); text(value.session_id); integer(value.session_revision);
  check(value.profile_id === null || typeof value.profile_id === "string", "invalid profile");
  check(value.profile_revision === null || (Number.isSafeInteger(value.profile_revision) && Number(value.profile_revision) >= 0), "invalid profile revision");
  check((value.profile_id === null) === (value.profile_revision === null), "unpaired profile attribution");
  check(typeof value.personalization_enabled === "boolean", "invalid personalization status");
  return value as unknown as GuidanceStatus;
}

function validateDocument(value: unknown): Document {
  object(value); text(value.graph_fingerprint);
  check(value.navigation_semantics === "browsing_order_not_completion_or_eligibility", "unsupported navigation semantics");
  array(value.cards); items(value.global_items); array(value.pages);
  object(value.visibility); items(value.visibility.visible); items(value.visibility.collapsed);
  object(value.explanation);
  const explanation = value.explanation;
  check(explanation.graph_fingerprint === value.graph_fingerprint, "source identity differs");
  check(explanation.origin === "generated" || explanation.origin === "fallback", "unknown explanation origin");
  text(explanation.source_status); text(explanation.assurance);
  object(explanation.source); object(explanation.source.graph); object(explanation.source.preservation);
  items(explanation.source.preservation.always_visible);
  strings(explanation.source.preservation.collapsible_content_ids);
  const graph = explanation.source.graph;
  check(typeof graph.synthetic === "boolean", "missing source classification"); text(graph.disclaimer);
  for (const field of ["stages", "actions", "content", "conditions", "stage_dependencies", "action_prerequisites", "branch_groups", "parallel_groups"]) array(graph[field]);
  for (const row of graph.stages as unknown[]) {
    object(row); text(row.service_id); text(row.name); text(row.agency); text(row.fee_fact_id); strings(row.document_fact_ids);
  }
  for (const row of graph.actions as unknown[]) {
    object(row); text(row.action_id); text(row.service_id); strings(row.required_content_ids); strings(row.supplementary_content_ids);
  }
  for (const row of graph.content as unknown[]) {
    object(row); text(row.content_id); text(row.text); check(row.role === "required" || row.role === "supplementary", "unknown content role");
  }
  for (const row of graph.conditions as unknown[]) { object(row); text(row.condition_id); text(row.text); }
  for (const field of ["stage_dependencies", "action_prerequisites"]) {
    for (const row of graph[field] as unknown[]) { object(row); text(row.edge_id); text(row.source_id); text(row.target_id); }
  }
  for (const row of graph.branch_groups as unknown[]) {
    object(row); text(row.group_id); text(row.service_id);
    check(["AND", "OR", "XOR"].includes(String(row.selection)), "unknown branch meaning"); array(row.options);
    for (const option of row.options) { object(option); text(option.option_id); strings(option.action_ids); strings(option.condition_ids); }
  }
  for (const row of graph.parallel_groups as unknown[]) {
    object(row); text(row.group_id); text(row.service_id); strings(row.action_ids);
  }
  for (const row of value.cards) {
    object(row); items([row.source]); text(row.title); strings(row.lines);
    check(row.lines.length > 0 && typeof row.collapsed === "boolean", "invalid source card");
  }
  for (const row of value.pages) {
    object(row); text(row.action_id); text(row.service_id); items(row.items); items(row.prerequisite_cues); strings(row.condition_ids);
    check(row.branch_group_id === null || typeof row.branch_group_id === "string", "invalid branch membership");
    check(row.branch_option_id === null || typeof row.branch_option_id === "string", "invalid option membership");
  }
  array(explanation.explanations);
  for (const row of explanation.explanations) {
    object(row); text(row.unit_id); text(row.action_id); text(row.content_id); text(row.text);
    check(row.origin === "generated" || row.origin === "source_copy", "unknown annotation origin");
    strings(row.fact_ids); strings(row.evidence_ids); array(row.citations);
    for (const citation of row.citations) { object(citation); text(citation.evidence_id); text(citation.quote); }
  }

  const doc = value as unknown as Document;
  const cards = new Map(doc.cards.map((card) => [itemKey(card.source), card]));
  unique(doc.cards.map((card) => itemKey(card.source)), "source card");
  unique(doc.pages.map((page) => page.action_id), "page");
  const preservation = doc.explanation.source.preservation;
  const inventory = [...preservation.always_visible, ...preservation.collapsible_content_ids.map((id) => ({ kind: "content", identifier: id }))];
  check(inventory.length === cards.size && inventory.every((ref) => cards.has(itemKey(ref))), "source inventory is not preserved");
  check(preservation.always_visible.every((ref) => cards.get(itemKey(ref))?.collapsed === false), "essential information is collapsed");
  check(doc.cards.every((card) => !card.collapsed || (card.source.kind === "content" && preservation.collapsible_content_ids.includes(card.source.identifier))), "unapproved disclosure");
  const located = new Set([...doc.global_items, ...doc.pages.flatMap((page) => page.items)].map(itemKey));
  check(located.size === cards.size && [...located].every((key) => cards.has(key)), "layout omits source information");
  check(same(doc.visibility.visible.map(itemKey), doc.cards.filter((card) => !card.collapsed).map((card) => itemKey(card.source))) &&
    same(doc.visibility.collapsed.map(itemKey), doc.cards.filter((card) => card.collapsed).map((card) => itemKey(card.source))), "visibility does not match cards");
  const ids = doc.explanation.source.graph.actions.map((action) => action.action_id);
  check(ids.length === doc.pages.length && doc.pages.every((page) => ids.includes(page.action_id)), "pages do not cover graph actions");
  for (const page of doc.pages) {
    check(page.prerequisite_cues.every((ref) => cards.has(itemKey(ref))), "unknown prerequisite cue");
    check(page.condition_ids.every((id) => doc.explanation.source.graph.conditions.some((c) => c.condition_id === id)), "unknown condition");
  }
  check(doc.explanation.explanations.every((row) => ids.includes(row.action_id) && doc.explanation.source.graph.content.some((c) => c.content_id === row.content_id)), "unknown explanation target");
  return doc;
}

export function parseSpec(value: unknown): Spec {
  const doc = validateDocument(value);
  object(value);
  check(value.schema_version === "c4-presentation-1.0" && value.text_format === "plain_text", "unsupported PresentationSpec");
  for (const field of ["presentation_id", "session_id", "exposure_id", "decision_id"]) text(value[field]);
  integer(value.context_revision); strings(value.acknowledgment_action_ids);
  object(value.configuration);
  const c = value.configuration;
  check(c.presentation_mode === "GUIDED" || c.presentation_mode === "OVERVIEW", "unknown layout");
  check(["NONE", "BRANCH_MAP", "DEPENDENCY_MAP", "PARALLEL_MAP"].includes(String(c.relationship_visual)), "unknown visual");
  for (const field of ["progressive_disclosure", "previous_context_recap", "prerequisite_cue"]) check(typeof c[field] === "boolean", "invalid scaffold flag");
  const expected = "c4-scaffold-v1:" + c.presentation_mode + ":pd" + Number(c.progressive_disclosure) +
    ":recap" + Number(c.previous_context_recap) + ":" + c.relationship_visual + ":cue" + Number(c.prerequisite_cue);
  check(c.configuration_id === expected, "configuration identity mismatch");
  object(value.explanation);
  check(value.explanation.exposure_id === value.exposure_id && value.explanation.decision_id === value.decision_id &&
    same(value.explanation.configuration, value.configuration), "explanation attribution differs");
  object(value.diagram); check(value.diagram.kind === c.relationship_visual, "diagram differs from selection");
  const spec = value as unknown as Spec;
  const graph = doc.explanation.source.graph;
  for (const field of ["stages", "actions", "stage_dependencies", "action_prerequisites", "branch_groups", "parallel_groups"] as const) {
    const rows = value.diagram[field];
    array(rows);
    // Every rendered relationship/node must be an exact supplied graph record.
    check(rows.every((row) => graph[field].some((source) => same(source, row))), "diagram invents graph content");
  }
  if (spec.diagram.kind === "NONE") check(Object.entries(spec.diagram).every(([key, rows]) => key === "kind" || (Array.isArray(rows) && rows.length === 0)), "NONE includes a diagram");
  if (spec.diagram.kind === "DEPENDENCY_MAP") check(spec.diagram.stage_dependencies.length + spec.diagram.action_prerequisites.length > 0 && !spec.diagram.branch_groups.length && !spec.diagram.parallel_groups.length, "invalid dependency map");
  if (spec.diagram.kind === "BRANCH_MAP") check(spec.diagram.branch_groups.length > 0 && !spec.diagram.stage_dependencies.length && !spec.diagram.action_prerequisites.length && !spec.diagram.parallel_groups.length, "invalid branch map");
  if (spec.diagram.kind === "PARALLEL_MAP") check(spec.diagram.parallel_groups.length > 0 && !spec.diagram.stage_dependencies.length && !spec.diagram.action_prerequisites.length && !spec.diagram.branch_groups.length, "invalid parallel map");
  validateSelectedDiagram(spec);
  if (c.presentation_mode === "GUIDED") {
    check(doc.pages.some((page) => page.action_id === value.initial_action_id) &&
      same(value.acknowledgment_action_ids, [value.initial_action_id]), "invalid guided display scope");
  } else check(value.initial_action_id === null && same(value.acknowledgment_action_ids, doc.pages.map((page) => page.action_id)), "invalid overview display scope");
  check(c.progressive_disclosure || !doc.cards.some((card) => card.collapsed), "disclosure is disabled");
  check(c.prerequisite_cue || doc.pages.every((page) => !page.prerequisite_cues.length), "cue scaffold is disabled");
  if (c.previous_context_recap) {
    object(value.recap); strings(value.recap.action_ids); strings(value.recap.exposure_ids);
    check(value.recap.meaning === "previously_displayed_not_completed" && value.recap.action_ids.length > 0 &&
      value.recap.action_ids.every((id) => doc.pages.some((page) => page.action_id === id)), "invalid recap");
  } else check(value.recap === null, "recap is disabled");
  return spec;
}

export function parseGuidance(value: unknown): Guidance {
  const status = parseStatus(value);
  object(value);
  if (value.mode === "adaptive") {
    check(status.personalization_enabled && status.profile_id !== null, "adaptive guidance lacks consent");
    const spec = parseSpec(value.spec);
    check(spec.session_id === status.session_id && spec.context_revision === status.session_revision, "decision context differs");
    check(typeof value.stale_for_display === "boolean", "missing staleness flag");
  } else {
    check(value.mode === "standard" && !status.personalization_enabled, "unknown guidance mode");
    validateDocument(value.guidance); object(value.guidance);
    const standard = value.guidance;
    check(standard.schema_version === "c4-standard-guidance-1.0" && standard.presentation_mode === "OVERVIEW" &&
      standard.personalization_applied === false && standard.exposure_acknowledgment_required === false &&
      standard.learning_eligible === false, "standard guidance must not learn or acknowledge");
    text(standard.standard_id);
    check(["plain", "extra_plain", "concise"].includes(String(standard.writing_style)), "unknown writing style");
    const doc = standard as unknown as Document;
    check(!doc.cards.some((card) => card.collapsed) && doc.pages.every((page) => !page.prerequisite_cues.length), "standard guidance has adaptive scaffolds");
  }
  const result = value as unknown as Guidance;
  return result.mode === "adaptive" ? { ...result, spec: attachWording(result.spec, value.wording) } :
    { ...result, guidance: attachWording(result.guidance, value.wording) };
}

export function parseNavigation(value: unknown, spec: Spec): Navigation {
  object(value);
  check(value.schema_version === "c4-navigation-1.0" &&
    value.presentation_id === spec.presentation_id && value.exposure_id === spec.exposure_id &&
    value.configuration_id === spec.configuration.configuration_id && value.graph_fingerprint === spec.graph_fingerprint, "navigation attribution differs");
  integer(value.session_revision); strings(value.displayed_action_ids); array(value.events);
  check(typeof value.acknowledged === "boolean", "invalid acknowledgment status");
  const ids = spec.pages.map((page) => page.action_id);
  check(value.current_action_id === null || ids.includes(String(value.current_action_id)), "unknown current action");
  check(value.displayed_action_ids.every((id) => ids.includes(id)), "unknown displayed action"); unique(value.displayed_action_ids, "displayed action");
  for (const event of value.events) {
    object(event); text(event.event_id); integer(event.sequence);
    check(ids.includes(String(event.action_id)) && typeof event.is_revisit === "boolean", "invalid navigation event");
  }
  return value as unknown as Navigation;
}

export function assertGuidanceScope(result: Guidance, sessionId: string, procedureId: string) {
  check(result.session_id === sessionId && documentOf(result).graph_fingerprint === procedureId, "wrong session or procedure");
}
