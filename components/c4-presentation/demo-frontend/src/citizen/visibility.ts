import type { ProcedureSummary } from '../api/types';

/**
 * Which registered procedures the citizen demo LISTS. Everything stays registered, reachable by id, and available to tests and experiments;
 * this only controls the sidebar and the profile familiarity choices.
 */
export const LISTED_FICTIONAL = ['synthetic-parallel-v1'];

export const isEarlier = (p: Pick<ProcedureSummary, 'procedure_id'>) => /-v3$/.test(p.procedure_id);

export function listed(procedures: ProcedureSummary[]): ProcedureSummary[] {
  return procedures.filter(p => !p.synthetic || LISTED_FICTIONAL.includes(p.procedure_id));
}
