import { useEffect, useRef } from 'react';
import type { Action, Configuration, Document, EventInput } from '../types';
import { expressionText } from '../semantics';
import { actionFacts, agencies, displayTitle, factLabel } from '../presentation';
import type { resolveLayout } from '../presentation';
import { DocIcon, FeeIcon } from './parts';

export type Layout = ReturnType<typeof resolveLayout>;
export type BodyProps = {
  action: Action; doc: Document; config: Configuration; layout: Layout; viewId: string; readOnly: boolean;
  /** Condition texts already shown by the surrounding route header. */
  shownConditions?: string[]; event: (e: EventInput) => void; jump: (id: string) => void;
};

export function NeedsLine({ doc, action, reference }: { doc: Document; action: Action; reference: boolean }) {
  const facts = actionFacts(doc, action), docs = facts.filter(f => f.kind === 'document'), fees = facts.filter(f => f.kind === 'fee');
  if (facts.length === 0) return null;
  if (reference) return <p className="gc-needs-ref gc-fine">Needs {docs.length > 0 && `${docs.length} document${docs.length === 1 ? '' : 's'}`}{docs.length > 0 && fees.length > 0 && ' · '}{fees.length > 0 && `${fees.length} charge${fees.length === 1 ? '' : 's'}`} — listed in Before you start</p>;
  return <div className="gc-needs">
    {docs.length > 0 && <p><span className="gc-k">Bring</span>{docs.map(f => <span className="gc-tag" key={f.fact_id}><DocIcon />{factLabel(f, doc)}</span>)}</p>}
    {fees.length > 0 && <p><span className="gc-k">Pay</span>{fees.map(f => {
      const stage = doc.stages.find(s => s.fee_fact_id === f.fact_id)?.name;
      return <span className="gc-tag gc-fee" key={f.fact_id}><FeeIcon /><b>{f.currency} {f.value}</b>{stage && <small>{stage}</small>}</span>;
    })}</p>}
  </div>;
}

/** One quiet line for collapsed rows, so required documents and charges are never hidden behind a tap. */
export function NeedsInline({ doc, action }: { doc: Document; action: Action }) {
  const facts = actionFacts(doc, action), docs = facts.filter(f => f.kind === 'document'), fees = facts.filter(f => f.kind === 'fee');
  if (facts.length === 0) return null;
  return <p className="gc-needs-line">{docs.length > 0 && <>Bring {docs.map(f => factLabel(f, doc)).join(', ')}</>}{docs.length > 0 && fees.length > 0 && ' · '}{fees.length > 0 && <>Pay {fees.map(f => `${f.currency} ${f.value}`).join(', ')}</>}</p>;
}

/** Conditions, prerequisites and joins stay visible even when a row is collapsed. */
export function Cues({ action, doc, layout, shownConditions = [], jump }: Pick<BodyProps, 'action' | 'doc' | 'layout' | 'shownConditions' | 'jump'>) {
  const prerequisites = doc.edges.filter(e => e.target_id === action.id), joins = doc.joins.filter(j => j.target === action.id);
  const own = action.conditions.filter(c => !shownConditions.includes(c));
  const titleOf = (id: string) => { const a = doc.actions.find(x => x.id === id); return a ? displayTitle(a) : id; };
  if (own.length + prerequisites.length + joins.length === 0) return null;
  return <div className="gc-cues">
    {own.length > 0 && <p className="gc-cond"><b>Applies when</b> {own.join(' AND ')}</p>}
    {prerequisites.length > 0 && (layout.cues === 'text'
      ? <p className="gc-pre"><b>Do first</b> {prerequisites.map(p => titleOf(p.source_id)).join('; ')}.</p>
      : <p className="gc-pre" data-support="relationships"><b>After</b>{prerequisites.map(p => <button type="button" className="gc-ref" key={p.source_id} onClick={() => jump(p.source_id)}>{titleOf(p.source_id)}</button>)}</p>)}
    {joins.map((j, i) => <p className="gc-pre" key={i}><b>Requires</b> {expressionText(j.requirement, doc)}.</p>)}
  </div>;
}

export default function ActionBody({ action, doc, layout, viewId, readOnly, event }: BodyProps) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const element = ref.current;
    if (!element || readOnly) return;
    const observer = new IntersectionObserver(entries => {
      if (entries.some(e => e.isIntersecting)) { event({ type: 'action_visible', action_id: action.id }); observer.disconnect(); }
    }, { threshold: 0.1 });
    observer.observe(element);
    return () => observer.disconnect();
  }, [action.id, viewId, event, readOnly]);

  const fuller = layout.explanation === 'full' && action.expanded !== action.concise;
  const paragraphs = (layout.explanation === 'full' ? action.expanded : action.concise).split('\n\n');
  const owner = action.actor ? `Responsible: ${action.actor}` : agencies(doc).length > 1 ? `Service agency: ${action.service_agency}` : null;
  return <div ref={ref} className="gc-body" id={`gc-body-${action.id}`}>
    {owner && <p className="gc-fine">{owner}</p>}
    <NeedsLine doc={doc} action={action} reference={layout.needs === 'reference'} />
    <div className={fuller ? 'gc-prose gc-prose-full' : 'gc-prose'} data-support={fuller ? 'explanation' : undefined}>
      {fuller && <span className="gc-label">Fuller explanation</span>}
      {paragraphs.map((p, i) => <p key={i} className={fuller && i > 0 ? 'gc-more' : undefined}>{p}</p>)}
    </div>
    {action.optional.map((block, i) => <div className="gc-extra" data-support="disclosure" key={`${viewId}:${block.id}`}>
      <details open={layout.optionalOpen}>
        <summary onClick={e => { if (!readOnly) event({ type: (e.currentTarget.parentElement as HTMLDetailsElement).open ? 'detail_close' : 'detail_open', action_id: action.id, value: block.id }); }}>
          Extra info{action.optional.length > 1 ? ` (${i + 1} of ${action.optional.length})` : ''}</summary>
        <p>{block.text}</p></details></div>)}
    {action.unreviewed_supplement.map((text, i) => <aside className="gc-note" key={i}><b>Source note</b><p>{text}</p></aside>)}
  </div>;
}
