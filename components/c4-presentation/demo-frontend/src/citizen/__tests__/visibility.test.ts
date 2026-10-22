import { describe, expect, it } from 'vitest';
import type { ProcedureSummary } from '../../api/types';
import { isEarlier, listed } from '../visibility';

const p = (procedure_id: string, synthetic: boolean) => ({ procedure_id, synthetic }) as ProcedureSummary;
const all = [p('synthetic-linear-v1', true), p('synthetic-conditional-v1', true), p('synthetic-parallel-v1', true), p('synthetic-practice-v2', true),
  p('official-birth_copy-v3', false), p('official-nic_amendment-v3', false), p('official-company_pack-v3', false),
  p('official-birth_copy-v4', false), p('official-nic_amendment-v4', false), p('official-tin_registration-v1', false)];

describe('procedure sidebar visibility', () => {
  it('lists every official procedure and only the parallel fictional example, hiding nothing from the registry', () => {
    const shown = listed(all).map(x => x.procedure_id);
    expect(shown).toEqual(['synthetic-parallel-v1', 'official-birth_copy-v3', 'official-nic_amendment-v3', 'official-company_pack-v3', 'official-birth_copy-v4', 'official-nic_amendment-v4', 'official-tin_registration-v1']);
    expect(all.length).toBe(10);                                                                  // the input list (the registry) is not modified
  });

  it('keeps exactly the three earlier versions apart from the current official services', () => {
    const real = listed(all).filter(x => !x.synthetic);
    expect(real.filter(isEarlier).map(x => x.procedure_id)).toEqual(['official-birth_copy-v3', 'official-nic_amendment-v3', 'official-company_pack-v3']);
    expect(real.filter(x => !isEarlier(x)).map(x => x.procedure_id)).toEqual(['official-birth_copy-v4', 'official-nic_amendment-v4', 'official-tin_registration-v1']);
  });
});
