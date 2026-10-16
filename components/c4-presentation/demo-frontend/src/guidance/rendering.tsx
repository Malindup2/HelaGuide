import { useEffect, useRef } from "react";
import type { Card, Document, Item, Page, Spec } from "./types";
import { actionLabel, itemKey } from "./types";

function SourceCard({ card }: { card: Card }) {
  const body = <>{card.lines.map((line, index) => <p key={index}>{line}</p>)}</>;
  if (card.collapsed) return (
    <details className="source-card source-disclosure">
      <summary>{card.title} <span className="helper-text">Supplementary</span></summary>{body}
    </details>
  );
  return <div className={"source-card source-kind-" + card.source.kind}><h4>{card.title}</h4>{body}</div>;
}
export function SourceItems({ doc, refs }: { doc: Document; refs: Item[] }) {
  const cards = new Map(doc.cards.map((card) => [itemKey(card.source), card]));
  return <>{refs.map((ref) => {
    const card = cards.get(itemKey(ref));
    return card ? <SourceCard key={itemKey(ref)} card={card} /> : null;
  })}</>;
}
export function ActionSection({ doc, page, index, disabled, observeToken, onVisible }: {
  doc: Document; page: Page; index: number; disabled: boolean; observeToken: string;
  onVisible: (id: string) => void;
}) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    const element = ref.current;
    if (!element || disabled) return;
    let delivered = false;
    const deliver = () => {
      if (delivered || document.visibilityState !== "visible") return;
      const rect = element.getBoundingClientRect();
      if (rect.bottom <= 0 || rect.top >= window.innerHeight || rect.right <= 0 || rect.left >= window.innerWidth) return;
      delivered = true;
      onVisible(page.action_id);
    };
    // Availability/visibility is observable; it is not evidence of reading or comprehension.
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) deliver();
    }, { threshold: 0 });
    observer.observe(element);
    document.addEventListener("visibilitychange", deliver);
    return () => { observer.disconnect(); document.removeEventListener("visibilitychange", deliver); };
  }, [disabled, observeToken, onVisible, page.action_id]);

  const graph = doc.explanation.source.graph;
  const stage = graph.stages.find((row) => row.service_id === page.service_id);
  const relevant = [
    ...page.condition_ids.map((id) => ({ kind: "condition", identifier: id })),
    ...(page.branch_group_id ? [{ kind: "branch_group", identifier: page.branch_group_id }] : []),
    ...(stage ? [{ kind: "fact", identifier: stage.fee_fact_id }, ...stage.document_fact_ids.map((id) => ({ kind: "fact", identifier: id }))] : []),
  ];
  const annotations = doc.explanation.explanations.filter((row) => row.action_id === page.action_id && row.origin === "generated");
  return (
    <article ref={ref} className="action-section" aria-label={"Procedure action " + (index + 1)}>
      <div className="action-heading"><span className="action-number">{String(index + 1).padStart(2, "0")}</span>
        <div><span className="eyebrow">{stage?.name ?? page.service_id}</span><h3>{actionLabel(doc, page.action_id)}</h3>
          {stage && <p className="muted">Agency: {stage.agency}</p>}</div></div>
      {page.branch_group_id && <p className="applicability-note">Alternative-path action. Check the supplied conditions and selection meaning below; viewing this action does not select a path.</p>}
      <SourceItems doc={doc} refs={relevant} />
      {page.prerequisite_cues.length > 0 && <aside className="prerequisite-callout"><strong>Before this action</strong><SourceItems doc={doc} refs={page.prerequisite_cues} /></aside>}
      <SourceItems doc={doc} refs={page.items} />
      {annotations.length > 0 && <aside className="explanation-annotation"><strong>Additional explanation</strong>
        {annotations.map((row) => <div key={row.unit_id}><p>{row.text}</p>
          {row.citations.map((citation, i) => <blockquote key={i}><p>{citation.quote}</p><cite>{citation.evidence_id}</cite></blockquote>)}
          <p className="helper-text">Supporting evidence: {row.evidence_ids.join(", ")}. Original source requirements remain above.</p>
        </div>)}</aside>}
    </article>
  );
}
const branchMeanings = {
  AND: "All options apply under the supplied applicability.",
  OR: "One or more applicable options may be selected.",
  XOR: "Exactly one applicable option is selected.",
};
export function SelectedAids({ spec }: { spec: Spec }) {
  const diagram = spec.diagram;
  return <>
    {spec.recap && <aside className="recap-panel"><span className="eyebrow">Previously displayed</span><h3>A reminder from earlier guidance</h3>
      <ul>{spec.recap.action_ids.map((id) => <li key={id}>{actionLabel(spec, id)}</li>)}</ul>
      <p className="helper-text">Previously displayed does not mean completed. No prerequisite completion is inferred.</p></aside>}
    {diagram.kind !== "NONE" && <section className="relationship-panel" aria-label="Selected relationship aid">
      <p className="eyebrow">Selected relationship aid</p>
      <h3>{diagram.kind === "DEPENDENCY_MAP" ? "What depends on what" : diagram.kind === "BRANCH_MAP" ? "Understand the available paths" : "Actions explicitly represented as parallel"}</h3>
      {diagram.kind === "DEPENDENCY_MAP" && <>
        {diagram.stage_dependencies.map((edge) => <div className="relationship-edge" key={edge.edge_id}>
          <span>{diagram.stages.find((row) => row.service_id === edge.source_id)?.name ?? edge.source_id}</span>
          <span className="relationship-arrow">→<small>service dependency</small></span>
          <span>{diagram.stages.find((row) => row.service_id === edge.target_id)?.name ?? edge.target_id}</span>
        </div>)}
        {diagram.action_prerequisites.map((edge) => <div className="relationship-edge" key={edge.edge_id}>
          <span>{actionLabel(spec, edge.source_id)}</span><span className="relationship-arrow">→<small>must precede</small></span><span>{actionLabel(spec, edge.target_id)}</span>
        </div>)}
        <p className="helper-text">Only supplied directed edges are shown. This does not establish completion or infer AND/OR relationships.</p>
      </>}
      {diagram.kind === "BRANCH_MAP" && diagram.branch_groups.map((group) => <div className="relationship-group" key={group.group_id}>
        <strong>{group.selection}: {branchMeanings[group.selection]}</strong>
        <div className="relationship-options">{group.options.map((option) => <div className="relationship-option" key={option.option_id}>
          <span className="tag">{option.option_id}</span>
          <ul>{option.action_ids.map((id) => <li key={id}>{actionLabel(spec, id)}</li>)}</ul>
          {option.condition_ids.map((id) => <p key={id}>{spec.explanation.source.graph.conditions.find((row) => row.condition_id === id)?.text ?? id}</p>)}
        </div>)}</div><p className="helper-text">The application does not decide eligibility or choose an option for you.</p>
      </div>)}
      {diagram.kind === "PARALLEL_MAP" && diagram.parallel_groups.map((group) => <div className="relationship-group" key={group.group_id}>
        <div className="relationship-options">{group.action_ids.map((id) => <div className="relationship-option" key={id}>{actionLabel(spec, id)}</div>)}</div>
        <p className="helper-text">These actions are explicitly grouped as parallel, subject to their supplied applicability and prerequisites. No other independence is inferred.</p>
      </div>)}
    </section>}
  </>;
}
