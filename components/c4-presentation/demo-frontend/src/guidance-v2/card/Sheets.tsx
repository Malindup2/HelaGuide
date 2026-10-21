import { useEffect, useRef, useState } from 'react';
import type { Configuration, Document, EventInput } from '../types';
import { DIMENSIONS, SUPPORT_TEXT, displayTitle, factLabel, groupFacts, sourceFor } from '../presentation';
import type { FactEntry } from '../presentation';

/** Consolidated requirements. Route-specific items stay under their own condition; nothing is totalled. */
export function PreparationSummary({ doc, checklist = false }: { doc: Document; checklist?: boolean }) {
  const [done, setDone] = useState<string[]>([]);
  const toggle = (key: string) => setDone(old => old.includes(key) ? old.filter(x => x !== key) : [...old, key]);
  const groups = groupFacts(doc);
  const item = (entry: FactEntry, scope: string, key: string, service?: boolean) => {
    const f = entry.fact, label = factLabel(f, doc), source = sourceFor(doc, f.fact_id);
    return <li key={key}>{checklist
      ? <label className="gc-check"><input type="checkbox" checked={done.includes(key)} onChange={() => toggle(key)} /><span>{label}</span></label>
      : label}
      <small className="gc-kind">{f.kind === 'fee' ? 'Charge' : 'Document'}</small>
      <small>{service ? (f.kind === 'fee' ? 'Service-level charge; no action-level fee inferred.' : 'Service-level fact; action scope not supplied') : scope}</small>
      {entry.routes.length > 0 && entry.always.length > 0 && entry.routes.map(a => <small className="gc-route-line" key={a.id}>Route-dependent: {a.conditions.length ? `if ${a.conditions.join(' AND ')}, ` : ''}{displayTitle(a)}</small>)}
      {source && <a className="gc-fine" href={source.url} target="_blank" rel="noreferrer">Source</a>}</li>;
  };
  return <div className="gc-summary" id="gc-prep" data-support="summary">
    {checklist && <p className="gc-fine">Optional tick-list for your own reference. Ticking does not confirm that anything is prepared or done, and nothing is sent or saved.</p>}
    {groups.always.length > 0 && <section><h3>Needed in every case</h3><ul>{groups.always.map(e => item(e, e.always.map(a => displayTitle(a)).join('; '), `always:${e.fact.fact_id}`))}</ul></section>}
    {groups.conditional.map(g => <section key={g.key}><h3>Only if: {g.key}</h3><ul>{g.entries.map(e => item(e, e.routes.map(a => displayTitle(a)).join('; '), `${g.key}:${e.fact.fact_id}`))}</ul></section>)}
    {groups.service.length > 0 && <section><h3>Not tied to a specific action</h3><ul>{groups.service.map(f => item({ fact: f, always: [], routes: [] }, '', `service:${f.fact_id}`, true))}</ul></section>}
    <p className="gc-fine">Charges are not added into a total. Read each action for timing, exclusions and applicable conditions.</p>
    {doc.actions.some(a => a.actor) && <p className="gc-fine">{doc.actions.filter(a => a.actor).map(a => `${displayTitle(a)}: ${a.actor}`).join(' · ')}</p>}
  </div>;
}

/** Manual support controls. Same gating as before: procedure capabilities plus the feasible configurations. */
export function SupportContent({ doc, config, viewId, allowed, onChange, onUndo, event }: {
  doc: Document; config: Configuration; viewId: string; allowed: (k: keyof Configuration, v: string) => boolean;
  onChange: (k: keyof Configuration, v: string) => void; onUndo?: () => void; event: (e: EventInput) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const observer = new IntersectionObserver(entries => {
      for (const entry of entries) if (entry.isIntersecting) {
        const dimension = (entry.target as HTMLElement).dataset.dimension;
        if (dimension) event({ type: 'opportunity_visible', opportunity_id: `${viewId}:${dimension}` });
        observer.unobserve(entry.target);
      }
    }, { threshold: 0.5 });
    ref.current?.querySelectorAll('[data-dimension]').forEach(el => observer.observe(el));
    return () => observer.disconnect();
  }, [viewId, event]);
  const rows = DIMENSIONS.filter(d => ['navigation', 'explanation'].includes(d) || doc.capabilities[d].applicable);
  return <div ref={ref} className="gc-support">
    <p className="gc-fine">Changing support affects only this visit and is recorded as your adjustment.</p>
    {rows.map(d => {
      const text = SUPPORT_TEXT[d], states = Object.keys(text.states), blocked = states.filter(s => !doc.capabilities[d].states.includes(s));
      return <div className="gc-srow" key={d} data-dimension={d}>
        <div><b>{text.title}</b><small>{text.states[config[d]].benefit}</small></div>
        <div className="gc-seg" role="group" aria-label={text.title}>
          {states.map(s => <button type="button" key={s} aria-pressed={config[d] === s} disabled={!allowed(d, s)} onClick={() => onChange(d, s)}>{text.states[s].label}</button>)}
        </div>
        {blocked.length > 0 && <small className="gc-fine gc-srow-note">Not offered for this guidance: {blocked.map(s => text.states[s].label).join(', ')}. {doc.capabilities[d].reason}.</small>}
      </div>;
    })}
    {onUndo && <button type="button" className="gc-chip" onClick={onUndo}>Undo latest adjustment</button>}
  </div>;
}

export function SourcesContent({ doc, event }: { doc: Document; event: (e: EventInput) => void }) {
  useEffect(() => { event({ type: 'source_open' }); }, [event]);
  const factSources = doc.facts.map(f => ({ f, p: doc.provenance?.find(p => p.fact_id === f.fact_id) })).filter(x => x.p);
  return <div className="gc-sources">
    <p>{doc.scope}</p>
    {Object.values(doc.completeness).some(v => v !== 'complete') && <p>Some procedure coverage is incomplete. Missing relationships do not establish independence. This response covers the supplied scope.</p>}
    <p>Actions are listed for browsing. Relationships, where shown, say what must come first.</p>
    {factSources.length > 0 && <><h3>Where documents and charges come from</h3><ul>{factSources.map(({ f, p }) => <li key={f.fact_id}>{factLabel(f, doc)} · <a href={p!.source_url} target="_blank" rel="noreferrer">Source</a>{p!.retrieved_at ? ` · retrieved ${p!.retrieved_at}` : ''}</li>)}</ul></>}
    {doc.sources.map(s => <p key={s.evidence_id}><a href={s.source_url} target="_blank" rel="noreferrer">Source passage</a>{s.retrieved_at ? ` · retrieved ${s.retrieved_at}` : ' · authored fictional evidence'}<br />{s.text}</p>)}
  </div>;
}
