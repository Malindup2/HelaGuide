import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ContractError } from "../api/client";
import { parseSpec } from "../guidance/contracts";
import RelationshipMap from "../guidance/RelationshipMap";
import { ActionSection, PrerequisiteCues, SelectedAids, SourceItems, SourceRegister } from "../guidance/rendering";
import { actionTitle, branchLayout, dependencyLayout, layoutMap, validateSelectedDiagram } from "../guidance/scaffoldModel";
import type { MapNode } from "../guidance/scaffoldModel";
import type { Card, Spec } from "../guidance/types";
import { actionLabel } from "../guidance/types";
import { specFixture } from "./fixtures/guidance";

function addGlobal(spec: Spec, card: Card) {
  spec.cards.push(card); spec.global_items.push(card.source);
  spec.visibility.visible.push(card.source); spec.explanation.source.preservation.always_visible.push(card.source);
}
function syncConfiguration(spec: Spec) {
  const c = spec.configuration;
  c.configuration_id = "c4-scaffold-v1:" + c.presentation_mode + ":pd" + Number(c.progressive_disclosure) +
    ":recap" + Number(c.previous_context_recap) + ":" + c.relationship_visual + ":cue" + Number(c.prerequisite_cue);
  spec.explanation = { ...spec.explanation, ...{ configuration: { ...c } } };
}
function branchSpec(selection: "AND" | "OR" | "XOR" = "XOR"): Spec {
  const spec = specFixture();
  const group = { group_id: "branch:collection", service_id: "svc:demo", selection,
    options: spec.pages.map((page, index) => ({ option_id: "option:" + index, action_ids: [page.action_id], condition_ids: index === 0 ? ["condition:counter"] : [] })) };
  spec.explanation.source.graph.conditions.push({ condition_id: "condition:counter", text: "Only when the counter option is chosen." });
  spec.explanation.source.graph.branch_groups.push(group);
  addGlobal(spec, { source: { kind: "condition", identifier: "condition:counter" }, title: "Supplied condition",
    lines: ["Only when the counter option is chosen."], collapsed: false });
  addGlobal(spec, { source: { kind: "branch_group", identifier: group.group_id }, title: "Alternative group",
    lines: ["Selection semantics: " + selection], collapsed: false });
  spec.diagram = { ...spec.diagram, kind: "BRANCH_MAP", actions: spec.explanation.source.graph.actions,
    stages: spec.explanation.source.graph.stages, branch_groups: [group] };
  spec.configuration.relationship_visual = "BRANCH_MAP";
  syncConfiguration(spec);
  return spec;
}
function dependencySpec(): Spec {
  const spec = specFixture();
  const edge = { edge_id: "prerequisite:one-two", source_id: "action:one", target_id: "action:two" };
  spec.explanation.source.graph.action_prerequisites.push(edge);
  addGlobal(spec, { source: { kind: "action_prerequisite", identifier: edge.edge_id }, title: "Prerequisite",
    lines: ["Action one must precede action two."], collapsed: false });
  spec.diagram = { ...spec.diagram, kind: "DEPENDENCY_MAP", actions: spec.explanation.source.graph.actions, action_prerequisites: [edge] };
  spec.configuration.relationship_visual = "DEPENDENCY_MAP";
  syncConfiguration(spec);
  return spec;
}
function simpleNode(id: string): MapNode {
  return { id, title: id, fullLabel: id, eyebrow: "Test action", tone: "action", actionIds: [id], conditionIds: [] };
}

describe("truthful relationship maps", () => {
  it("draws a shared predecessor and join once, using only the four supplied edges", () => {
    const nodes = ["register", "form", "copy", "submit"].map(simpleNode);
    const edges = [["register", "form"], ["register", "copy"], ["form", "submit"], ["copy", "submit"]].map(([source, target], index) => ({
      id: "edge:" + index, source, target, meaning: "dependency" as const,
    }));
    const layout = layoutMap(nodes, edges);
    expect(layout.nodes).toHaveLength(4); expect(layout.edges).toEqual(edges);
    expect(new Set(layout.nodes.map((node) => node.id)).size).toBe(4);
    expect(layout.nodes.find((node) => node.id === "register")!.x).toBeLessThan(layout.nodes.find((node) => node.id === "submit")!.x);
  });
  it("rejects missing endpoints and dependency cycles", () => {
    const nodes = ["one", "two"].map(simpleNode);
    expect(() => layoutMap(nodes, [{ id: "edge:bad", source: "one", target: "missing", meaning: "dependency" }])).toThrow(ContractError);
    expect(() => layoutMap(nodes, [
      { id: "edge:1", source: "one", target: "two", meaning: "dependency" },
      { id: "edge:2", source: "two", target: "one", meaning: "dependency" },
    ])).toThrow(ContractError);
  });
  it("renders one dependency arrow per actual edge without repeating its source node", () => {
    const spec = dependencySpec(); parseSpec(spec);
    const html = renderToStaticMarkup(<RelationshipMap spec={spec} currentActionId="action:two" />);
    expect(html.match(/data-edge-id=/g)).toHaveLength(1);
    expect(html.match(/data-node-id=/g)).toHaveLength(2);
    expect(html.match(/role="button"/g)).toHaveLength(2);
    expect(html).toContain('tabindex="0"');
    expect(html).toContain("data-relationship=\"dependency\"");
    expect(html).toContain("Currently open");
    expect(html).toContain("Unconnected nodes do not prove independence");
  });
  it.each([
    ["AND", "All options apply"],
    ["OR", "One or more applicable options"],
    ["XOR", "Exactly one applicable option"],
  ] as const)("preserves %s selection semantics and draws membership rather than prerequisite arrows", (selection, meaning) => {
    const spec = branchSpec(selection); parseSpec(spec);
    const model = branchLayout(spec, spec.diagram.branch_groups[0]);
    expect(model.edges.every((edge) => edge.meaning === "membership")).toBe(true);
    const html = renderToStaticMarkup(<RelationshipMap spec={spec} />);
    expect(html).toContain(meaning);
    expect(html.match(/data-relationship="membership"/g)).toHaveLength(2);
    expect(html).not.toContain("marker-end=");
    expect(html).toContain("does not decide eligibility");
  });
  it("uses each dependency layer's actual node set", () => {
    const spec = dependencySpec();
    const stageMap = dependencyLayout(spec, "service", ["svc:demo"], []);
    const actionMap = dependencyLayout(spec, "action", ["action:one", "action:two"], spec.diagram.action_prerequisites);
    expect(stageMap.nodes.map((node) => node.id)).toEqual(["svc:demo"]);
    expect(actionMap.nodes.map((node) => node.id)).toEqual(["action:one", "action:two"]);
  });
  it("shows only explicitly grouped parallel actions and invents no fork/join arrows", () => {
    const spec = specFixture();
    const group = { group_id: "parallel:preparation", service_id: "svc:demo", action_ids: ["action:one", "action:two"] };
    spec.explanation.source.graph.parallel_groups.push(group);
    spec.diagram = { ...spec.diagram, kind: "PARALLEL_MAP", actions: spec.explanation.source.graph.actions, parallel_groups: [group] };
    const html = renderToStaticMarkup(<RelationshipMap spec={spec} />);
    expect(html).toContain("Explicit parallel group");
    expect(html.match(/class="parallel-node /g)).toHaveLength(2);
    expect(html).not.toContain("data-edge-id");
    expect(html).toContain("No additional ordering, fork/join or independence");
  });
  it("does not draw a relationship aid when NONE was selected", () => {
    expect(renderToStaticMarkup(<RelationshipMap spec={specFixture()} />)).toBe("");
  });
  it("rejects a selected diagram whose explicit edges have no displayed endpoints", () => {
    const spec = dependencySpec(); spec.diagram.actions = [];
    expect(() => parseSpec(spec)).toThrow(ContractError);
    const parallel = specFixture();
    parallel.diagram.kind = "PARALLEL_MAP";
    parallel.diagram.parallel_groups = [{ group_id: "parallel:bad", service_id: "svc:demo", action_ids: ["unknown"] }];
    expect(() => validateSelectedDiagram(parallel)).toThrow(ContractError);
  });
});

describe("safe scaffold presentation", () => {
  it("shortens navigation labels while retaining complete required instructions", () => {
    const spec = specFixture();
    const full = "Register the fictional application before preparing both required items and checking all the listed conditions. The two items must both be complete before submission.";
    spec.explanation.source.graph.content[0].text = full;
    spec.cards.find((card) => card.source.identifier === "content:one")!.lines = [full];
    expect(actionTitle(spec, "action:one").length).toBeLessThanOrEqual(68);
    expect(actionLabel(spec, "action:one")).toBe(full);
    const html = renderToStaticMarkup(<ActionSection doc={spec} page={spec.pages[0]} index={0}
      disabled observeToken="static" onVisible={() => {}} />);
    expect(html).toContain(full);
    expect(html).not.toContain("<details");
  });
  it("keeps generated supplementary text inside the same reviewed disclosure", () => {
    const spec = specFixture();
    const source = { kind: "content", identifier: "content:extra" };
    spec.explanation.source.graph.content.push({ content_id: source.identifier, role: "supplementary", text: "Reviewed optional context." });
    spec.explanation.source.graph.actions[0].supplementary_content_ids.push(source.identifier);
    spec.pages[0].items.push(source);
    spec.cards.push({ source, title: "Supplementary source text", lines: ["Reviewed optional context."], collapsed: true });
    spec.explanation.source.preservation.collapsible_content_ids.push(source.identifier);
    spec.visibility.collapsed.push(source);
    spec.explanation.explanations.push({
      unit_id: "unit:extra", action_id: "action:one", content_id: source.identifier, origin: "generated",
      text: "Generated optional explanation.", fact_ids: [], evidence_ids: [], citations: [],
    });
    spec.explanation.origin = "generated"; spec.explanation.assurance = "automated_checks_only";
    spec.configuration.progressive_disclosure = true; syncConfiguration(spec); parseSpec(spec);
    const html = renderToStaticMarkup(<SourceItems doc={spec} refs={[source]} annotationActionId="action:one" />);
    const start = html.indexOf("<details"); const end = html.indexOf("</details>");
    expect(start).toBeGreaterThanOrEqual(0);
    expect(html.indexOf("Generated optional explanation.")).toBeGreaterThan(start);
    expect(html.indexOf("Generated optional explanation.")).toBeLessThan(end);
    expect(html).not.toContain("<details open");
  });
  it("renders prerequisite cues with human labels only when the cue references are present", () => {
    const spec = dependencySpec();
    expect(renderToStaticMarkup(<PrerequisiteCues doc={spec} refs={[]} />)).toBe("");
    const html = renderToStaticMarkup(<PrerequisiteCues doc={spec} refs={[{ kind: "action_prerequisite", identifier: "prerequisite:one-two" }]} />);
    expect(html).toContain("Required instruction 1");
    expect(html).toContain("does not confirm its completion");
    expect(html).not.toContain("action:one");
  });
  it("recaps acknowledged actions without implying completion or rendering extra diagrams", () => {
    const spec = specFixture();
    spec.recap = { action_ids: ["action:one"], exposure_ids: ["exposure:old"], meaning: "previously_displayed_not_completed" };
    const html = renderToStaticMarkup(<SelectedAids spec={spec} />);
    expect(html).toContain("Pick up the context"); expect(html).toContain("Required instruction 1");
    expect(html).toContain("Previously displayed does not mean completed");
    expect(html).not.toContain("<svg");
  });
  it("retains the source inventory in the register and pages without hiding protected cards", () => {
    const spec = branchSpec();
    const html = renderToStaticMarkup(<><SourceRegister doc={spec} />
      {spec.pages.map((page, index) => <ActionSection key={page.action_id} doc={spec} page={page} index={index}
        disabled observeToken="static" onVisible={() => {}} />)}
      <SourceItems doc={spec} refs={spec.global_items.filter((item) => item.kind === "notice")} /></>);
    for (const card of spec.cards) for (const line of card.lines) expect(html).toContain(line);
    expect(html).not.toContain("<details");
  });
  it("rendering aids leaves original decision, configuration and source records unchanged", () => {
    const spec = branchSpec(); const before = JSON.stringify(spec);
    renderToStaticMarkup(<SelectedAids spec={spec} currentActionId="action:one" />);
    expect(JSON.stringify(spec)).toBe(before);
  });
});
