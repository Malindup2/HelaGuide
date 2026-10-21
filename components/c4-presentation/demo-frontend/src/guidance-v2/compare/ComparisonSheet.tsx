import { useEffect, useRef, useState } from 'react';
import type { Journey } from '../types';
import GuidanceMessage from '../GuidanceMessage';
import { SUPPORT_TEXT, diffConfigurations, presentationCounts, unavailableStates } from '../presentation';
import type { Dimension } from '../presentation';
import { ComparisonError, createStandardComparison } from './compareClient';
import type { Request, StandardComparison } from './compareClient';

type Stage = { name: 'consent' } | { name: 'working' } | { name: 'ready'; result: StandardComparison } | { name: 'error'; message: string };

/** Frozen, read-only projection: the originally selected view, never the user's later adjustments. */
const root = (j: Journey): Journey => ({ ...j, current_view: j.root_view, seen: [], focus: null, focused_routes: undefined });
const noop = () => undefined;
const never = () => Promise.reject(new Error('Comparison views are read-only.'));

export default function ComparisonSheet({ original, sessionId, research, request, storage, onClose }: {
  original: Journey; sessionId: string; research: boolean; request: Request; storage?: Pick<Storage, 'getItem' | 'setItem'>; onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [stage, setStage] = useState<Stage>({ name: 'consent' }), [highlight, setHighlight] = useState<Dimension | null>(null), [pane, setPane] = useState<'standard' | 'selected'>('standard');
  useEffect(() => {
    const d = dialog.current;
    if (!d) return;
    if (typeof d.showModal === 'function') { if (!d.open) d.showModal(); } else d.setAttribute('open', '');
  }, []);

  const start = async () => {
    setStage({ name: 'working' });
    try { setStage({ name: 'ready', result: await createStandardComparison(original, sessionId, { request, storage }) }); }
    catch (e) { setStage({ name: 'error', message: e instanceof ComparisonError ? e.message : 'The comparison could not be created. Your guidance was not changed.' }); }
  };

  return <dialog ref={dialog} className="v2-compare" aria-labelledby="v2-compare-title" onClose={onClose} onCancel={onClose}>
    <div className="v2-compare-head"><h2 id="v2-compare-title">Compare with standard guidance</h2><button type="button" onClick={onClose}>Close</button></div>
    {stage.name === 'consent' && <div className="v2-compare-consent">
      <p>This shows what <strong>standard guidance</strong> for the same procedure looks like next to the presentation <strong>selected for your saved profile</strong>.</p>
      <p>To do that, a separate demonstration guest journey is created. It does not change your profile, your original guidance, your ratings or the learning state.</p>
      <div className="v2-compare-actions"><button type="button" className="v2-primary" onClick={() => void start()}>Create comparison</button><button type="button" onClick={onClose}>Cancel</button></div></div>}
    {stage.name === 'working' && <p role="status">Preparing the standard view…</p>}
    {stage.name === 'error' && <div role="alert"><p>{stage.message}</p><button type="button" onClick={onClose}>Close</button></div>}
    {stage.name === 'ready' && <Ready original={original} result={stage.result} research={research} highlight={highlight} setHighlight={setHighlight} pane={pane} setPane={setPane} />}
  </dialog>;
}

function Ready({ original, result, research, highlight, setHighlight, pane, setPane }: {
  original: Journey; result: StandardComparison; research: boolean; highlight: Dimension | null; setHighlight: (d: Dimension | null) => void; pane: 'standard' | 'selected'; setPane: (p: 'standard' | 'selected') => void;
}) {
  const standard = root(result.journey), selected = root(original);
  const a = standard.views[standard.current_view].configuration, b = selected.views[selected.current_view].configuration;
  const diffs = diffConfigurations(a, b), changed = diffs.filter(d => !d.same);
  const ca = presentationCounts(standard.document, a), cb = presentationCounts(selected.document, b);
  const missing = unavailableStates(original.document);
  const label = (d: Dimension, s: string) => SUPPORT_TEXT[d].states[s].label;
  const adjusted = original.current_view !== original.root_view;
  return <div className="v2-compare-body">
    <section aria-labelledby="v2-diff-title"><h3 id="v2-diff-title">What differs</h3>
      {changed.length === 0
        ? <p className="v2-same">The presentation selected for this saved profile matches standard guidance for this procedure. Both views are shown below.</p>
        : <p>{changed.length} of 6 supports differ. Choose a row to highlight where it appears in both views.</p>}
      <table className="v2-diff"><thead><tr><th scope="col">Support</th><th scope="col">Standard</th><th scope="col">Selected for your saved profile</th></tr></thead>
        <tbody>{diffs.map(d => <tr key={d.dimension} className={d.same ? undefined : 'differs'}>
          <th scope="row"><button type="button" aria-pressed={highlight === d.dimension} onClick={() => setHighlight(highlight === d.dimension ? null : d.dimension)}>{SUPPORT_TEXT[d.dimension].title}</button></th>
          <td>{label(d.dimension, d.standard)}<small>{SUPPORT_TEXT[d.dimension].states[d.standard].benefit}</small></td>
          <td>{d.same ? <span className="v2-fine">Same</span> : <>{label(d.dimension, d.selected)}<small>{SUPPORT_TEXT[d.dimension].states[d.selected].benefit}</small></>}</td></tr>)}</tbody></table>
      <ul className="v2-counts">
        <li>Actions visible without navigating: <strong>{ca.actionsVisible}</strong> vs <strong>{cb.actionsVisible}</strong></li>
        {(ca.optionalTotal > 0) && <li>Optional notes open by default: <strong>{ca.optionalOpen}</strong> vs <strong>{cb.optionalOpen}</strong> of {ca.optionalTotal}</li>}
        <li>Relationship cues shown: <strong>{ca.relationshipCues}</strong> vs <strong>{cb.relationshipCues}</strong></li>
      </ul>
      {missing.length > 0 && <details><summary>Not offered for this procedure</summary><ul>{[...new Set(missing.map(m => `${SUPPORT_TEXT[m.dimension].title}: ${label(m.dimension, m.state)} (${m.reason})`))].map(t => <li key={t}>{t}</li>)}</ul></details>}
      <p className="v2-fine">Both views show the same procedure facts. Browsing inside the comparison is not recorded and cannot affect learning.{adjusted && ' You have since adjusted your own view; the right-hand view shows the originally selected presentation.'}</p>
      {research && <p className="v2-fine">Policy revision {result.policyBefore.posterior_revision} before and {result.policyAfter.posterior_revision} after; fingerprint {result.policyBefore.posterior_fingerprint === result.policyAfter.posterior_fingerprint ? 'unchanged' : 'CHANGED'}. {result.reused ? 'Reused the earlier standard comparison journey.' : 'Created a new standard guest journey.'}</p>}
    </section>
    <div className="v2-pane-switch" role="group" aria-label="Choose view"><button type="button" aria-pressed={pane === 'standard'} onClick={() => setPane('standard')}>Standard</button><button type="button" aria-pressed={pane === 'selected'} onClick={() => setPane('selected')}>Selected for your saved profile</button></div>
    <div className="v2-panes" data-pane={pane}>
      <section aria-label="Standard guidance" className="v2-pane v2-pane-standard"><h3>Standard guidance</h3><p className="v2-fine">Same procedure and accessibility settings, no personalization.</p>
        <GuidanceMessage journey={standard} event={noop} adjust={noop} rate={never} readOnly highlight={highlight} /></section>
      <section aria-label="Selected for your saved profile" className="v2-pane v2-pane-selected"><h3>Selected for your saved profile</h3><p className="v2-fine">The presentation the system selected when your guidance was created.</p>
        <GuidanceMessage journey={selected} event={noop} adjust={noop} rate={never} readOnly highlight={highlight} /></section>
    </div>
  </div>;
}

