import type { Configuration, Doc, RenderedAction, ScopedFact } from '../types';
import { cueView, formatAmount, paragraphs, scopeNote } from '../model';
import { ChevronIcon, DocIcon, FeeIcon } from '../ui';

/** Documents and charges exactly as scoped by the backend. A stage or service fact is never shown as a step payment. */
export function Facts({ facts, doc, label = true }: { facts: ScopedFact[]; doc: Doc; label?: boolean }) {
  const docs = facts.filter(f => f.fact.kind === 'document'), fees = facts.filter(f => f.fact.kind === 'fee');
  if (facts.length === 0) return null;
  const tag = (f: ScopedFact, fee: boolean) => {
    const note = scopeNote(doc, f);
    return <span className={`cz-tag${fee ? ' cz-fee' : ''}`} key={f.id}>{fee ? <FeeIcon /> : <DocIcon />}
      {fee ? <b>{formatAmount(f.fact)}</b> : f.fact.name}{note && <small>{note}</small>}{f.qualification && <small>{f.qualification}</small>}</span>;
  };
  return <div className="cz-facts">
    {docs.length > 0 && <p>{label && <span className="cz-k">Documents</span>}{docs.map(f => tag(f, false))}</p>}
    {fees.length > 0 && <p>{label && <span className="cz-k">{fees.every(f => f.scope === 'action' || f.scope === 'route') ? 'Charge' : 'Charges recorded'}</span>}{fees.map(f => tag(f, true))}</p>}
  </div>;
}

/** Passages of source text about facts, so qualifications and exclusions stay reachable without being invented. */
export function SourceWording({ facts, doc }: { facts: ScopedFact[]; doc: Doc }) {
  const shown = facts.filter(f => (f.source_context?.length ?? 0) > 0);
  if (shown.length === 0) return null;
  return <details className="cz-more"><summary>Source wording about these items</summary>
    {shown.map(f => <div key={f.id} className="cz-passages"><b>{f.fact.kind === 'fee' ? formatAmount(f.fact) : f.fact.name}</b>
      {f.source_context!.map(p => <p key={p.content_id}>{paragraphs(p.text, doc.source_limit).join(' ')}</p>)}</div>)}
  </details>;
}

export function Marker({ text, kind = 'step' }: { text: string; kind?: 'step' | 'route' }) {
  return text ? <span className={`cz-mark cz-mark-${kind}`} aria-hidden="true">{text}</span> : null;
}

type BodyProps = {
  action: RenderedAction; doc: Doc; config: Configuration; open: boolean; onToggle: (id: string, open: boolean) => void;
  hideConditions?: string[]; showFacts?: boolean; heading?: string;
};

/**
 * One step. The essential layer (instruction, conditions, destination, scoped facts) is always visible.
 * Only the reviewed explanation remainder can sit behind More/Less, and only when Disclosure is ON.
 */
export function StepBody({ action, doc, config, open, onToggle, hideConditions = [], showFacts = true, heading }: BodyProps) {
  const conditions = action.conditions.filter(c => !hideConditions.includes(c));
  const cues = config.relationships === 'inline' ? doc.relationship_aid.inline_by_action[action.id] ?? [] : [];
  const detailed = config.explanation === 'detailed';
  // A fallback heading is the instruction's own first sentence; show it once rather than twice. Nothing is dropped.
  const essential = (() => {
    const ps = paragraphs(action.essential, doc.source_limit);
    if (heading && ps[0]?.startsWith(heading)) { const rest = ps[0].slice(heading.length).replace(/^[.\s]+/, ''); return rest ? [rest, ...ps.slice(1)] : ps.slice(1); }
    return ps;
  })();
  return <div className="cz-body" id={`cz-body-${action.id}`}>
    {conditions.length > 0 && <p className="cz-cond"><b>Applies when</b> {conditions.join(' and ')}</p>}
    {essential.map((p, i) => <p key={i} className="cz-essential">{p}</p>)}
    {(action.destination || action.actor) && <p className="cz-where">{action.destination && <><b>Where</b> {action.destination} </>}{action.actor && <><b>Who</b> {action.actor}</>}</p>}
    {showFacts && <Facts facts={action.facts} doc={doc} />}
    {showFacts && <SourceWording facts={action.facts} doc={doc} />}
    {cues.length > 0 && <ul className="cz-cues" data-support="relationships">{cues.map(c => { const v = cueView(c); return <li key={c.relation_id + c.text}><b>{v.label}</b> {v.body}</li>; })}</ul>}
    {action.explanation_visible && <div className="cz-expl" data-support="explanation">{detailed && <span className="cz-label">In more detail</span>}
      {paragraphs(action.explanation_visible, doc.source_limit).map((p, i) => <p key={i}>{p}</p>)}</div>}
    {config.disclosure === 'on' && action.explanation_hidden && <div data-support="disclosure">
      <button type="button" className="cz-toggle" aria-expanded={open} aria-controls={`cz-expl-${action.id}`} onClick={() => onToggle(action.id, !open)}>
        {open ? 'Less' : 'More'}<ChevronIcon /></button>
      {open && <div className="cz-expl" id={`cz-expl-${action.id}`}>{detailed && <span className="cz-label">In more detail</span>}
        {paragraphs(action.explanation_hidden, doc.source_limit).map((p, i) => <p key={i}>{p}</p>)}</div>}
    </div>}
  </div>;
}
