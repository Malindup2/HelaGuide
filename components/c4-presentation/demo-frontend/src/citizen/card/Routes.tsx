import type { ReactNode } from 'react';
import type { Doc, Route, RouteOption, ScopedFact } from '../types';
import { Facts } from './StepParts';

const TEXT = {
  XOR: { title: 'Which applies to you?', hint: 'Pick the route that matches your situation. This only changes what you see here; it does not check eligibility.' },
  OR: { title: 'Which of these apply?', hint: 'More than one may apply. This only changes what you see here; it does not check eligibility.' },
  AND: { title: 'All of these are needed', hint: 'The source lists these together.' },
} as const;

type Props = {
  route: Route; selected: string[]; onChoose: (optionIds: string[]) => void;
  /** Steps of an option (shown for the chosen option, or for every option when all are required). */
  steps?: (o: RouteOption) => ReactNode;
  /** Headings only, shown before a choice has been made. */
  preview?: (o: RouteOption) => ReactNode;
  compact?: boolean;
  /** Facts attached to this route group (for example one fee that applies whichever route is taken). */
  facts?: ScopedFact[]; doc?: Doc;
};

/** A branch group is a CHOICE, never consecutive steps. The other routes stay reachable after choosing. */
export default function RouteChoice({ route, selected, onChoose, steps, preview, compact = false, facts = [], doc }: Props) {
  const text = TEXT[route.selection], any = selected.length > 0, letter = (i: number) => String.fromCharCode(65 + i);
  const toggle = (id: string) => onChoose(route.selection === 'OR' ? (selected.includes(id) ? selected.filter(x => x !== id) : [...selected, id]) : [id]);
  return <section className="cz-route" aria-label={text.title} data-compact={compact}>
    <div className="cz-route-head"><h3>{text.title}</h3>
      {any && route.selection !== 'AND' && <button type="button" className="cz-link" onClick={() => onChoose([])}>Change route</button>}</div>
    {!any && route.selection !== 'AND' && <p className="cz-fine">{text.hint}</p>}
    {doc && facts.length > 0 && <section className="cz-atstep" aria-label="Facts for this choice"><Facts facts={facts} doc={doc} byRole /><p className="cz-fine">Applies whichever route you take.</p></section>}
    {route.options.map((o, i) => {
      const chosen = selected.includes(o.option_id), collapsed = route.selection !== 'AND' && any && !chosen && route.selection === 'XOR';
      return <div className="cz-opt" key={o.option_id} data-chosen={chosen}>
        <div className="cz-opt-head">
          <span className="cz-mark cz-mark-route" aria-hidden="true">{letter(i)}</span>
          <p className="cz-opt-cond">{collapsed && <span className="cz-fine">Other route: </span>}{o.label}</p>
          {route.selection !== 'AND' && <button type="button" className="cz-chip" aria-pressed={chosen} onClick={() => toggle(o.option_id)}>
            {chosen ? 'Showing' : collapsed ? 'Switch' : route.selection === 'OR' ? 'Apply' : 'Show steps'}</button>}
        </div>
        {!compact && (chosen || route.selection === 'AND') && steps?.(o)}
        {!any && route.selection !== 'AND' && preview?.(o)}
      </div>;
    })}
  </section>;
}
