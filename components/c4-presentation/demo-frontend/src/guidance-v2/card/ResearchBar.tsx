import type { Journey } from '../types';
import { originOf } from '../presentation';

/** Discreet research view: what was selected and how it is attributed. Read-only except the opt-in comparison. */
export default function ResearchBar({ journey, onCompare }: { journey: Journey; onCompare?: () => void }) {
  const view = journey.views[journey.current_view], c = view.configuration;
  return <aside className="sh-research" aria-label="Research view">
    <p><b>Research view</b> · routing {journey.routing ?? 'unknown'} · {originOf(journey)} · {c.navigation}/{c.explanation}/{c.disclosure}/{c.relationships}/{c.recap}/{c.summary}</p>
    <p className="gc-fine">Original selected view {journey.root_view === journey.current_view ? 'is showing' : 'has been adjusted'}. Ratings count toward the policy only for the original, unadjusted, personalised view.</p>
    <p className="sh-research-actions"><a href="#c4-v2-inspector">Open Research Inspector</a>{onCompare && <button type="button" className="gc-chip" onClick={onCompare}>Compare with standard guidance</button>}</p>
  </aside>;
}
