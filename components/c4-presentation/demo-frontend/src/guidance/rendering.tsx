import { useEffect, useRef } from "react";
import type { Card, Document, Item, Page, Spec, Navigation } from "./types";
import { actionFactItems, contentCoveredByNotice, itemKey, serviceFactItems } from "./types";
import { actionDomId, actionTitle } from "./scaffoldModel";
import RelationshipMap from "./RelationshipMap";
import { preparedText, previousViewedAction } from "./wording";

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
export function SourceItems({ doc, refs, annotationActionId, suppressAnnotations = false }: { doc: Document; refs: Item[]; annotationActionId?: string; suppressAnnotations?: boolean }) {
  const cards = new Map(doc.cards.map((card) => [itemKey(card.source), card]));
  return <>{refs.map((ref) => {
    const card = cards.get(itemKey(ref));
    const annotations = !suppressAnnotations && annotationActionId && ref.kind === "content" ? doc.explanation.explanations.filter((row) =>
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
      const wording = preparedText(doc, "prerequisite_explanation", ref.kind, ref.identifier);
      if (actionEdge) return <li key={itemKey(ref)}>{wording && <p>{wording}</p>}First complete: <strong>{actionTitle(doc, actionEdge.source_id)}</strong></li>;
      if (stageEdge) return <li key={itemKey(ref)}>{wording && <p>{wording}</p>}This service depends on: <strong>{graph.stages.find((row) => row.service_id === stageEdge.source_id)?.name ?? stageEdge.source_id}</strong></li>;
      return <li key={itemKey(ref)}><SourceItems doc={doc} refs={[ref]} /></li>;
    })}</ul>
    <p className="helper-text">These are supplied requirements. Viewing an earlier action does not confirm its completion.</p>
  </aside>;
}
export function ServiceRequirements({ doc }: { doc: Document }) {
  const actionLinked = new Set(doc.pages.flatMap((page) => actionFactItems(doc, page.action_id).map((item) => item.identifier)));
  const available = new Set(serviceFactItems(doc).filter((item) => !actionLinked.has(item.identifier)).map((item) => item.identifier));
  const emitted = new Set<string>();
  const services = doc.explanation.source.graph.stages.map((stage) => {
    const refs = [stage.fee_fact_id, ...stage.document_fact_ids].filter((id) => {
      if (!available.has(id) || emitted.has(id)) return false;
      emitted.add(id); return true;
    }).map((identifier) => ({ kind: "fact", identifier }));
    return { stage, refs };
  }).filter((service) => service.refs.length > 0);
  if (!services.length) return null;
  return <section className="source-register" aria-label="Service fees and documents">
    <h3>Service fees and documents</h3>
    <p className="helper-text">These records apply to the named service, not as an additional charge at each action. Read the scope information above for fee exclusions and applicability.</p>
    {services.map(({ stage, refs }) => <section key={stage.service_id} className="source-register-group">
      <h4>{stage.name}</h4><p className="muted">Agency: {stage.agency}</p>
      <div className="source-register-grid"><SourceItems doc={doc} refs={refs} /></div>
    </section>)}
  </section>;
}
export function ActionRequirements({ doc, actionId }: { doc: Document; actionId: string }) {
  const refs = actionFactItems(doc, actionId);
  const stage = doc.explanation.source.graph.stages.find((row) =>
    doc.explanation.source.graph.actions.some((a) => a.action_id === actionId && a.service_id === row.service_id));
  const fee = refs.filter((ref) => ref.identifier === stage?.fee_fact_id);
  const documents = refs.filter((ref) => stage?.document_fact_ids.includes(ref.identifier));
  if (!refs.length) return <p className="helper-text">No action-specific fee or document links were supplied. This does not mean the step is free or needs no documents.</p>;
  return <section className="action-facts" aria-label="Requirements for this step">
    {fee.length > 0 && <div><h4>Fee associated with this step</h4><SourceItems doc={doc} refs={fee} />
      <p className="helper-text">Read the step explanation for payment timing and exclusions. A repeated fee reference is the same charge.</p></div>}
    {documents.length > 0 && <div><h4>Documents used or prepared in this step</h4><SourceItems doc={doc} refs={documents} /></div>}
    <SourceItems doc={doc} refs={refs.filter((ref) => !fee.includes(ref) && !documents.includes(ref))} />
  </section>;
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
  const primaryItems = page.items.filter((item) => item.kind === "content" &&
    (!contentCoveredByNotice(doc, item.identifier) || doc.explanation.explanations.some((row) =>
      row.action_id === page.action_id && row.content_id === item.identifier && row.origin === "generated")));
  const otherItems = page.items.filter((item) => item.kind !== "content");
  const preparedExplanation = preparedText(doc, "action_explanation", "action", page.action_id);
  return <article ref={ref} id={actionDomId(page.action_id)} tabIndex={-1} className="action-section" aria-label={"Procedure action " + (index + 1)}>
    <div className="action-heading"><span className="action-number">{String(index + 1).padStart(2, "0")}</span>
      <div><span className="eyebrow">{stage?.name ?? page.service_id}</span><h3>{actionTitle(doc, page.action_id)}</h3>
        {stage && <p className="muted">Agency: {stage.agency}</p>}</div></div>
    {group && <p className="applicability-note"><strong>{group.selection === "XOR" ? "Part of one applicant route" : group.selection === "OR" ? "Part of an applicable route" : "All required parts"}.</strong> This step belongs to the route described below. Other steps in the same route may also be required.</p>}
    {page.condition_ids.length > 0 && <div className="action-conditions"><strong>Applies under these supplied conditions</strong>
      {page.condition_ids.map((id) => <p key={id}>{graph.conditions.find((row) => row.condition_id === id)?.text ?? id}</p>)}</div>}
    <PrerequisiteCues doc={doc} refs={page.prerequisite_cues} />
    {preparedExplanation && <aside className="prepared-step-explanation" aria-label="Step explanation"><p>{preparedExplanation}</p></aside>}
    <SourceItems doc={doc} refs={primaryItems} annotationActionId={page.action_id} suppressAnnotations={!!preparedExplanation} />
    <ActionRequirements doc={doc} actionId={page.action_id} />
    {otherItems.length > 0 && <div className="action-source-records"><SourceItems doc={doc} refs={otherItems} /></div>}
  </article>;
}
export function PreviousStepSummary({ spec, navigation, currentActionId }: {
  spec: Spec; navigation: Navigation | null; currentActionId: string | null;
}) {
  const previous = previousViewedAction(spec, navigation, currentActionId);
  if (!previous) return null;
  const summary = preparedText(spec, "action_summary", "action", previous);
  return <aside className="guided-previous-summary" aria-label="Previous viewed step">
    <p className="eyebrow">From your previous step</p>
    <h4>{actionTitle(spec, previous)}</h4>
    {summary && <p>{summary}</p>}
    <p className="helper-text">A reminder of information shown, not confirmation of completion.</p>
  </aside>;
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
export function SourceRegister({ doc, serviceFactsRendered = false }: { doc: Document; serviceFactsRendered?: boolean }) {
  const renderedFacts = new Set(serviceFactsRendered ? serviceFactItems(doc).map(itemKey) : []);
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
      const refs = doc.global_items.filter((ref) => group.kinds.includes(ref.kind) && !renderedFacts.has(itemKey(ref)));
      return refs.length ? <section className="source-register-group" key={group.title}><h4>{group.title}</h4>
        <div className="source-register-grid"><SourceItems doc={doc} refs={refs} /></div></section> : null;
    })}
    {additional.length > 0 && <SourceItems doc={doc} refs={additional} />}
  </section>;
}
