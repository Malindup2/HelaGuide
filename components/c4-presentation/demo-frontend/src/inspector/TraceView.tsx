import { useState } from "react";
import type { ReactNode } from "react";
import type { Configuration, Spec } from "../guidance/types";
import { dependencyLayout, NODE_HEIGHT, NODE_WIDTH, wrapLabel } from "../guidance/scaffoldModel";
import type { PipelineTrace, TraceCandidate } from "./types";

const human = (s: string) => s.replaceAll("_", " ");
const number = (v: number | null | undefined) => v == null ? "Not recorded" : v.toLocaleString(undefined, { maximumSignificantDigits: 6 });
export function ConfigurationLabel({ value: c }: { value: Configuration }) {
  return <span>{human(c.presentation_mode)} · {human(c.relationship_visual)} · Disclosure {c.progressive_disclosure ? "on" : "off"} · Recap {c.previous_context_recap ? "on" : "off"} · Prerequisites {c.prerequisite_cue ? "on" : "off"}</span>;
}
function Json({ title, value }: { title: string; value: unknown }) {
  return <details className="inspector-json"><summary>{title}</summary><pre>{JSON.stringify(value, null, 2)}</pre></details>;
}
function Panel({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return <section id={id} className="inspector-panel" aria-labelledby={id + "-title"}><h2 id={id + "-title"}>{title}</h2>{children}</section>;
}
function Facts({ items }: { items: [string, ReactNode][] }) {
  return <dl className="inspector-facts">{items.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value ?? "Not recorded"}</dd></div>)}</dl>;
}
function ContextFacts({ trace }: { trace: PipelineTrace }) {
  const snapshot = trace.records.policy_offer.offer.context_snapshot;
  if (typeof snapshot !== "object" || snapshot === null || Array.isArray(snapshot)) return null;
  const context = snapshot as Record<string, unknown>;
  const settings = typeof context.settings === "object" && context.settings !== null ? context.settings as Record<string, unknown> : {};
  const scalar = (v: unknown) => typeof v === "number" || typeof v === "string" ? String(v) : "Unknown";
  return <><Facts items={[["Requested service", scalar(context.requested_service_id)], ["Context revision at selection", scalar(context.revision)],
    ["Self-reported navigation capability", scalar(settings.navigation_capability)], ["Matching previous exposures", scalar(context.matching_exposure_count)],
    ["Preference changes recorded", scalar(context.preference_change_count)], ["Captured at", scalar(context.captured_at)]]} />
    <div className="inspector-context-columns"><Json title="Original familiarity reports" value={settings.familiarity} /><Json title="Original preferences" value={settings.preferences} />
      <Json title="Original hard locks" value={settings.locks} /><Json title="Original accessibility constraints" value={settings.accessibility} /></div></>;
}
function SavedGraph({ spec, layer }: { spec: Spec; layer: "stage" | "action" }) {
  const graph = spec.explanation.source.graph;
  const ids = layer === "stage" ? graph.stages.map(x => x.service_id) : graph.actions.map(x => x.action_id);
  const edges = layer === "stage" ? graph.stage_dependencies : graph.action_prerequisites;
  const layout = dependencyLayout(spec, layer === "stage" ? "service" : "action", ids, edges);
  const nodes = new Map(layout.nodes.map(n => [n.id, n]));
  return <div className="inspector-graph" tabIndex={0} role="region" aria-label={layer + " graph, horizontally scrollable"}>
    <svg width={layout.width} height={layout.height} viewBox={`0 0 ${layout.width} ${layout.height}`} role="img" aria-label={layer === "stage" ? "Recorded service dependencies" : "Recorded action prerequisites"}>
      <defs><marker id={"inspect-arrow-" + layer} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10z" fill="#526b87" /></marker></defs>
      {layout.edges.map(edge => { const a = nodes.get(edge.source)!; const b = nodes.get(edge.target)!;
        return <path key={edge.id} d={`M${a.x + NODE_WIDTH} ${a.y + NODE_HEIGHT / 2} L${b.x} ${b.y + NODE_HEIGHT / 2}`} stroke="#526b87" strokeWidth="2" fill="none" markerEnd={`url(#inspect-arrow-${layer})`}><title>{edge.id}</title></path>;
      })}
      {layout.nodes.map(node => <g key={node.id} transform={`translate(${node.x} ${node.y})`}>
        <title>{node.fullLabel}</title><rect width={NODE_WIDTH} height={NODE_HEIGHT} rx="12" fill="#f2f5fa" stroke="#526b87" />
        <text x="15" y="24" fontSize="12" fill="#526b87">{node.eyebrow}</text>
        <text x="15" y="50" fontSize="15">{wrapLabel(node.title).map((line, i) => <tspan key={i} x="15" dy={i ? 20 : 0}>{line}</tspan>)}</text>
      </g>)}
    </svg>
  </div>;
}
function CandidateTable({ trace }: { trace: PipelineTrace }) {
  const [filter, setFilter] = useState("all");
  const [sort, setSort] = useState("recorded");
  const rows = trace.candidates.filter(c => filter === "all" || (filter === "feasible" ? c.feasible : filter === "selected" ? c.selected : !c.feasible));
  if (sort === "sampled") rows.sort((a, b) => (b.score?.sampled_score ?? -Infinity) - (a.score?.sampled_score ?? -Infinity));
  if (sort === "mean") rows.sort((a, b) => (b.score?.posterior_mean ?? -Infinity) - (a.score?.posterior_mean ?? -Infinity));
  return <>
    <p>{trace.selection.feasible_count} feasible · {trace.selection.rejected_count} rejected · {trace.selection.sampled_candidate_count} sampled. Linear surrogate scores are not probabilities or causal feature explanations.</p>
    <div className="inspector-controls"><label>Show candidates<select value={filter} onChange={e => setFilter(e.target.value)}><option value="all">All 64</option><option value="feasible">Feasible</option><option value="rejected">Rejected</option><option value="selected">Selected</option></select></label>
      <label>Order<select value={sort} onChange={e => setSort(e.target.value)}><option value="recorded">Recorded order</option><option value="sampled">Sampled score, descending</option><option value="mean">Posterior mean, descending</option></select></label></div>
    <div className="inspector-table" tabIndex={0} role="region" aria-label="Candidate scores and feasibility"><table>
      <caption>Original candidate evaluation at selection revision {trace.selection.selection_posterior_revision}. Missing scores remain unscored.</caption>
      <thead><tr><th>Configuration</th><th>Decision</th><th>Posterior mean</th><th>Posterior SD</th><th>Sampling SD</th><th>Sampled score</th><th>Recorded reasons</th></tr></thead>
      <tbody>{rows.map(c => <CandidateRow key={c.configuration.configuration_id} candidate={c} />)}</tbody>
    </table></div>
  </>;
}
function CandidateRow({ candidate: c }: { candidate: TraceCandidate }) {
  return <tr className={c.selected ? "inspector-selected" : ""}><td><ConfigurationLabel value={c.configuration} /><details><summary>Configuration ID</summary><code>{c.configuration.configuration_id}</code></details></td>
    <td>{c.selected ? "Selected" : c.feasible ? "Feasible" : "Rejected"}</td><td>{number(c.score?.posterior_mean)}</td><td>{number(c.score?.posterior_std)}</td><td>{number(c.score?.sampling_std)}</td>
    <td>{c.score_status === "not_scored" ? "Not scored" : c.score_status === "recorded_moments_not_sampled" ? "Not sampled" : number(c.score?.sampled_score)}</td>
    <td><details><summary>{c.rejections.length ? `${c.rejections.length} rejection reason(s)` : `${c.satisfied.length} satisfied reason(s)`}</summary>
      {[...c.rejections, ...c.satisfied].map((r, i) => <p key={i}><code>{r.code}</code>: {r.message}</p>)}</details></td></tr>;
}

export function TraceView({ trace: t }: { trace: PipelineTrace }) {
  const spec = t.records.presentation;
  const graph = spec.explanation.source.graph;
  const decision = t.records.policy_offer.decision;
  const sections = [["trace-input", "Graph & sources"], ["trace-features", "Seven features"], ["trace-context", "User context"], ["trace-candidates", "Feasibility & scores"], ["trace-selection", "Selection"], ["trace-content", "Content"], ["trace-display", "Display"], ["trace-learning", "Learning"], ["trace-evidence", "Evidence boundaries"]];
  return <>
    <div className="inspector-snapshot"><strong>Saved presentation</strong><code>{spec.exposure_id}</code><ConfigurationLabel value={spec.configuration} />
      <p>Selected at revision <b>{t.selection.selection_posterior_revision}</b> · {human(t.selection.selection_mode)} · Current shared revision <b>{t.current.shared_posterior_revision}</b></p>
      {t.current.stale_for_display && <p className="notice">Historical view: current settings or routing differ. These are the original records.</p>}
      {t.current.shared_policy_run_id !== t.selection.policy_run_id && <p className="notice">The current shared policy run differs from this decision’s run.</p>}
    </div>
    <nav className="inspector-flow" aria-label="Pipeline sections">{sections.map(([id, title], i) => <a href={"#" + id} key={id} onClick={e => { e.preventDefault(); document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" }); }}><span>{String(i + 1).padStart(2, "0")}</span>{title}</a>)}</nav>
    <Panel id="trace-input" title="1. Canonical graph and supplied sources">
      <p>Saved normalized input. Raw Plan/enrichment payloads and historical validation execution were not recorded. This diagram shows supplied dependencies; it does not reconstruct an execution log.</p>
      <Facts items={[["Source status", human(t.input.source_authenticity)], ["Graph fingerprint", <code>{t.input.graph_fingerprint}</code>], ["Saved graph fingerprint matches", "Yes"]]} />
      <div className="inspector-counts">{Object.entries(t.input.graph_counts).map(([key, value]) => <span key={key}><b>{value}</b> {human(key)}</span>)}</div>
      <h3>Service dependencies</h3><SavedGraph spec={spec} layer="stage" />
      <h3>Action prerequisites</h3><SavedGraph spec={spec} layer="action" />
      <p>Arrows show only recorded edges. An unconnected node does not establish independence. Service and action relationships are separate.</p>
      <h3>Branch and parallel groups</h3>
      {graph.branch_groups.length === 0 && graph.parallel_groups.length === 0 && <p>No explicit branch or parallel groups were supplied.</p>}
      {graph.branch_groups.map(group => <div className="inspector-group" key={group.group_id}><strong>{group.selection}: {group.group_id}</strong><p>{group.selection === "XOR" ? "Exactly one applicable option" : group.selection === "AND" ? "All required options" : "One or more applicable options"}. This is supplied structure, not a selected citizen path.</p>
        {group.options.map(option => <div key={option.option_id}><code>{option.option_id}</code><p>Actions: {option.action_ids.join(", ") || "None supplied"}</p><p>Conditions: {option.condition_ids.join(", ") || "None supplied"}</p></div>)}</div>)}
      {graph.parallel_groups.map(group => <div className="inspector-group" key={group.group_id}><strong>Parallel: {group.group_id}</strong><p>{group.action_ids.join(", ")}</p><p>Explicit grouping only; no additional fork/join semantics inferred.</p></div>)}
      <Json title="Complete saved canonical graph, provenance and evidence" value={graph} />
    </Panel>
    <Panel id="trace-features" title="2. Seven source-based structural features">
      <p>Observed values describe supplied structure, not validated cognitive difficulty. Partial or unknown coverage has no exact value.</p>
      <div className="inspector-table"><table><thead><tr><th>Feature</th><th>Observed</th><th>Completeness</th><th>Exact</th><th>Scale</th><th>Normalized observed</th><th>Normalized exact</th></tr></thead>
        <tbody>{t.structural_features.map(f => <tr key={f.name}><th>{human(f.name)}</th><td>{f.measurement.observed}</td><td>{f.measurement.completeness}</td><td>{f.measurement.exact_value ?? "Unknown"}</td><td>{f.measurement.scale}</td><td>{number(f.measurement.normalized_observed)}</td><td>{f.measurement.normalized_exact === null ? "Unknown" : number(f.measurement.normalized_exact)}</td></tr>)}</tbody></table></div>
    </Panel>
    <Panel id="trace-context" title="3. Context at selection">
      <p>The original settings and processed history used for this decision. Current settings are shown separately below.</p>
      <ContextFacts trace={t} />
      <Json title="Original context snapshot" value={t.records.policy_offer.offer.context_snapshot} />
      <details><summary>81 named context encoding values</summary><div className="inspector-table"><table><thead><tr><th>Context term</th><th>Value</th></tr></thead><tbody>{t.selection.context_encoding.map(([key, value]) => <tr key={key}><th>{key}</th><td>{number(value)}</td></tr>)}</tbody></table></div></details>
    </Panel>
    <Panel id="trace-candidates" title="4. Original feasibility and candidate scores"><CandidateTable trace={t} /></Panel>
    <Panel id="trace-selection" title="5. Recorded policy selection">
      <Facts items={[["Decision", <code>{spec.decision_id}</code>], ["Policy run at selection", <code>{t.selection.policy_run_id}</code>], ["Selection mode", human(t.selection.selection_mode)], ["Recorded reason", t.selection.selection_reason], ["Prior version", t.selection.prior_version], ["Prior status", human(t.selection.prior_status)], ["Prior digest", t.selection.prior_digest], ["Selection model revision", t.selection.selection_posterior_revision], ["Feature dimension", t.selection.feature_names.length]]} />
      <p>Thompson scores are sampled linear surrogate values. Forced or baseline decisions may have posterior moments without a sampled score. No resampling or feature-importance explanation happens here.</p>
      <Json title="Original policy configuration, prior and numerical versions" value={{ config: decision.config, numerical_versions: decision.numerical_versions, feature_schema_version: decision.feature_schema_version, feature_schema_fingerprint: decision.feature_schema_fingerprint, draw_seed: decision.draw_seed }} />
      <Json title="Original 656 selected feature values and sampled parameters" value={{ names: t.selection.feature_names, selected_features: decision.selected_features, sampled_parameters: decision.sampled_parameters }} />
    </Panel>
    <Panel id="trace-content" title="6. Content and prepared wording provenance">
      <Facts items={[["Explanation origin", human(t.content.explanation_origin)], ["Assurance", human(t.content.assurance)], ["Recorded explanation cache hit", t.content.recorded_cache_hit ? "Yes" : "No"], ["Generated explanation items", t.content.generated_item_count], ["Source-copy items", t.content.source_copy_item_count], ["Wording snapshot", human(t.content.wording_status)], ["Wording origins", t.content.wording_origins.join(", ") || "Not available"], ["Wording digest", t.content.wording_digest]]} />
      <p>Fallback is source-preserving content. A generated origin or cache flag does not establish a live provider call for this presentation. Provider metadata, when present, belongs to artifact creation.</p>
      <Json title="Recorded content diagnostics" value={{ explanation: t.content.diagnostics, wording: t.content.wording_diagnostics }} />
      <Json title="Frozen wording resolution, artifact and style" value={{ resolution: t.records.wording, artifact: t.records.wording_artifact, style: t.records.wording_style }} />
      <Json title="Saved presentation specification and explanation" value={spec} />
    </Panel>
    <Panel id="trace-display" title="7. Display and navigation records">
      {t.adjustments && <><h3>Manual view lineage</h3><p>{t.adjustments.ledger.views.length} view changes · {t.adjustments.ledger.displays.length} manual display events · {t.adjustments.ledger.ratings.length} separate view ratings. These do not alter the recorded policy selection or its reward.</p><Json title="Manual views, Undo targets, display records and separate ratings" value={t.adjustments} /></>}
      <Facts items={[["Display status", human(t.display.status)], ["Recorded current action", t.display.current_action_id], ["Displayed action IDs", t.display.displayed_action_ids.join(", ") || "None acknowledged"], ["Navigation events", t.display.navigation_event_count]]} />
      <p>A client acknowledgment records display, not reading, comprehension, eligibility or completion. Inspecting this page does not acknowledge any action.</p>
      <Json title="Original acknowledgment and navigation events" value={{ acknowledgment: t.records.acknowledgment, navigation: t.records.navigation_events }} />
    </Panel>
    <Panel id="trace-learning" title="8. Attributed feedback and learning">
      <Facts items={[["Feedback status", human(t.learning.status)], ["Accepted reward", t.learning.reward === null ? "No accepted reward" : t.learning.reward], ["Selection revision", t.learning.selection_posterior_revision], ["Revision immediately before accepted update", t.learning.revision_immediately_before_update], ["Revision immediately after accepted update", t.learning.resulting_posterior_revision]]} />
      <p>About right → 1; need more / too much → 0. No response produces no update. Diagnostic reasons and preference changes are not additional rewards.</p>
      {t.learning.status === "accepted" && <><p>Derived from the original selected feature vector and recorded receipt: ΔA = φφᵀ / σ²; Δb = φ(reward − 0.5) / σ². The parameter snapshot immediately after this update was not separately stored.</p><Json title="Derived update terms" value={{ precision_rank_one_scale: t.learning.precision_rank_one_scale, centered_reward: t.learning.centered_reward, linear_delta_b: t.learning.linear_delta_b }} /></>}
      <Json title="Accepted feedback receipt and separate correction record" value={{ feedback: t.records.feedback, correction: t.records.correction }} />
      <h3>Current shared state, observed when this trace was read</h3>
      <Facts items={[["Current policy run", <code>{t.current.shared_policy_run_id}</code>], ["Current shared revision", t.current.shared_posterior_revision], ["Accepted feedback count", t.current.accepted_feedback_count], ["Current posterior fingerprint", <code>{t.current.shared_posterior_fingerprint}</code>]]} />
      <Json title="Current routing and current user settings" value={{ guidance: t.current.guidance, user_settings: t.current.user_settings }} />
    </Panel>
    <Panel id="trace-evidence" title="9. Evidence boundaries">
      <p>Recorded fields, derived summaries and unavailable evidence are distinguished explicitly. This is a projection of saved records, not a live execution timeline.</p>
      {t.evidence_boundaries.map((b, i) => <div className="inspector-boundary" key={i}><span className={"inspector-badge " + b.kind}>{b.kind}</span><strong>{human(b.section)}</strong><p>{b.explanation}</p><code>{b.location}</code></div>)}
      <Json title="Complete trace JSON" value={t} />
    </Panel>
  </>;
}
