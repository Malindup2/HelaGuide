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
  const position=journey.document.actions.findIndex(a=>a.id===current);
  // Previously displayed preceding guidance remains available on revisits.
  // Browsing position is not a newly inferred execution dependency.
  return journey.document.actions.slice(0,Math.max(0,position)).filter(a=>journey.seen.includes(a.id) &&
    (!a.branch || journey.document.branches.find(b=>b.group_id===a.branch)?.selection!=='XOR' || !journey.focused_routes?.[a.branch] || journey.focused_routes[a.branch] === a.option));
}
export function relationshipLines(doc: Document): string[] {
  const title = (id: string) => doc.actions.find(a => a.id === id)?.title ?? id;
  return [...doc.edges.map(e => `${title(e.source_id)} must precede ${title(e.target_id)}.`),
    ...doc.joins.map(j => `${title(j.target)} requires ${expressionText(j.requirement, doc)}.`),
    ...doc.parallel.map(p => `${p.action_ids.map(title).join(' and ')} may proceed in parallel as explicitly supplied.`),
    ...doc.parallel_areas.map(p => `${p.map(e => expressionText(e, doc)).join(' and ')} are explicitly parallel work areas.`),
    ...doc.branches.map(b => `${b.selection==='AND'?'Joint requirements':b.selection==='XOR'?'One alternative route':'One or more applicable options'}: ${b.options.map(o => '('+o.action_ids.map(title).join(' and ')+')').join(b.selection==='AND'?' AND ':' OR ')}. Conditions determine applicability; browsing does not determine eligibility.`)];
}
