import type { Dimension, GuidanceResponse, Configuration } from '../types';
import { DIMENSIONS, DIMENSION_TEXT, allowedValues, reasonText } from '../model';

/** Changing a dimension asks the backend for a child view; it is recorded as the person's own adjustment. */
export function SupportControls({ response, busy, onChange }: { response: GuidanceResponse; busy: boolean; onChange: (c: Configuration) => void }) {
  const config = response.document.configuration;
  return <div className="cz-support">
    <p className="cz-fine">Only combinations the backend can support for this procedure are offered. A change is recorded as your adjustment and is not the originally selected presentation.</p>
    {DIMENSIONS.map(dim => {
      const text = DIMENSION_TEXT[dim], options = allowedValues(response.availability, config, dim);
      const blocked = options.filter(o => !o.feasible && o.value !== config[dim]);
      return <div className="cz-srow" key={dim}>
        <div><b>{text.title}</b><small>{text.hint}</small></div>
        <div className="cz-seg" role="group" aria-label={text.title}>
          {options.map(o => <button type="button" key={o.value} aria-pressed={config[dim] === o.value} disabled={busy || !o.feasible}
            onClick={() => config[dim] !== o.value && onChange({ ...config, [dim as Dimension]: o.value } as Configuration)}>{text.values[o.value] ?? o.value}</button>)}
        </div>
        {blocked.length > 0 && <small className="cz-fine">Not offered here: {blocked.map(b => `${text.values[b.value] ?? b.value}${b.reason ? ` (${reasonText(b.reason)})` : ''}`).join('; ')}.</small>}
      </div>;
    })}
  </div>;
}

function statusText(r: GuidanceResponse): string {
  const p = r.preparation;
  if (p.content_state === 'source_fallback') return 'This guidance uses the wording of a bounded official-source snapshot. No reviewed explanation has been published for it, so richer explanation, disclosure, recap and phases are not offered.';
  if (p.content_state === 'demo_accepted') return 'Wording for this service was written with AI assistance from the official pages listed under Source passages and checked only by automatic source-grounding checks. The project owner accepted it for this local research demonstration. No expert, agency or government body has reviewed it, and it is not official guidance.';
  if (p.content_state === 'provisional_demo') return 'Provisional demo wording, written with AI assistance and checked only by automatic source-grounding checks. No person or authority has reviewed it.';
  if (p.review_kind === 'internal_fictional_author') return 'Fictional example. Its wording was prepared and checked in an internal, AI-assisted author review. It has not been reviewed by a human expert or by any government body.';
  return `Published wording (${p.content_origin.replaceAll('_', ' ')}).`;
}

export function SourcesContent({ response, onSource }: { response: GuidanceResponse; onSource: (evidenceId: string) => void }) {
  const doc = response.document, review = response.preparation.source_review;
  const incomplete = Object.entries(doc.completeness).filter(([, v]) => v !== 'complete');
  return <div className="cz-sources">
    <h3 className="cz-subhead">What this guidance covers</h3>
    <p>{doc.source_limit}</p>
    <h3 className="cz-subhead">Wording status</h3>
    <p>{statusText(response)}</p>
    {review && <p className="cz-fine">Review record: {review.reviewer} ({review.reviewed_at.slice(0, 10)}). {review.scope_note}{review.independent_government_validation ? '' : ' No independent or government validation.'}</p>}
    {incomplete.length > 0 && <p className="cz-fine">Coverage is not complete for: {incomplete.map(([k, v]) => `${k.replaceAll('_', ' ')} (${v})`).join(', ')}. Aids that need it are not offered.</p>}
    {doc.actions.some(a => a.source_wording) && <><h3 className="cz-subhead">Source wording, step by step</h3>
      <ul className="cz-textlist">{doc.actions.filter(a => a.source_wording).map(a => <li key={a.id}><b>{a.heading}</b><br />{(a.source_wording ?? '').split(/\n\s*\n/).filter(p => p.trim() && p.trim() !== doc.source_limit.trim()).join(' ')}</li>)}</ul></>}
    {doc.sources.length > 0 && <><h3 className="cz-subhead">Source passages</h3><ul className="cz-textlist">{doc.sources.map(s => <li key={s.evidence_id}>
      {/^https?:\/\//.test(s.source_url) ? <a href={s.source_url} target="_blank" rel="noreferrer" onClick={() => onSource(s.evidence_id)}>Open source</a> : <span>Source reference</span>}
      {s.retrieved_at ? ` · retrieved ${s.retrieved_at.slice(0, 10)}` : ' · authored fictional evidence'}<br />{s.text}</li>)}</ul></>}
  </div>;
}
