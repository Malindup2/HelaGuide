import type { ReactNode } from 'react';
import type { Route, RouteOption } from '../types';

const TEXT = {
  XOR: { title: 'Which applies to you?', hint: 'Choosing a route only focuses the guidance. It does not check eligibility or show anything as done.' },
  OR: { title: 'Which of these apply?', hint: 'More than one may apply. Choosing only focuses the guidance; it does not check eligibility.' },
  AND: { title: 'All of these are needed', hint: 'These are joint requirements from the source.' },
} as const;

type Props = {
  route: Route; selected: string[]; onChoose: (optionIds: string[]) => void;
  /** Steps of an option (shown for the chosen option, or for every option when all are required). */
  steps?: (o: RouteOption) => ReactNode;
  /** Headings only, shown before a choice has been made. */
  preview?: (o: RouteOption) => ReactNode;
  compact?: boolean;
};

/** A branch group is a CHOICE, never consecutive steps. The other routes stay reachable after choosing. */
export default function RouteChoice({ route, selected, onChoose, steps, preview, compact = false }: Props) {
  const text = TEXT[route.selection], any = selected.length > 0, letter = (i: number) => String.fromCharCode(65 + i);
  const toggle = (id: string) => onChoose(route.selection === 'OR' ? (selected.includes(id) ? selected.filter(x => x !== id) : [...selected, id]) : [id]);
  return <section className="cz-route" aria-label={text.title} data-compact={compact}>
    <div className="cz-route-head"><h3>{text.title}</h3>
      {any && route.selection !== 'AND' && <button type="button" className="cz-link" onClick={() => onChoose([])}>Change route</button>}</div>
    {!any && route.selection !== 'AND' && <p className="cz-fine">{text.hint}</p>}
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
        {!compact && !any && route.selection !== 'AND' && preview?.(o)}
      </div>;
    })}
  </section>;
}
