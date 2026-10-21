import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import type { Action, Configuration, Document, EventInput } from '../types';
import { expressionText } from '../semantics';
import { agencies, displayTitle } from '../presentation';
import type { Mark } from '../presentation';
import { NeedsRow } from './parts';

type Props = {
  action: Action; mark: Mark; doc: Document; config: Configuration; viewId: string; readOnly: boolean;
  event: (e: EventInput) => void; jump: (id: string) => void; recap?: ReactNode;
};

export default function StepCard({ action, mark, doc, config, viewId, readOnly, event, jump, recap }: Props) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    const element = ref.current;
    if (!element || readOnly) return;
    const observer = new IntersectionObserver(entries => {
      if (entries.some(e => e.isIntersecting)) { event({ type: 'action_visible', action_id: action.id }); observer.disconnect(); }
    }, { threshold: 0.1 });
    observer.observe(element);
    return () => observer.disconnect();
  }, [action.id, viewId, event, readOnly]);

  const prerequisites = doc.edges.filter(e => e.target_id === action.id);
  const titleOf = (id: string) => { const a = doc.actions.find(x => x.id === id); return a ? displayTitle(a) : undefined; };
  const expanded = config.explanation === 'expanded' && action.expanded !== action.concise;
  const paragraphs = (config.explanation === 'expanded' ? action.expanded : action.concise).split('\n\n');
  const owner = action.actor ? `Responsible: ${action.actor}` : agencies(doc).length > 1 ? `Service agency: ${action.service_agency}` : null;
  const compactNeeds = config.summary === 'on' && config.navigation === 'overview';

  return <article ref={ref} id={`v2-${action.id}`} className="v2-action" tabIndex={-1}>
    <header className="v2-action-head"><span className={`v2-num v2-num-${mark.kind}`} aria-hidden="true">{mark.label || '•'}</span>
      <div><h3 id={`v2-h-${action.id}`} tabIndex={-1}>{mark.note && <span className="sr-only">{mark.note}: </span>}{displayTitle(action)}</h3>
        {mark.note && <p className="v2-routenote">{mark.note}</p>}</div></header>
    {recap}
    {owner && <p className="v2-fine">{owner}</p>}
    {action.conditions.length > 0 && <p className="v2-condition"><strong>Applies when:</strong> {action.conditions.join(' AND ')}</p>}
    {prerequisites.length > 0 && (config.relationships === 'none'
      ? <p className="v2-dofirst"><strong>Do first:</strong> {prerequisites.map(p => titleOf(p.source_id)).join('; ')}.</p>
      : <aside className="v2-dofirst" data-support="relationships"><strong>Do first:</strong> {prerequisites.map(p => <button type="button" key={p.source_id} onClick={() => jump(p.source_id)}>{titleOf(p.source_id)}</button>)}</aside>)}
    {doc.joins.filter(j => j.target === action.id).map((j, i) => <aside className="v2-dofirst" key={i}>Requires {expressionText(j.requirement, doc)}.</aside>)}
    <NeedsRow doc={doc} action={action} compact={compactNeeds} />
    {expanded && <p className="v2-tag" data-support="explanation">Fuller explanation</p>}
    <div data-support={expanded ? 'explanation' : undefined} className="v2-prose">
      {paragraphs.map((p, i) => <p key={i} className={expanded ? (i === 0 ? 'v2-lead' : 'v2-more') : undefined}>{p}</p>)}
    </div>
    {action.optional.map((block, i) => <div className="v2-optional" data-support="disclosure" key={`${viewId}:${block.id}`}>
      <details open={config.disclosure === 'expanded'}>
        <summary onClick={e => { if (!readOnly) event({ type: (e.currentTarget.parentElement as HTMLDetailsElement).open ? 'detail_close' : 'detail_open', action_id: action.id, value: block.id }); }}>
          Optional explanation{action.optional.length > 1 ? ` (${i + 1} of ${action.optional.length})` : ''}</summary>
        <p>{block.text}</p></details></div>)}
    {action.unreviewed_supplement.map((text, i) => <aside className="v2-sourcenote" key={i}><strong>Source note</strong><p>{text}</p></aside>)}
  </article>;
}
