import { useEffect, useState } from 'react';
import { parseSession } from '../api/client';
import type { ActiveIdentity, GuestSession, ProcedureSummary } from '../api/types';
import { GuidanceError, guidanceApi, newId } from './api';
import type { EffectiveContext } from './types';

/** The saved context that applies to this procedure, with origins, and an editor that uses the existing profile services. */
export default function ProfileContext({ active, procedure, onSession }: { active: ActiveIdentity; procedure: ProcedureSummary; onSession: (s: GuestSession) => void }) {
  const session = active.session, [ctx, setCtx] = useState<EffectiveContext | null>(null), [error, setError] = useState(''), [note, setNote] = useState(''), [saving, setSaving] = useState(false);
  const acc = session.settings.accessibility;
  const [form, setForm] = useState({ familiarity: '', confidence: '', guided: acc.allow_guided_navigation, maps: acc.allow_relationship_visuals, collapse: acc.allow_collapsed_content });
  useEffect(() => {
    let live = true;
    guidanceApi.context(session.session_id, procedure.procedure_id)
      .then(c => { if (live) { setCtx(c); setError(''); setForm({ familiarity: c.familiarity?.toString() ?? '', confidence: c.confidence?.toString() ?? '', guided: !c.constraints.no_guided, maps: !c.constraints.no_map, collapse: !c.constraints.no_disclosure }); } })
      .catch(e => { if (live) setError(e instanceof GuidanceError ? e.message : 'The saved context could not be read.'); });
    return () => { live = false; };
  }, [session.session_id, session.revision, procedure.procedure_id]);

  const save = async () => {
    setSaving(true); setError(''); setNote('');
    try {
      const result = await guidanceApi.patchProfileContext(session.session_id, {
        request_id: newId(), expected_identity_revision: session.revision,
        familiarity: [{ service_id: procedure.requested_service_id, score: form.familiarity ? Number(form.familiarity) : null, source: 'self_reported' }],
        confidence: form.confidence ? Number(form.confidence) : null,
        accessibility: { allow_guided_navigation: form.guided, allow_relationship_visuals: form.maps, allow_collapsed_content: form.collapse },
      });
      onSession(parseSession((result as { session: unknown }).session));
      setNote('Saved. Request guidance again to use these settings.');
    } catch (e) { setError(e instanceof GuidanceError ? e.message : 'The settings could not be saved.'); } finally { setSaving(false); }
  };
  const restrictions = ctx ? [ctx.constraints.no_guided && 'guided steps off', ctx.constraints.no_map && 'maps off', ctx.constraints.no_disclosure && 'show/hide explanation off'].filter(Boolean) : [];
  const rate = (n: number | null) => n === null ? 'not set' : `${n} of 5`;
  return <div className="cz-context">
    {ctx && <p className="cz-fine">For this procedure: familiarity {rate(ctx.familiarity)} · navigation confidence {rate(ctx.confidence)} · restrictions: {restrictions.join(', ') || 'none'}.</p>}
    {error && <p role="alert" className="cz-alert">{error}</p>}
    {active.kind === 'profile' && <details className="cz-edit"><summary>Edit saved settings</summary>
      <div className="cz-grid">
        <label><span>Familiarity with this service</span><select value={form.familiarity} onChange={e => setForm({ ...form, familiarity: e.target.value })}><option value="">Not set</option>{[1, 2, 3, 4, 5].map(n => <option key={n}>{n}</option>)}</select></label>
        <label><span>Confidence following instructions</span><select value={form.confidence} onChange={e => setForm({ ...form, confidence: e.target.value })}><option value="">Not set</option>{[1, 2, 3, 4, 5].map(n => <option key={n}>{n}</option>)}</select></label>
      </div>
      <fieldset className="cz-reasons"><legend className="cz-fine">Accessibility</legend>
        <label><input type="checkbox" checked={form.guided} onChange={e => setForm({ ...form, guided: e.target.checked })} /><span>Allow guided, one-step-at-a-time navigation</span></label>
        <label><input type="checkbox" checked={form.maps} onChange={e => setForm({ ...form, maps: e.target.checked })} /><span>Allow process maps</span></label>
        <label><input type="checkbox" checked={form.collapse} onChange={e => setForm({ ...form, collapse: e.target.checked })} /><span>Allow show/hide explanations</span></label></fieldset>
      <button type="button" className="cz-btn" disabled={saving} onClick={() => void save()}>{saving ? 'Saving…' : 'Save settings'}</button>
      {note && <p role="status" className="cz-fine">{note}</p>}
    </details>}
  </div>;
}
