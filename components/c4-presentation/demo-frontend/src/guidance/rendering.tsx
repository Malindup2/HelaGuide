import { useEffect, useRef } from "react";
import type { Card, Document, Item, Page, Spec } from "./types";
import { itemKey } from "./types";
import { actionDomId, actionTitle } from "./scaffoldModel";
import RelationshipMap from "./RelationshipMap";

function GeneratedText({ annotations }: { annotations: Document["explanation"]["explanations"] }) {
  if (!annotations.length) return null;
  return <aside className="explanation-annotation"><strong>Additional explanation</strong>
    {annotations.map((row) => <div key={row.unit_id}><p>{row.text}</p>
      {row.citations.map((citation, index) => <blockquote key={index}><p>{citation.quote}</p><cite>{citation.evidence_id}</cite></blockquote>)}
      <p className="helper-text">Supporting evidence: {row.evidence_ids.join(", ")}. The original source text remains above.</p>
    </div>)}</aside>;
}
function SourceCard({ card, annotations = [] }: { card: Card; annotations?: Document["explanation"]["explanations"] }) {
  const body = <><div className="source-lines">{card.lines.map((line, index) => <p key={index}>{line}</p>)}</div>
    <GeneratedText annotations={annotations} /></>;
  if (card.collapsed) return (
    <details className="source-card source-disclosure" data-source-kind={card.source.kind} data-source-id={card.source.identifier}>
      <summary><span>{card.title}</span><span className="disclosure-label">Optional context <span aria-hidden="true">+</span></span></summary>
      <div className="disclosure-body">{body}</div>
    </details>
  );
  return <div className={"source-card source-kind-" + card.source.kind} data-source-kind={card.source.kind} data-source-id={card.source.identifier}>
    <h4>{card.title}</h4>{body}</div>;
}
export function SourceItems({ doc, refs, annotationActionId }: { doc: Document; refs: Item[]; annotationActionId?: string }) {
  const cards = new Map(doc.cards.map((card) => [itemKey(card.source), card]));
  return <>{refs.map((ref) => {
    const card = cards.get(itemKey(ref));
    const annotations = annotationActionId && ref.kind === "content" ? doc.explanation.explanations.filter((row) =>
      row.action_id === annotationActionId && row.content_id === ref.identifier && row.origin === "generated") : [];
    return card ? <SourceCard key={itemKey(ref)} card={card} annotations={annotations} /> : null;
  })}</>;
}
export function PrerequisiteCues({ doc, refs }: { doc: Document; refs: Item[] }) {
  if (!refs.length) return null;
  const graph = doc.explanation.source.graph;
  return <aside className="prerequisite-callout scaffold-cues">
    <span className="eyebrow">Before you begin</span><h4>Check the prerequisites</h4>
    <ul>{refs.map((ref) => {
      const actionEdge = ref.kind === "action_prerequisite" ? graph.action_prerequisites.find((row) => row.edge_id === ref.identifier) : null;
      const stageEdge = ref.kind === "stage_dependency" ? graph.stage_dependencies.find((row) => row.edge_id === ref.identifier) : null;
      if (actionEdge) return <li key={itemKey(ref)}>First complete: <strong>{actionTitle(doc, actionEdge.source_id)}</strong></li>;
      if (stageEdge) return <li key={itemKey(ref)}>This service depends on: <strong>{graph.stages.find((row) => row.service_id === stageEdge.source_id)?.name ?? stageEdge.source_id}</strong></li>;
      return <li key={itemKey(ref)}><SourceItems doc={doc} refs={[ref]} /></li>;
    })}</ul>
    <p className="helper-text">These are supplied requirements. Viewing an earlier action does not confirm its completion.</p>
  </aside>;
}
function ActionFacts({ doc, page }: { doc: Document; page: Page }) {
  const stage = doc.explanation.source.graph.stages.find((row) => row.service_id === page.service_id);
  if (!stage) return null;
  const lookup = (id: string) => doc.cards.find((card) => card.source.kind === "fact" && card.source.identifier === id)?.lines[0];
  const fee = lookup(stage.fee_fact_id);
  const documents = stage.document_fact_ids.map(lookup).filter((line): line is string => !!line);
  return <dl className="action-facts">
    {fee && <div><dt>Fee for this service</dt><dd>{fee}</dd></div>}
    {documents.length > 0 && <div><dt>Required documents</dt><dd><ul>{documents.map((line, index) => <li key={index}>{line}</li>)}</ul></dd></div>}
  </dl>;
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
      delivered = true; onVisible(page.action_id);
    };
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) deliver();
    }, { threshold: 0 });
    observer.observe(element);
    document.addEventListener("visibilitychange", deliver);
    return () => { observer.disconnect(); document.removeEventListener("visibilitychange", deliver); };
  }, [disabled, observeToken, onVisible, page.action_id]);

  const graph = doc.explanation.source.graph;
  const stage = graph.stages.find((row) => row.service_id === page.service_id);
  const group = graph.branch_groups.find((row) => row.group_id === page.branch_group_id);
  const primaryItems = page.items.filter((item) => item.kind === "content");
  const otherItems = page.items.filter((item) => item.kind !== "content");
  return <article ref={ref} id={actionDomId(page.action_id)} tabIndex={-1} className="action-section" aria-label={"Procedure action " + (index + 1)}>
    <div className="action-heading"><span className="action-number">{String(index + 1).padStart(2, "0")}</span>
      <div><span className="eyebrow">{stage?.name ?? page.service_id}</span><h3>{actionTitle(doc, page.action_id)}</h3>
        {stage && <p className="muted">Agency: {stage.agency}</p>}</div></div>
    {group && <p className="applicability-note"><strong>{group.selection === "XOR" ? "One alternative only" : group.selection === "OR" ? "One or more applicable alternatives" : "All applicable options"}.</strong> Check the supplied conditions. Viewing this action does not select an option.</p>}
    {page.condition_ids.length > 0 && <div className="action-conditions"><strong>Applies under these supplied conditions</strong>
      {page.condition_ids.map((id) => <p key={id}>{graph.conditions.find((row) => row.condition_id === id)?.text ?? id}</p>)}</div>}
    <PrerequisiteCues doc={doc} refs={page.prerequisite_cues} />
    <SourceItems doc={doc} refs={primaryItems} annotationActionId={page.action_id} />
    <ActionFacts doc={doc} page={page} />
    {otherItems.length > 0 && <div className="action-source-records"><SourceItems doc={doc} refs={otherItems} /></div>}
  </article>;
}
export function SelectedAids({ spec, currentActionId }: { spec: Spec; currentActionId?: string | null }) {
  return <>
    {spec.recap && <aside className="recap-panel scaffold-recap"><div className="scaffold-heading">
      <div><p className="eyebrow">Previously displayed</p><h3>Pick up the context</h3></div><span className="scaffold-icon" aria-hidden="true">↶</span></div>
      <ul className="recap-actions">{spec.recap.action_ids.map((id) => <li key={id}>
        <span className="recap-number">{spec.pages.findIndex((page) => page.action_id === id) + 1}</span>
        <span>{actionTitle(spec, id)}</span><small>Displayed earlier</small>
      </li>)}</ul>
      <p className="helper-text">Previously displayed does not mean completed. No prerequisite completion is inferred.</p>
    </aside>}
    <RelationshipMap spec={spec} currentActionId={currentActionId} />
  </>;
}
export function SourceRegister({ doc }: { doc: Document }) {
  const groups = [
    { title: "Requirements and conditions", kinds: ["fact", "condition", "branch_group", "parallel_group", "stage_dependency", "action_prerequisite"] },
    { title: "Sources and provenance", kinds: ["evidence", "provenance"] },
    { title: "Service records", kinds: ["stage"] },
  ];
  const grouped = new Set(groups.flatMap((group) => group.kinds));
  const additional = doc.global_items.filter((ref) => ref.kind !== "notice" && !grouped.has(ref.kind));
  return <section className="source-register compact-register" aria-label="Procedure-wide requirements and source information">
    <div className="section-heading"><div><p className="eyebrow">Source information</p><h3>Requirements and supporting records</h3></div></div>
    <p className="helper-text">These supplied records remain available throughout. A diagram does not replace requirements or establish completion.</p>
    {groups.map((group) => {
      const refs = doc.global_items.filter((ref) => group.kinds.includes(ref.kind));
      return refs.length ? <section className="source-register-group" key={group.title}><h4>{group.title}</h4>
        <div className="source-register-grid"><SourceItems doc={doc} refs={refs} /></div></section> : null;
    })}
    {additional.length > 0 && <SourceItems doc={doc} refs={additional} />}
  </section>;
}
