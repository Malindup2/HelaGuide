import type { Document, Expression, Journey } from './types';
export function expressionText(expression: Expression, doc: Document): string {
  if (expression.kind === 'action') return doc.actions.find(a => a.id === expression.ref)?.title ?? 'Unresolved action';
  if (expression.kind === 'selected_option_of') {
    const branch = doc.branches.find(b => b.group_id === expression.ref);
    return `the applicable ${branch?.selection === 'XOR' ? 'one alternative' : 'alternative(s)'} from the route group`;
  }
  return expression.children.map(c => expressionText(c, doc)).join(expression.kind === 'all_of' ? ' AND ' : ' OR ');
}
export function previousActions(journey: Journey, current: string) {
  const end = journey.seen.indexOf(current);
  const prior = end < 0 ? journey.seen : journey.seen.slice(0, end);
  return prior.map(id => journey.document.actions.find(a => a.id === id)!).filter(a => a &&
    (!a.branch || !journey.focused_routes?.[a.branch] || journey.focused_routes[a.branch] === a.option));
}
export function relationshipLines(doc: Document): string[] {
  const title = (id: string) => doc.actions.find(a => a.id === id)?.title ?? id;
  return [...doc.edges.map(e => `${title(e.source_id)} must precede ${title(e.target_id)}.`),
    ...doc.joins.map(j => `${title(j.target)} requires ${expressionText(j.requirement, doc)}.`),
    ...doc.parallel.map(p => `${p.action_ids.map(title).join(' and ')} may proceed in parallel as explicitly supplied.`),
    ...doc.parallel_areas.map(p => `${p.map(e => expressionText(e, doc)).join(' and ')} are explicitly parallel work areas.`),
    ...doc.branches.map(b => `${b.selection}: ${b.options.map(o => o.action_ids.map(title).join(' and ')).join(' / ')}. Conditions determine applicability; browsing does not determine eligibility.`)];
}
