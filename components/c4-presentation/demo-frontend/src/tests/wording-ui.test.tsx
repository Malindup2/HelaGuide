import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ContractError } from "../api/client";
import { GuidanceApi } from "../guidance/api";
import { attachWording, parseGuidance } from "../guidance/contracts";
import { ActionSection, PreviousStepSummary, PrerequisiteCues } from "../guidance/rendering";
import { actionNode, actionTitle, dependencyLayout } from "../guidance/scaffoldModel";
import { actionLabel } from "../guidance/types";
import type { Navigation, PreparedWording, Spec } from "../guidance/types";
import { previousViewedAction } from "../guidance/wording";
import { specFixture } from "./fixtures/guidance";

function wording(spec: Spec): PreparedWording {
  return {
    request_key: "d".repeat(64), graph_fingerprint: spec.graph_fingerprint,
    artifact_digest: "e".repeat(64), diagnostics: [],
    items: [
      ["action_heading", "A clear demo heading"],
      ["action_explanation", "This explains the supplied fictional step."],
      ["action_summary", "The previous step explained the fictional request."],
      ["diagram_label", "Demo request"],
    ].map(([kind, text]) => ({ slot_id: `${kind}/action/action:one`, text,
      source_references: [{ kind: "action", reference_id: "action:one" }], origin: "human_prepared" })),
  };
}

function navigation(spec: Spec, visits: string[] = []): Navigation {
  return {
    schema_version: "c4-navigation-1.0", presentation_id: spec.presentation_id,
    exposure_id: spec.exposure_id, configuration_id: spec.configuration.configuration_id,
    graph_fingerprint: spec.graph_fingerprint, session_revision: visits.length + 1,
    acknowledged: true, current_action_id: visits.at(-1) ?? spec.initial_action_id,
    displayed_action_ids: [...new Set([spec.initial_action_id!, ...visits])],
    events: visits.map((action_id, index) => ({ event_id: `event:${index}`, action_id, sequence: index + 1, is_revisit: index > 0 })),
  };
}

describe("reviewed wording rendering", () => {
  it("uses readable headings and explanations while retaining full required source cards", () => {
    const original = specFixture(); const source = actionLabel(original, "action:one");
    const doc = attachWording(original, wording(original));
    const html = renderToStaticMarkup(<ActionSection doc={doc} page={doc.pages[0]} index={0}
      disabled observeToken="test" onVisible={() => {}} />);
    expect(html).toContain("A clear demo heading");
    expect(html).toContain("This explains the supplied fictional step.");
    expect(html).toContain(source);
    expect(doc.cards).toEqual(original.cards);
    expect(original.prepared_wording).toBeUndefined();
    expect(doc.exposure_id).toBe(original.exposure_id);
    expect(doc.configuration).toEqual(original.configuration);
  });
  it("uses diagram labels without adding or changing edges", () => {
    const original = specFixture(); const doc = attachWording(original, wording(original));
    const edges = [{ edge_id: "edge:one-two", source_id: "action:one", target_id: "action:two" }];
    const layout = dependencyLayout(doc, "action", ["action:one", "action:two"], edges);
    expect(actionNode(doc, "action:one").title).toBe("Demo request");
    expect(actionTitle(doc, "action:one")).toBe("A clear demo heading");
    expect(layout.edges.map((edge) => [edge.id, edge.source, edge.target])).toEqual([["edge:one-two", "action:one", "action:two"]]);
  });
  it("retains source-based rendering for legacy and missing-slot responses", () => {
    const spec = specFixture();
    expect(actionTitle(attachWording(spec, null), "action:one")).toBe(actionTitle(spec, "action:one"));
    const partial = wording(spec); partial.items = partial.items.filter((row) => row.slot_id.startsWith("action_heading/"));
    const doc = attachWording(spec, partial);
    const html = renderToStaticMarkup(<ActionSection doc={doc} page={doc.pages[1]} index={1} disabled observeToken="test" onVisible={() => {}} />);
    expect(html).toContain(actionLabel(spec, "action:two"));
    expect(html).not.toContain("This explains the supplied fictional step.");
  });
  it.each(["graph", "subject", "reference", "review", "origin", "duplicate", "format"])("rejects invalid wording %s", (change) => {
    const spec = specFixture(); const value = wording(spec);
    if (change === "graph") value.graph_fingerprint = "other";
    else if (change === "subject") value.items[0].slot_id = "action_heading/action/action:unknown";
    else if (change === "reference") value.items[0].source_references.push({ kind: "action", reference_id: "unknown" });
    else if (change === "review") value.artifact_digest = null;
    else if (change === "origin") value.items[1].origin = "provider_generated";
    else if (change === "duplicate") value.items.push(value.items[0]);
    else value.items[0].text = "<script>untrusted()</script>";
    expect(() => attachWording(spec, value)).toThrow(ContractError);
  });
  it("binds the outer guidance and saved-presentation wording without changing identity", async () => {
    const spec = specFixture(); const prepared = wording(spec);
    const result = parseGuidance({ mode: "adaptive", session_id: spec.session_id,
      session_revision: spec.context_revision, profile_id: "profile:test", profile_revision: 0,
      personalization_enabled: true, spec, stale_for_display: false, wording: prepared });
    expect(result.mode === "adaptive" && result.spec.prepared_wording).toEqual(prepared);
    const request = vi.fn().mockResolvedValue({ spec, stale_for_display: false, wording: prepared });
    const api = new GuidanceApi({ request });
    const restored = await api.presentation(spec.session_id, spec.exposure_id, spec.graph_fingerprint);
    expect(restored.spec.prepared_wording).toEqual(prepared);
    expect(restored.spec.presentation_id).toBe(spec.presentation_id);
    expect(restored.spec.decision_id).toBe(spec.decision_id);
    expect(request.mock.calls[0][1]).toBe("GET");
  });
  it("shows prepared prerequisite wording while retaining the original prerequisite cue", () => {
    const spec = specFixture();
    const edge = { edge_id: "prerequisite:test", source_id: "action:one", target_id: "action:two" };
    spec.explanation.source.graph.action_prerequisites.push(edge);
    spec.cards.push({ source: { kind: "action_prerequisite", identifier: edge.edge_id }, title: "Prerequisite", lines: ["Original requirement."], collapsed: false });
    const prepared = wording(spec);
    prepared.items.push({ slot_id: `prerequisite_explanation/action_prerequisite/${edge.edge_id}`,
      text: "The fictional request comes before collection.", origin: "human_prepared",
      source_references: [{ kind: "action_prerequisite", reference_id: edge.edge_id }] });
    const doc = attachWording(spec, prepared);
    const html = renderToStaticMarkup(<PrerequisiteCues doc={doc} refs={[{ kind: "action_prerequisite", identifier: edge.edge_id }]} />);
    expect(html).toContain("The fictional request comes before collection.");
    expect(html).toContain("First complete:");
    expect(html).toContain("does not confirm its completion");
  });
});

describe("Guided previous-view reminders", () => {
  it("is absent on the first viewed step and when display has not been acknowledged", () => {
    const spec = specFixture(); const nav = navigation(spec);
    expect(previousViewedAction(spec, nav, spec.initial_action_id)).toBeNull();
    expect(previousViewedAction(spec, { ...nav, acknowledged: false }, "action:two")).toBeNull();
    expect(renderToStaticMarkup(<PreviousStepSummary spec={spec} navigation={nav} currentActionId={spec.initial_action_id} />)).toBe("");
  });
  it("uses the previous displayed visit, including jumps and backwards navigation", () => {
    const spec = specFixture();
    expect(previousViewedAction(spec, navigation(spec), "action:two")).toBe("action:one");
    expect(previousViewedAction(spec, navigation(spec, ["action:two"]), "action:two")).toBe("action:one");
    expect(previousViewedAction(spec, navigation(spec, ["action:two", "action:one"]), "action:one")).toBe("action:two");
    const jumped = structuredClone(spec);
    jumped.pages.push({ ...jumped.pages[1], action_id: "action:three" });
    expect(previousViewedAction(jumped, navigation(jumped), "action:three")).toBe("action:one");
  });
  it("shows a reviewed step summary independently of cross-visit recap, without mutations", () => {
    const base = specFixture(); const spec = attachWording(base, wording(base));
    const nav = navigation(spec, ["action:two"]); const before = JSON.stringify([spec, nav]);
    expect(spec.recap).toBeNull();
    const html = renderToStaticMarkup(<PreviousStepSummary spec={spec} navigation={nav} currentActionId="action:two" />);
    expect(html).toContain("The previous step explained the fictional request.");
    expect(html).toContain("not confirmation of completion");
    expect(JSON.stringify([spec, nav])).toBe(before);
  });
  it("shows a source heading when no reviewed summary exists and never appears in Overview", () => {
    const spec = specFixture(); const nav = navigation(spec, ["action:two"]);
    const html = renderToStaticMarkup(<PreviousStepSummary spec={spec} navigation={nav} currentActionId="action:two" />);
    expect(html).toContain("From your previous step");
    expect(html).toContain(actionTitle(spec, "action:one"));
    const overview = structuredClone(spec); overview.configuration.presentation_mode = "OVERVIEW";
    expect(previousViewedAction(overview, nav, "action:two")).toBeNull();
  });
});
