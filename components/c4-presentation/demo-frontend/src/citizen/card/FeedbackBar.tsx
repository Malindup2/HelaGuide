import { useState } from 'react';
import type { RatingReason } from '../types';
import { ThumbDownIcon, ThumbUpIcon } from '../ui';

const REASONS: { value: RatingReason; label: string }[] = [
  { value: 'too_much_explanation', label: 'Too much explanation' },
  { value: 'not_enough_explanation', label: 'Not enough explanation' },
  { value: 'navigation_difficult', label: 'Navigation was difficult' },
  { value: 'diagram_confusing', label: 'The diagram was confusing' },
  { value: 'requirements_hard_to_find', label: 'Hard to find the requirements' },
  { value: 'other', label: 'Something else' },
];

/**
 * Fit feedback: thumbs-up is Fits (reward 1) and thumbs-down is Does not fit (reward 0). Reasons are diagnostic only.
 * Shown only when the backend offers it; a research preview is labelled as a diagnostic that trains nothing.
 */
export default function FeedbackBar({ eligible, rate, busy }: { eligible: boolean; rate: (r: 'fits' | 'does_not_fit', reasons: RatingReason[]) => Promise<unknown>; busy: boolean }) {
  const [stage, setStage] = useState<'ask' | 'reasons' | 'done'>('ask'), [picked, setPicked] = useState<RatingReason[]>([]), [sending, setSending] = useState(false);
  const send = async (rating: 'fits' | 'does_not_fit', reasons: RatingReason[]) => {
    setSending(true);
    try { if (await rate(rating, reasons)) setStage('done'); } finally { setSending(false); }
  };
  return <section className="cz-feedback" aria-labelledby="cz-fb-q">
    <p id="cz-fb-q"><b>Did this way of presenting the guidance suit you?</b></p>
    {!eligible && <p className="cz-fine">Research preview diagnostic. Recorded for evaluation only; it does not train or change any selection.</p>}
    {stage === 'ask' && <div className="cz-fbrow">
      <button type="button" className="cz-chip" disabled={busy || sending} onClick={() => void send('fits', [])}><ThumbUpIcon />Fits</button>
      <button type="button" className="cz-chip" disabled={busy || sending} onClick={() => setStage('reasons')}><ThumbDownIcon />Does not fit</button></div>}
    {stage === 'reasons' && <div>
      <fieldset className="cz-reasons"><legend className="cz-fine">Optional: what was the main difficulty?</legend>
        {REASONS.map(r => <label key={r.value}><input type="checkbox" checked={picked.includes(r.value)} onChange={() => setPicked(p => p.includes(r.value) ? p.filter(x => x !== r.value) : [...p, r.value])} /><span>{r.label}</span></label>)}</fieldset>
      <div className="cz-fbrow"><button type="button" className="cz-btn" disabled={sending} onClick={() => void send('does_not_fit', picked)}>Send</button>
        <button type="button" className="cz-link" onClick={() => setStage('ask')}>Back</button></div></div>}
    {stage === 'done' && <p role="status">Thank you. Your answer was recorded.</p>}
  </section>;
}
