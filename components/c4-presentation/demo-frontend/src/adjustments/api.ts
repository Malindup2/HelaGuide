import { api, ContractError, parseSession } from "../api/client";
import type { C4Api } from "../api/client";
import { parseSpec } from "../guidance/contracts";
import type { Configuration, Spec } from "../guidance/types";

export interface ViewRecord { view_id: string; parent_view_id: string; operation: "adjust" | "undo"; configuration: Configuration; focus_action_id: string; created_at: string; undo_target_id: string | null }
export interface ViewDisplay { event_id: string; view_id: string; action_id: string; recorded_at: string }
export interface ViewRating { event_id: string; view_id: string; rating: "about_right" | "need_more" | "too_much"; recorded_at: string; origin: string; learning_eligible: false }
export interface AdjustmentState {
  schema_version: "c4-adjustment-state-1.0";
  ledger: { schema_version: "c4-adjustments-1.0"; session_id: string; exposure_id: string; presentation_id: string; policy_run_id: string; revision: number; views: ViewRecord[]; displays: ViewDisplay[]; ratings: ViewRating[] };
  active_view_id: string; original_view: boolean; spec: Spec; focus_action_id: string; displayed_action_ids: string[];
  feasible_configurations: Configuration[]; can_undo: boolean; stale_for_display: boolean; learning_eligible: boolean;
}
export type PendingAdjustment =
  | { kind: "view"; body: { request_id: string; expected_revision: number; parent_view_id: string; operation: "adjust" | "undo"; configuration: Omit<Configuration, "configuration_id"> | null; focus_action_id: string } }
  | { kind: "display"; body: { event_id: string; expected_revision: number; view_id: string; action_id: string } }
  | { kind: "rating"; body: { event_id: string; expected_revision: number; view_id: string; rating: ViewRating["rating"] } }
  | { kind: "preferences"; body: { request_id: string; view_id: string; expected_session_revision: number } };
type Obj = Record<string, unknown>;
const object = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
function check(v: unknown, message: string): asserts v { if (!v) throw new ContractError("Invalid adjustment state: " + message); }
const count = (v: unknown) => Number.isSafeInteger(v) && Number(v) >= 0;
function configuration(v: unknown): Configuration {
  check(object(v) && ["GUIDED", "OVERVIEW"].includes(String(v.presentation_mode)) && ["NONE", "BRANCH_MAP", "DEPENDENCY_MAP", "PARALLEL_MAP"].includes(String(v.relationship_visual)) &&
    [v.progressive_disclosure, v.previous_context_recap, v.prerequisite_cue].every(x => typeof x === "boolean"), "configuration");
  check(v.configuration_id === `c4-scaffold-v1:${v.presentation_mode}:pd${Number(v.progressive_disclosure)}:recap${Number(v.previous_context_recap)}:${v.relationship_visual}:cue${Number(v.prerequisite_cue)}`, "configuration identity");
  return v as unknown as Configuration;
}
export function parseAdjustment(value: unknown, root: Spec): AdjustmentState {
  check(object(value) && value.schema_version === "c4-adjustment-state-1.0" && object(value.ledger), "version");
  const l = value.ledger;
  check(l.schema_version === "c4-adjustments-1.0" && l.session_id === root.session_id && l.exposure_id === root.exposure_id && l.presentation_id === root.presentation_id && typeof l.policy_run_id === "string" && count(l.revision), "root lineage");
  const spec = parseSpec(value.spec);
  check(spec.session_id === root.session_id && spec.exposure_id === root.exposure_id && spec.presentation_id === root.presentation_id && spec.decision_id === root.decision_id && spec.graph_fingerprint === root.graph_fingerprint, "projected view scope");
  check(JSON.stringify(spec.explanation.source) === JSON.stringify(root.explanation.source), "source preservation");
  check(Array.isArray(value.feasible_configurations) && value.feasible_configurations.length > 0 && value.feasible_configurations.length <= 64, "feasible configurations");
  const feasible = new Set(value.feasible_configurations.map(c => configuration(c).configuration_id));
  check(feasible.size === value.feasible_configurations.length && feasible.has(spec.configuration.configuration_id), "feasible view");
  check(Array.isArray(l.views) && Array.isArray(l.displays) && Array.isArray(l.ratings), "history arrays");
  const ids = new Set(["original"]);
  let active = "original";
  for (const v of l.views) {
    check(object(v) && typeof v.view_id === "string" && /^view:[0-9a-f]{32}$/.test(v.view_id) && !ids.has(v.view_id) && v.parent_view_id === active &&
      ["adjust", "undo"].includes(String(v.operation)) && typeof v.focus_action_id === "string" && typeof v.created_at === "string" && Number.isFinite(Date.parse(v.created_at)), "view lineage");
    check(feasible.has(configuration(v.configuration).configuration_id), "view feasibility");
    ids.add(v.view_id); active = v.view_id;
  }
  const eventIds = new Set<string>();
  for (const d of [...l.displays, ...l.ratings]) {
    check(object(d) && typeof d.event_id === "string" && /^event:[0-9a-f]{32}$/.test(d.event_id) && !eventIds.has(d.event_id) && typeof d.view_id === "string" && d.view_id !== "original" && ids.has(d.view_id) && typeof d.recorded_at === "string" && Number.isFinite(Date.parse(d.recorded_at)), "view event");
    eventIds.add(d.event_id);
  }
  const actionIds = new Set(root.pages.map(p => p.action_id));
  check(l.displays.every(d => actionIds.has(String(d.action_id))), "display action");
  check(l.ratings.every(r => ["about_right", "need_more", "too_much"].includes(String(r.rating)) && r.learning_eligible === false && ["simulation", "participant_report"].includes(String(r.origin))), "manual ratings are not policy rewards");
  check(l.revision === l.views.length + l.displays.length + l.ratings.length && value.active_view_id === active && value.learning_eligible === (l.views.length === 0) &&
    typeof value.can_undo === "boolean" && typeof value.stale_for_display === "boolean" && typeof value.original_view === "boolean" && actionIds.has(String(value.focus_action_id)) &&
    Array.isArray(value.displayed_action_ids) && value.displayed_action_ids.every(id => actionIds.has(String(id))), "state summary");
  // Keep the original frozen wording attachment; do not consult today's registry.
  spec.prepared_wording = root.prepared_wording;
  return { ...value, spec } as unknown as AdjustmentState;
}
export function pendingAdjustment(value: unknown): value is PendingAdjustment {
  if (!object(value) || !object(value.body)) return false;
  const b = value.body;
  const id = "request_id" in b ? b.request_id : b.event_id;
  if (typeof id !== "string" || !/^event:[0-9a-f]{32}$/.test(id)) return false;
  if (value.kind === "preferences") return typeof b.view_id === "string" && count(b.expected_session_revision);
  if (!count(b.expected_revision)) return false;
  if (value.kind === "display") return typeof b.view_id === "string" && typeof b.action_id === "string";
  if (value.kind === "rating") return typeof b.view_id === "string" && ["about_right", "need_more", "too_much"].includes(String(b.rating));
  return value.kind === "view" && ["adjust", "undo"].includes(String(b.operation)) && typeof b.parent_view_id === "string" && typeof b.focus_action_id === "string" && (b.configuration === null || object(b.configuration));
}
export class AdjustmentApi {
  constructor(private transport: Pick<C4Api, "request"> = api) {}
  private path(root: Spec) { return `/dev/v1/sessions/${encodeURIComponent(root.session_id)}/presentations/${encodeURIComponent(root.exposure_id)}/views`; }
  async read(root: Spec) { return parseAdjustment(await this.transport.request(this.path(root), "GET"), root); }
  async send(root: Spec, pending: PendingAdjustment) {
    const suffix = pending.kind === "view" ? "" : "/" + pending.kind;
    const response = await this.transport.request(this.path(root) + suffix, "POST", undefined, pending.body);
    if (pending.kind === "preferences") {
      const session = parseSession(response);
      if (session.session_id !== root.session_id) throw new ContractError("Preference response belongs to another session.");
      return this.read(root);
    }
    return parseAdjustment(response, root);
  }
}
