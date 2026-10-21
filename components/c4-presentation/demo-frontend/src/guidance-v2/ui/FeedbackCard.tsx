import { useState } from 'react';
import type { EventInput, Journey, Receipt } from '../types';
import { feedbackNote } from '../presentation';
import type { Origin } from '../presentation';

const CHOICES = [
  { value: 'about_right', label: 'About right', hint: 'The amount of guidance suited me.' },
  { value: 'need_more', label: 'I needed more help', hint: 'I would have liked more support.' },
  { value: 'too_much', label: 'This was more than I needed', hint: 'I would have liked less.' },
] as const;

function citizenText(r: Receipt) {
  return r.eligible ? 'Thanks. This may help improve how support is chosen.' : 'Thanks. Your answer is saved with this view. It does not change which layout is selected.';
}
function researchText(r: Receipt, routing: Journey['routing']) {
  if (r.eligible) return 'Original selected view: counted for the policy update.';
  if (routing === 'standard') return 'Standard guidance: recorded, no policy update.';
  if (r.exclusion_reason === 'personalization_revoked') return 'Personalization disabled: recorded, no policy update.';
  if (r.exclusion_reason === 'constraints_changed') return 'Constraints changed: recorded, no policy update.';
  return 'Adjusted view: recorded, no policy update.';
}

export default function FeedbackCard({ origin, existing, canRate, routing, research, rate, event }: {
  origin: Origin; existing: Receipt | null; canRate: boolean; routing: Journey['routing']; research: boolean;
  rate: (rating: string) => Promise<Receipt>; event: (e: EventInput) => void;
}) {
  const [choice, setChoice] = useState<string>(''), [receipt, setReceipt] = useState<Receipt | null>(null), [sending, setSending] = useState(false), [reason, setReason] = useState('');
  const done = receipt ?? existing;
  const send = async () => {
    if (!choice) return;
    setSending(true);
    try { setReceipt(await rate(choice)); } catch { /* The parent shows the request error; the choice stays available for retry. */ } finally { setSending(false); }
  };
  return <section className="v2-feedback" aria-labelledby="v2-feedback-title"><h3 id="v2-feedback-title">Was this the right amount of guidance?</h3>
    {!done && <p className="v2-fine">{feedbackNote(origin)}</p>}
    {done ? <div role="status"><p><strong>{CHOICES.find(c => c.value === done.rating)?.label ?? done.rating}.</strong> {citizenText(done)}</p>
        {research && <p className="v2-fine">{researchText(done, routing)}</p>}</div>
      : <>
        <fieldset className="v2-choices"><legend className="sr-only">Amount of guidance</legend>
          {CHOICES.map(c => <label key={c.value} className={choice === c.value ? 'selected' : undefined}>
            <input type="radio" name="v2-amount" value={c.value} checked={choice === c.value} disabled={!canRate} onChange={() => setChoice(c.value)} />
            <span><strong>{c.label}</strong><small>{c.hint}</small></span></label>)}
        </fieldset>
        <div className="v2-feedback-actions"><button type="button" className="v2-primary" disabled={!canRate || !choice || sending} onClick={() => void send()}>{sending ? 'Sending…' : 'Send feedback'}</button>
          {!canRate && <span className="v2-fine">Available once the guidance has been on screen.</span>}</div>
      </>}
    {done && done.rating !== 'about_right' && <details><summary>Optional: what would have helped most?</summary>
      <div className="v2-choices-inline">
        <button type="button" aria-pressed={reason === 'explanation'} onClick={() => { setReason('explanation'); event({ type: 'reason', value: 'explanation' }); }}>The explanations</button>
        <button type="button" aria-pressed={reason === 'other_or_unsure'} onClick={() => { setReason('other_or_unsure'); event({ type: 'reason', value: 'other_or_unsure' }); }}>Something else or not sure</button>
      </div></details>}
  </section>;
}
