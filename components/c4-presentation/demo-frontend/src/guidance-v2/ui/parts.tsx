import type { ReactNode, RefObject } from 'react';
import type { Action, Configuration, Document, EventInput } from '../types';
import { SUPPORT_TEXT, DIMENSIONS, ORIGIN_TEXT, activeSupports, actionFacts, agencies, factLabel, incomplete, statusChip } from '../presentation';
import type { Origin } from '../presentation';

export function DocIcon() {
  return <svg className="v2-icon" viewBox="0 0 16 16" aria-hidden="true"><path d="M4 1.5h5.5L13 5v9.5H4z M9.5 1.5V5H13" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" /></svg>;
}
export function FeeIcon() {
  return <svg className="v2-icon" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6.2" fill="none" stroke="currentColor" strokeWidth="1.3" /><path d="M8 4.5v7 M6.2 6.2c0-1.6 3.6-1.6 3.6 0S6.2 8.2 6.2 9.8c0 1.6 3.6 1.6 3.6 0" fill="none" stroke="currentColor" strokeWidth="1.1" /></svg>;
}

export function ServiceHeader({ doc }: { doc: Document }) {
  const names = agencies(doc);
  return <header className="v2-head">
    <p className="v2-chip-row"><span className="v2-chip v2-chip-status">{statusChip(doc)}</span>
      {incomplete(doc) && <span className="v2-chip v2-chip-warn">Covers the supplied actions only</span>}</p>
    <h2>{doc.title}</h2>
    {names.length > 0 && <p className="v2-agency">{names.length === 1 ? 'Service agency' : 'Service agencies'}: <strong>{names.join(' · ')}</strong></p>}
    <details className="v2-about"><summary>About this guidance</summary><p>{doc.scope}</p>
      {incomplete(doc) && <p>Some procedure coverage is incomplete. Missing relationships do not establish independence. This response covers the supplied scope.</p>}
      <p>Actions are listed for browsing. Relationships, where shown, say what must come first.</p></details>
  </header>;
}

export function SupportLine({ origin, config, onCompare, children }: { origin: Origin; config: Configuration; onCompare?: () => void; children?: ReactNode }) {
  const supports = activeSupports(config);
  return <div className="v2-support" data-origin={origin}>
    <div className="v2-support-top"><span className={`v2-origin v2-origin-${origin}`}>{ORIGIN_TEXT[origin].label}</span>
      {onCompare && <button type="button" className="v2-link" onClick={onCompare}>Compare with standard guidance</button>}</div>
    {supports.length > 0
      ? <ul className="v2-supports" aria-label="Support in this view">{supports.map(s => <li key={s.dimension}><strong>{s.label}</strong><span>{s.benefit}</span></li>)}</ul>
      : <p className="v2-fine">Plain layout. Every action and requirement is shown. Use “Adjust support” if you would like extra help.</p>}
    {children}
  </div>;
}

type Allowed = (key: keyof Configuration, value: string) => boolean;
export function SupportSheet({ doc, config, allowed, onChange, onUndo, controlsRef }: {
  doc: Document; config: Configuration; allowed: Allowed; onChange: (key: keyof Configuration, value: string) => void;
  onUndo?: () => void; controlsRef: RefObject<HTMLElement | null>;
}) {
  const rows = DIMENSIONS.filter(d => ['navigation', 'explanation'].includes(d) || doc.capabilities[d].applicable);
  return <details className="v2-adjustments"><summary>Adjust support for this visit</summary>
    <nav ref={controlsRef} className="v2-sheet" aria-label="Adjust support for this visit">
      {rows.map(d => {
        const text = SUPPORT_TEXT[d], states = Object.keys(text.states), blocked = states.filter(s => !doc.capabilities[d].states.includes(s));
        return <div className="v2-row" key={d} data-dimension={d}>
          <div className="v2-row-copy"><strong>{text.title}</strong><span>{text.question}</span></div>
          <div className="v2-seg" role="group" aria-label={text.title}>
            {states.map(s => <button type="button" key={s} aria-pressed={config[d] === s} disabled={!allowed(d, s)} onClick={() => onChange(d, s)} title={text.states[s].benefit}>{text.states[s].label}</button>)}
          </div>
          {blocked.length > 0 && <small className="v2-fine">Not offered for this guidance: {blocked.map(s => text.states[s].label).join(', ')}. {doc.capabilities[d].reason}.</small>}
        </div>;
      })}
      {onUndo && <button type="button" className="v2-undo" onClick={onUndo}>Undo latest adjustment</button>}
    </nav>
  </details>;
}

export function NeedsRow({ doc, action, compact }: { doc: Document; action: Action; compact: boolean }) {
  const facts = actionFacts(doc, action), docs = facts.filter(f => f.kind === 'document'), fees = facts.filter(f => f.kind === 'fee');
  if (facts.length === 0) return null;
  if (compact) return <p className="v2-needs-ref">You will need {docs.length > 0 && `${docs.length} document${docs.length === 1 ? '' : 's'}`}{docs.length > 0 && fees.length > 0 && ' and '}{fees.length > 0 && `${fees.length} charge${fees.length === 1 ? '' : 's'}`}. See <a href="#v2-prep">Before you start</a>.</p>;
  return <div className="v2-needs">
    {docs.length > 0 && <div><h4>Documents</h4><ul>{docs.map(f => <li key={f.fact_id}><DocIcon />{factLabel(f, doc)}</li>)}</ul></div>}
    {fees.length > 0 && <div><h4>Charges</h4><ul>{fees.map(f => <li key={f.fact_id}><FeeIcon />{factLabel(f, doc)}</li>)}</ul></div>}
  </div>;
}

export function SourcesPanel({ doc, event }: { doc: Document; event: (e: EventInput) => void }) {
  const factSources = doc.facts.map(f => ({ f, p: doc.provenance?.find(p => p.fact_id === f.fact_id) })).filter(x => x.p);
  return <details className="v2-sources" onToggle={e => { if (e.currentTarget.open) event({ type: 'source_open' }); }}><summary>Sources and scope</summary>
    <p>{doc.scope}</p>
    {factSources.length > 0 && <><h4>Where documents and charges come from</h4><ul>{factSources.map(({ f, p }) => <li key={f.fact_id}>{factLabel(f, doc)} · <a href={p!.source_url} target="_blank" rel="noreferrer">Source</a>{p!.retrieved_at ? ` · retrieved ${p!.retrieved_at}` : ''}</li>)}</ul></>}
    {doc.sources.map(s => <p key={s.evidence_id}><a href={s.source_url} target="_blank" rel="noreferrer">Source passage</a>{s.retrieved_at ? ` · retrieved ${s.retrieved_at}` : ' · authored fictional evidence'}<br />{s.text}</p>)}
  </details>;
}

/** Collapsed by default; opening it is the recorded recap_open interaction, exactly as before. */
export function RecapTrail({ previous, jump, onOpen }: { previous: Action[]; jump: (id: string) => void; onOpen: () => void }) {
  return <aside className="v2-recap" data-support="recap"><details onToggle={e => { if (e.currentTarget.open) onOpen(); }}>
    <summary>Earlier in this journey ({previous.length})</summary>
    <p className="v2-fine">Viewed guidance; completion has not been confirmed.</p>
    <ul>{previous.map(a => <li key={a.id}><span>{a.recap}</span> <button type="button" className="v2-link" onClick={() => jump(a.id)}>Revisit</button></li>)}</ul>
  </details></aside>;
}
