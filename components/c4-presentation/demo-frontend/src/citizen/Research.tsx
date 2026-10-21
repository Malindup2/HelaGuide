import { useEffect, useState } from 'react';
import { GuidanceError, guidanceApi, newId, newToken } from './api';
import type { Availability, Configuration, Dimension, GuidanceResponse, InspectorRecord } from './types';
import { DIMENSIONS, DIMENSION_TEXT, feasibleFor, originOf, reasonText } from './model';
import GuidanceCard from './card/GuidanceCard';
import { Sheet } from './ui';

const STANDARD: Configuration = { navigation: 'overview', explanation: 'concise', disclosure: 'off', relationships: 'none', recap: 'off', segmentation: 'off' };

/** Research-only chooser built from the backend's own feasibility list. A preview is labelled as such everywhere. */
export function PreviewChooser({ availability, busy, onStart }: { availability: Availability | null; busy: boolean; onStart: (c: Configuration) => void }) {
  const [config, setConfig] = useState<Configuration>(STANDARD);
  if (!availability) return <p className="cz-fine">Request guidance once to load the feasible combinations for this procedure.</p>;
  const exists = availability.candidates.some(c => c.feasible && DIMENSIONS.every(d => c.configuration[d] === config[d]));
  const values = (dim: Dimension) => [...new Set(availability.candidates.map(c => c.configuration[dim] as string))];
  return <div className="cz-preview-chooser">
    <p className="cz-fine">{availability.feasible_count} of {availability.nominal_count} combinations are feasible for this procedure and these settings. A preview shows one of them; it is not a learned or personalised selection.</p>
    <div className="cz-grid">{DIMENSIONS.map(dim => <label key={dim}><span>{DIMENSION_TEXT[dim].title}</span>
      <select value={config[dim]} onChange={e => setConfig({ ...config, [dim]: e.target.value } as Configuration)}>
        {values(dim).map(v => <option key={v} value={v} disabled={!feasibleFor(availability, config, dim, v)}>{DIMENSION_TEXT[dim].values[v] ?? v}</option>)}
      </select></label>)}</div>
    <button type="button" className="cz-btn" disabled={busy || !exists} onClick={() => onStart(config)}>Open research preview</button>
    {!exists && <p className="cz-fine">That exact combination is not feasible. Choose different values.</p>}
  </div>;
}

type Stage = { name: 'consent' } | { name: 'working' } | { name: 'ready'; standard: GuidanceResponse; preview: GuidanceResponse } | { name: 'error'; message: string };

/** Standard versus research preview, from two separate journeys created through the documented endpoints. Nothing here trains. */
export function CompareSheet({ sessionId, procedureId, previewConfig, onClose }: { sessionId: string; procedureId: string; previewConfig: Configuration | null; onClose: () => void }) {
  const [stage, setStage] = useState<Stage>({ name: 'consent' }), [tab, setTab] = useState<'standard' | 'preview'>('standard');
  const run = async () => {
    setStage({ name: 'working' });
    try {
      const base = (token = newToken()) => ({ request_id: newId(), session_id: sessionId, procedure_id: procedureId, capability_token: token });
      const standard = await guidanceApi.start({ ...base(), mode: 'standard' });
      const preview = await guidanceApi.preview({ ...base(), mode: 'research_preview', configuration: previewConfig ?? { ...STANDARD, navigation: 'guided' } });
      setStage({ name: 'ready', standard, preview });
    } catch (e) { setStage({ name: 'error', message: e instanceof GuidanceError ? `${e.message}${e.reasons.length ? ' ' + e.reasons.map(reasonText).join('; ') : ''}` : 'The comparison could not be created.' }); }
  };
  return <Sheet title="Standard guidance and research preview" onClose={onClose} variant="modal">
    {stage.name === 'consent' && <div className="cz-consent">
      <p>This creates two separate guidance records for the same procedure: the fixed standard presentation and a research preview of {previewConfig ? 'your chosen combination' : 'a guided, concise combination'}.</p>
      <p>A preview is an explicit researcher choice. It is <b>not</b> a learned or personalised selection, and nothing in this comparison trains or changes any model.</p>
      <div className="cz-fbrow"><button type="button" className="cz-btn" onClick={() => void run()}>Create comparison</button><button type="button" className="cz-btn cz-btn-quiet" onClick={onClose}>Cancel</button></div></div>}
    {stage.name === 'working' && <p role="status">Preparing both views…</p>}
    {stage.name === 'error' && <p role="alert">{stage.message}</p>}
    {stage.name === 'ready' && <CompareBody standard={stage.standard} preview={stage.preview} tab={tab} setTab={setTab} />}
  </Sheet>;
}

function CompareBody({ standard, preview, tab, setTab }: { standard: GuidanceResponse; preview: GuidanceResponse; tab: 'standard' | 'preview'; setTab: (t: 'standard' | 'preview') => void }) {
  const a = standard.document.configuration, b = preview.document.configuration, changed = DIMENSIONS.filter(d => a[d] !== b[d]);
  return <div>
    {changed.length === 0 ? <p className="cz-same">The research preview uses the same combination as the standard presentation.</p> : <p>{changed.length} of 6 dimensions differ.</p>}
    <table className="cz-matrix"><thead><tr><th scope="col">Dimension</th><th scope="col">Standard</th><th scope="col">Research preview</th></tr></thead>
      <tbody>{DIMENSIONS.map(d => <tr key={d} className={a[d] !== b[d] ? 'differs' : undefined}><th scope="row">{DIMENSION_TEXT[d].title}</th>
        <td>{DIMENSION_TEXT[d].values[a[d]]}</td><td>{a[d] === b[d] ? <span className="cz-fine">Same</span> : DIMENSION_TEXT[d].values[b[d]]}</td></tr>)}</tbody></table>
    <p className="cz-fine">Both views come from the same procedure facts. Browsing here is not recorded and cannot train anything.</p>
    <div className="cz-tabs" role="group" aria-label="Choose view"><button type="button" className="cz-chip" aria-pressed={tab === 'standard'} onClick={() => setTab('standard')}>Standard</button>
      <button type="button" className="cz-chip" aria-pressed={tab === 'preview'} onClick={() => setTab('preview')}>Research preview</button></div>
    <div className="cz-panes" data-tab={tab}>
      <section aria-label="Standard guidance" className="cz-pane cz-pane-standard"><h3>{originOf(standard).label}</h3><div className="cz-pane-scroll"><GuidanceCard response={standard} readOnly /></div></section>
      <section aria-label="Research preview" className="cz-pane cz-pane-preview"><h3>{originOf(preview).label} · not a learned selection</h3><div className="cz-pane-scroll"><GuidanceCard response={preview} readOnly /></div></section>
    </div>
  </div>;
}

const MEASURES = ['step_count', 'information_volume', 'branch_count', 'condition_count', 'dependency_count', 'dependency_depth', 'parallel_group_count'];
const tail = (id: string) => id.slice(-6);

/** Only genuine backend data: a record of the completed request, and, separately, recorded client events. */
export function InspectorSheet({ journeyId, token, onClose }: { journeyId: string; token: string; onClose: () => void }) {
  const [record, setRecord] = useState<InspectorRecord | null>(null), [error, setError] = useState('');
  useEffect(() => { let live = true; guidanceApi.inspector(journeyId, token).then(r => { if (live) setRecord(r); }).catch(e => { if (live) setError(e instanceof GuidanceError ? e.message : 'The record could not be read.'); }); return () => { live = false; }; }, [journeyId, token]);
  return <Sheet title="Research inspector" onClose={onClose} variant="panel">
    {error && <p role="alert">{error}</p>}{!record && !error && <p role="status">Reading the stored record…</p>}
    {record && <Record record={record} />}
  </Sheet>;
}

function Record({ record }: { record: InspectorRecord }) {
  const ctx = record.effective_context, av = record.availability, selected = record.views.at(-1)?.selection;
  const infeasible = av.candidates.filter(c => !c.feasible), grouped = new Map<string, number>();
  for (const c of infeasible) for (const r of c.reasons) grouped.set(r, (grouped.get(r) ?? 0) + 1);
  const m = record.measurements as Record<string, { observed?: number; completeness?: string; normalized_observed?: number }>;
  return <div className="cz-inspector">
    <h3 className="cz-subhead">A. Record of the completed request</h3>
    <p className="cz-fine">Reconstructed from the stored request. It is not a live trace.</p>
    <dl className="cz-dl">
      <dt>Context</dt><dd>Familiarity {ctx.familiarity ?? 'not set'} · confidence {ctx.confidence ?? 'not set'} · {ctx.profile_id ? `profile …${tail(ctx.profile_id)}` : 'guest session'}</dd>
      <dt>Restrictions</dt><dd>{[ctx.constraints.no_guided && 'guided off', ctx.constraints.no_map && 'map off', ctx.constraints.no_disclosure && 'show/hide off', ...Object.entries(ctx.constraints.locks).map(([k, v]) => `lock ${k}=${v}`)].filter(Boolean).join(', ') || 'none'}</dd>
      <dt>Context origins</dt><dd>{Object.entries(ctx.sources).map(([k, v]) => `${k}: ${v.replaceAll('_', ' ')}`).join(' · ')}</dd>
    </dl>
    <table className="cz-matrix"><caption>Seven structural measurements</caption><thead><tr><th scope="col">Measure</th><th scope="col">Observed</th><th scope="col">Completeness</th></tr></thead>
      <tbody>{MEASURES.map(k => <tr key={k}><th scope="row">{k.replaceAll('_', ' ')}</th><td>{m[k]?.observed ?? '–'}{typeof m[k]?.normalized_observed === 'number' && <small> ({m[k]!.normalized_observed!.toFixed(2)})</small>}</td><td>{m[k]?.completeness ?? '–'}</td></tr>)}</tbody></table>
    <dl className="cz-dl">
      <dt>Feasibility</dt><dd>{av.feasible_count} of {av.nominal_count} configurations feasible{grouped.size > 0 && <ul>{[...grouped].map(([r, n]) => <li key={r}>{n} excluded: {reasonText(r)}</li>)}</ul>}</dd>
      <dt>Encoder and scoring</dt><dd>{record.scoring_status === 'not_run' ? 'Scoring was not run for this journey' : `Scoring status: ${record.scoring_status}`}. Features: {record.features === null ? 'none recorded' : 'recorded'}. Sampled scores: {record.sampled_scores === null ? 'none recorded' : 'recorded'}. Policy: {record.policy === null ? 'none' : 'recorded'}. Posterior updates for this journey: {record.posterior_updates}.</dd>
      <dt>Selection</dt><dd>{selected ? `${selected.label} (${selected.kind.replaceAll('_', ' ')})` : 'unknown'}</dd>
      <dt>Views</dt><dd><ul>{record.views.map(v => <li key={v.id}>…{tail(v.id)} · {v.parent_view_id ? `child of …${tail(v.parent_view_id)} (adjusted)` : 'original'} · {Object.values(v.selection.configuration).join(' / ')}</li>)}</ul></dd>
    </dl>
    <p className="cz-fine">{record.note}</p>
    {record.policy !== null && <details><summary>Recorded model decision, features and sampled scores</summary><pre style={{ overflowX: 'auto', maxHeight: 400 }}>{JSON.stringify({ policy: record.policy, features: record.features, sampled_scores: record.sampled_scores }, null, 2)}</pre></details>}
    <h3 className="cz-subhead">B. Recorded interaction events</h3>
    <p className="cz-fine">Client-reported interaction events. They never establish reading or completion.</p>
    {record.events.length === 0 ? <p>No events recorded yet.</p> : <table className="cz-matrix"><thead><tr><th scope="col">#</th><th scope="col">Type</th><th scope="col">Detail</th><th scope="col">Counts for recap</th></tr></thead>
      <tbody>{record.events.map((e, i) => <tr key={i}><td>{e.sequence ?? i + 1}</td><td>{e.type}{e.rating ? ` (${e.rating})` : ''}</td>
        <td>{String(e.payload?.action_id ?? (e.payload?.action_ids as string[] | undefined)?.length ?? '')}<small>{e.server_timestamp?.slice(11, 19)}</small></td><td>{e.qualifies_for_recap ? 'yes' : 'no'}</td></tr>)}</tbody></table>}
  </div>;
}

