import { ContractError } from "../api/client";
import type { Branch, Document, Edge, Spec } from "./types";
import { actionLabel } from "./types";

export const branchMeanings = {
  AND: "All options apply under the supplied applicability.",
  OR: "One or more applicable options may be selected.",
  XOR: "Exactly one applicable option is selected.",
};
export function compactLabel(text: string, limit = 68): string {
  const normalized = text.replace(/\s+/g, " ").trim();
  const first = normalized.match(/^.*?[.!?](?=\s|$)/)?.[0] ?? normalized;
  if (first.length <= limit) return first;
  const cut = first.slice(0, limit - 1);
  const boundary = cut.lastIndexOf(" ");
  return cut.slice(0, boundary > limit / 2 ? boundary : cut.length).trimEnd() + "…";
}
/** Display label only. Complete requirements are never replaced with this label. */
export function actionTitle(doc: Document, id: string) { return compactLabel(actionLabel(doc, id)); }

export interface MapNode {
  id: string; title: string; fullLabel: string; eyebrow: string;
  tone: "action" | "service" | "choice" | "option";
  actionIds: string[]; conditionIds: string[]; serviceId?: string;
}
export interface MapEdge { id: string; source: string; target: string; meaning: "dependency" | "membership" }
export interface PositionedNode extends MapNode { x: number; y: number }
export interface MapLayout { nodes: PositionedNode[]; edges: MapEdge[]; width: number; height: number }
export const NODE_WIDTH = 236;
export const NODE_HEIGHT = 132;

/** Positions supplied nodes and connections; never adds a relationship. */
export function layoutMap(nodes: MapNode[], edges: MapEdge[]): MapLayout {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  if (byId.size !== nodes.length) throw new ContractError("Duplicate diagram node.");
  const edgeIds = new Set<string>();
  const incoming = new Map(nodes.map((node) => [node.id, 0]));
  const rank = new Map(nodes.map((node) => [node.id, 0]));
  for (const edge of edges) {
    if (edgeIds.has(edge.id) || !byId.has(edge.source) || !byId.has(edge.target) || edge.source === edge.target) {
      throw new ContractError("Diagram connection has an unknown, duplicate or self-referencing endpoint.");
    }
    edgeIds.add(edge.id);
    incoming.set(edge.target, incoming.get(edge.target)! + 1);
  }
  const queue = nodes.filter((node) => incoming.get(node.id) === 0).map((node) => node.id);
  let visited = 0;
  while (queue.length) {
    const id = queue.shift()!; visited += 1;
    for (const edge of edges.filter((row) => row.source === id)) {
      rank.set(edge.target, Math.max(rank.get(edge.target)!, rank.get(id)! + 1));
      incoming.set(edge.target, incoming.get(edge.target)! - 1);
      if (incoming.get(edge.target) === 0) queue.push(edge.target);
    }
  }
  if (visited !== nodes.length) throw new ContractError("A dependency cycle cannot be drawn as a procedure order.");
  const levels = new Map<number, MapNode[]>();
  for (const node of nodes) {
    const level = rank.get(node.id)!;
    levels.set(level, [...(levels.get(level) ?? []), node]);
  }
  const rows = Math.max(1, ...[...levels.values()].map((level) => level.length));
  const positioned = [...levels].sort(([a], [b]) => a - b).flatMap(([level, members]) =>
    members.map((node, index) => ({
      ...node, x: 24 + level * (NODE_WIDTH + 92),
      y: 24 + ((rows - members.length) / 2 + index) * (NODE_HEIGHT + 34),
    })),
  );
  return {
    nodes: positioned, edges: [...edges],
    width: 48 + Math.max(1, levels.size) * NODE_WIDTH + Math.max(0, levels.size - 1) * 92,
    height: 48 + rows * NODE_HEIGHT + Math.max(0, rows - 1) * 34,
  };
}
export function actionNode(doc: Document, id: string): MapNode {
  const index = doc.pages.findIndex((page) => page.action_id === id);
  return {
    id, title: actionTitle(doc, id), fullLabel: actionLabel(doc, id),
    eyebrow: index >= 0 ? "Action " + (index + 1) : "Supplied action", tone: "action",
    actionIds: [id], conditionIds: doc.pages[index]?.condition_ids ?? [],
  };
}
export function dependencyLayout(doc: Document, layer: "action" | "service", nodes: string[], edges: Edge[]) {
  const mapNodes = nodes.map((id): MapNode => {
    if (layer === "action") return actionNode(doc, id);
    const stage = doc.explanation.source.graph.stages.find((row) => row.service_id === id);
    return { id, title: compactLabel(stage?.name ?? id), fullLabel: stage?.name ?? id, eyebrow: "Service",
      tone: "service", serviceId: id, actionIds: [], conditionIds: [] };
  });
  return layoutMap(mapNodes, edges.map((edge) => ({
    id: edge.edge_id, source: edge.source_id, target: edge.target_id, meaning: "dependency",
  })));
}
export function branchLayout(doc: Document, group: Branch): MapLayout {
  const gate: MapNode = {
    id: group.group_id, title: group.selection === "XOR" ? "Choose exactly one" : group.selection === "OR" ? "One or more options" : "All applicable options",
    fullLabel: branchMeanings[group.selection], eyebrow: group.selection + " selection",
    tone: "choice", actionIds: [], conditionIds: [],
  };
  const options: MapNode[] = group.options.map((option, index) => ({
    id: option.option_id, title: compactLabel(option.action_ids.map((id) => actionTitle(doc, id)).join(" · ")),
    fullLabel: option.action_ids.map((id) => actionLabel(doc, id)).join("\n"),
    eyebrow: "Option " + (index + 1), tone: "option", actionIds: [...option.action_ids],
    conditionIds: [...new Set([...option.condition_ids,
      ...option.action_ids.flatMap((id) => doc.pages.find((page) => page.action_id === id)?.condition_ids ?? [])])],
  }));
  return layoutMap([gate, ...options], options.map((option) => ({
    id: group.group_id + "/" + option.id, source: gate.id, target: option.id, meaning: "membership",
  })));
}
export function wrapLabel(text: string, width = 27): string[] {
  const words = text.split(/\s+/).flatMap((word) => {
    const chunks: string[] = [];
    for (let i = 0; i < word.length; i += width) chunks.push(word.slice(i, i + width));
    return chunks;
  });
  const lines: string[] = [];
  for (const word of words) {
    if (!lines.length || lines[lines.length - 1].length + word.length + 1 > width) lines.push(word);
    else lines[lines.length - 1] += " " + word;
  }
  if (lines.length <= 3) return lines;
  return [...lines.slice(0, 2), lines[2].slice(0, width - 1).trimEnd() + "…"];
}

export function validateSelectedDiagram(spec: Spec): void {
  const d = spec.diagram;
  const actions = new Set(d.actions.map((action) => action.action_id));
  if (d.kind === "DEPENDENCY_MAP") {
    dependencyLayout(spec, "service", d.stages.map((stage) => stage.service_id), d.stage_dependencies);
    dependencyLayout(spec, "action", d.actions.map((action) => action.action_id), d.action_prerequisites);
  }
  if (d.kind === "BRANCH_MAP") {
    for (const group of d.branch_groups) {
      if (group.options.some((option) => option.action_ids.some((id) => !actions.has(id)))) {
        throw new ContractError("A branch option references an action outside the selected diagram.");
      }
      branchLayout(spec, group);
    }
  }
  if (d.kind === "PARALLEL_MAP") {
    for (const group of d.parallel_groups) {
      if (new Set(group.action_ids).size !== group.action_ids.length || group.action_ids.some((id) => !actions.has(id))) {
        throw new ContractError("A parallel group references duplicate or unavailable actions.");
      }
    }
  }
}

export function actionDomId(id: string) { return "guidance-action-" + encodeURIComponent(id); }
