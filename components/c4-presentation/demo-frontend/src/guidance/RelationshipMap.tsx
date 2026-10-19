import { useId, useState } from "react";
import type { Document, Spec } from "./types";
import { actionLabel } from "./types";
import { preparedText } from "./wording";
import {
  NODE_HEIGHT, NODE_WIDTH, actionNode, branchLayout, branchMeanings, dependencyLayout, wrapLabel,
} from "./scaffoldModel";
import type { MapLayout, MapNode } from "./scaffoldModel";

function NodeDetails({ doc, node }: { doc: Document; node: MapNode | undefined }) {
  if (!node) return <p className="map-hint">Select a node to inspect its supplied information. This does not change your presentation or mark an action complete.</p>;
  const graph = doc.explanation.source.graph;
  const stage = graph.stages.find((row) => row.service_id === node.serviceId);
  return <aside className="map-node-details" aria-live="polite">
    <span className="eyebrow">{node.eyebrow}</span><h4>{node.title}</h4>
    {node.actionIds.length === 0 && <p>{node.fullLabel}</p>}
    {stage && <p>Agency: {stage.agency}</p>}
    {node.actionIds.map((id) => {
      const action = graph.actions.find((row) => row.action_id === id);
      return <div key={id}>{action?.required_content_ids.map((contentId) => {
        const content = graph.content.find((row) => row.content_id === contentId);
        return content ? <p key={contentId}>{content.text}</p> : null;
      })}</div>;
    })}
    {node.conditionIds.length > 0 && <div className="map-conditions"><strong>Supplied conditions</strong>
      {node.conditionIds.map((id) => <p key={id}>{graph.conditions.find((row) => row.condition_id === id)?.text ?? id}</p>)}
    </div>}
  </aside>;
}

function MapCanvas({ doc, layout, title, currentActionId }: {
  doc: Document; layout: MapLayout; title: string; currentActionId?: string | null;
}) {
  const instance = useId().replace(/[^a-zA-Z0-9_-]/g, "");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const byId = new Map(layout.nodes.map((node) => [node.id, node]));
  const selected = layout.nodes.find((node) => node.id === selectedId);
  return <div className="procedure-map">
    <div className="map-scroll" tabIndex={0} role="region" aria-label={title + ". Scroll horizontally on small screens."}>
      <svg width={layout.width} height={layout.height} viewBox={"0 0 " + layout.width + " " + layout.height}
        role="group" aria-labelledby={instance + "-title"} className="procedure-map-svg">
        <title id={instance + "-title"}>{title}</title>
        <defs><marker id={instance + "-arrow"} viewBox="0 0 10 10" refX="9" refY="5"
          markerWidth="8" markerHeight="8" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="#526b87" />
        </marker></defs>
        {layout.edges.map((edge) => {
          const source = byId.get(edge.source)!; const target = byId.get(edge.target)!;
          const x1 = source.x + NODE_WIDTH; const y1 = source.y + NODE_HEIGHT / 2;
          const x2 = target.x; const y2 = target.y + NODE_HEIGHT / 2;
          const mid = (x1 + x2) / 2;
          return <path key={edge.id} data-edge-id={edge.id} data-relationship={edge.meaning}
            className={"map-edge map-edge-" + edge.meaning}
            d={"M " + x1 + " " + y1 + " C " + mid + " " + y1 + ", " + mid + " " + y2 + ", " + x2 + " " + y2}
            markerEnd={edge.meaning === "dependency" ? "url(#" + instance + "-arrow)" : undefined}>
            <title>{source.title + (edge.meaning === "dependency" ? " → " : " belongs to the same selection group as ") + target.title}</title>
          </path>;
        })}
        {layout.nodes.map((node) => {
          const current = !!currentActionId && node.actionIds.includes(currentActionId);
          const lines = wrapLabel(node.title);
          return <g key={node.id} transform={"translate(" + node.x + " " + node.y + ")"}
            className={"map-node map-node-" + node.tone + (selectedId === node.id ? " selected" : "") + (current ? " current" : "")}
            role="button" tabIndex={0} aria-label={node.eyebrow + ": " + node.fullLabel}
            aria-pressed={selectedId === node.id} data-node-id={node.id}
            onClick={() => setSelectedId(node.id)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setSelectedId(node.id); }
            }}>
            <title>{node.fullLabel}</title>
            <rect width={NODE_WIDTH} height={NODE_HEIGHT} rx="12" />
            <text x="16" y="24" className="map-node-eyebrow">{node.eyebrow}</text>
            <text x="16" y="48" className="map-node-title">
              {lines.map((line, index) => <tspan key={index} x="16" dy={index === 0 ? 0 : 19}>{line}</tspan>)}
            </text>
            <text x="16" y={NODE_HEIGHT - 12} className="map-node-caption">
              {current ? "Currently open" : node.conditionIds.length > 0 ? "Conditions supplied" :
                node.actionIds.length > 1 ? node.actionIds.length + " supplied actions" : "Inspect information"}
            </text>
          </g>;
        })}
      </svg>
    </div>
    <NodeDetails doc={doc} node={selected} />
  </div>;
}

export default function RelationshipMap({ spec, currentActionId }: { spec: Spec; currentActionId?: string | null }) {
  const diagram = spec.diagram;
  if (diagram.kind === "NONE") return null;
  return <section className={"relationship-panel scaffold-map scaffold-map-" + diagram.kind.toLowerCase()} aria-label="Selected relationship aid">
    <div className="scaffold-heading"><div><p className="eyebrow">Selected support</p>
      <h3>{diagram.kind === "DEPENDENCY_MAP" ? "See the dependencies" : diagram.kind === "BRANCH_MAP" ? "Compare the available paths" : "See what may run in parallel"}</h3></div>
      <span className="scaffold-icon" aria-hidden="true">{diagram.kind === "BRANCH_MAP" ? "⑂" : diagram.kind === "PARALLEL_MAP" ? "∥" : "↗"}</span></div>
    {diagram.kind === "DEPENDENCY_MAP" && <>
      {diagram.stage_dependencies.length > 0 && <div className="map-layer"><h4>Between services</h4>
        <p className="helper-text">Arrows show supplied service dependencies. They do not add an AND/OR interpretation.</p>
        <MapCanvas doc={spec} title="Service dependency map"
          layout={dependencyLayout(spec, "service", diagram.stages.map((row) => row.service_id), diagram.stage_dependencies)} />
      </div>}
      {diagram.action_prerequisites.length > 0 && <div className="map-layer"><h4>Between actions</h4>
        <p className="helper-text">An arrow means the source action must be completed before the target action. No completion is assumed.</p>
        <MapCanvas doc={spec} title="Action prerequisite map" currentActionId={currentActionId}
          layout={dependencyLayout(spec, "action", diagram.actions.map((row) => row.action_id), diagram.action_prerequisites)} />
      </div>}
      <p className="map-footnote">Only supplied edges are drawn. Unconnected nodes do not prove independence. Service and action relationships are shown separately.</p>
    </>}
    {diagram.kind === "BRANCH_MAP" && diagram.branch_groups.map((group) => <div className="map-layer" key={group.group_id}>
      <div className="branch-meaning"><span className="branch-symbol">{group.selection}</span><p>{branchMeanings[group.selection]}</p></div>
      <MapCanvas doc={spec} layout={branchLayout(spec, group)} title={group.selection + " branch membership map"} currentActionId={currentActionId} />
      <p className="map-footnote">Lines connect a selection group to its options; they are not prerequisite arrows. The application does not decide eligibility or choose an option for you.</p>
    </div>)}
    {diagram.kind === "PARALLEL_MAP" && diagram.parallel_groups.map((group) => <ParallelGroup key={group.group_id} spec={spec}
      groupId={group.group_id} actionIds={group.action_ids} currentActionId={currentActionId} />)}
  </section>;
}
function ParallelGroup({ spec, groupId, actionIds, currentActionId }: { spec: Spec; groupId: string; actionIds: string[]; currentActionId?: string | null }) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  return <div className="parallel-group-frame">
    <div className="parallel-label"><span aria-hidden="true">∥</span><strong>{preparedText(spec, "diagram_label", "parallel_group", groupId) ?? "Explicit parallel group"}</strong></div>
    <div className="parallel-lanes">{actionIds.map((id) => {
      const node = actionNode(spec, id);
      return <button type="button" key={id} className={"parallel-node " + (currentActionId === id ? "current" : "")}
        aria-label={"Inspect " + actionLabel(spec, id)} aria-pressed={selectedId === id}
        onClick={() => setSelectedId(id)}>
        <span className="eyebrow">{node.eyebrow}</span><strong>{node.title}</strong>
        <small>{currentActionId === id ? "Currently open" : "Inspect information"}</small>
      </button>;
    })}</div>
    <p className="map-footnote">These actions are explicitly grouped as parallel, subject to their supplied conditions and prerequisites. No additional ordering, fork/join or independence is inferred.</p>
    <NodeDetails doc={spec} node={selectedId ? actionNode(spec, selectedId) : undefined} />
  </div>;
}
