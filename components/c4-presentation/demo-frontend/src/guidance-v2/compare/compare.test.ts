import { describe, expect, it } from 'vitest';
import fixture from '../fixture.json';
import type { Journey } from '../types';
import { ComparisonError, createStandardComparison } from './compareClient';
import type { Request } from './compareClient';

const original = (): Journey => ({ ...(structuredClone(fixture) as unknown as Journey), id: 'journey-original', routing: 'adaptive' });

function backend(opts: { restricted?: boolean; mutate?: (j: Journey) => void; policy?: () => { posterior_revision: number; posterior_fingerprint: string } } = {}) {
  const calls: { method: string; path: string; body?: unknown }[] = [];
  const request: Request = async <T,>(path: string, body?: unknown, _token?: string, method?: string) => {
    const m = method ?? (body === undefined ? 'GET' : 'POST');
    calls.push({ method: m, path, body });
    if (path === '/v2/policy') return (opts.policy?.() ?? { posterior_revision: 7, posterior_fingerprint: 'abc' }) as T;
    if (path === '/dev/v1/sessions') return { session_id: 'guest:new' } as T;
    if (path.endsWith('/settings') && m === 'GET') {
      const access = { allow_relationship_visuals: !(opts.restricted && path.includes('profile')), allow_collapsed_content: true, allow_guided_navigation: true };
      return { session: { settings: { accessibility: access } }, locks: {}, settings_revision: 3 } as T;
    }
    if (path.endsWith('/settings') && m === 'PATCH') return {} as T;
    if (path.startsWith('/v2/journeys/')) return { ...original(), id: 'journey-standard', routing: 'standard' as const } as T;
    if (path.endsWith('/guidance')) {
      const j = { ...original(), id: 'journey-standard', routing: 'standard' as const, token: 'tok' };
      opts.mutate?.(j);
      return j as T;
    }
    throw new Error(`unexpected ${m} ${path}`);
  };
  return { calls, request };
}
const memory = () => { const m = new Map<string, string>(); return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v) }; };

describe('standard comparison client', () => {
  it('creates a separate standard guest journey and only reads the original', async () => {
    const { calls, request } = backend();
    const result = await createStandardComparison(original(), 'profile:session', { request, storage: memory() });
    expect(result.journey.routing).toBe('standard');
    expect(result.policyBefore).toEqual(result.policyAfter);
    const touchesOriginal = calls.filter(c => c.path.includes('profile%3Asession') || c.path.includes('journey-original'));
    expect(touchesOriginal.every(c => c.method === 'GET')).toBe(true);
    expect(calls.some(c => c.method === 'PATCH')).toBe(false);
    expect(calls.find(c => c.path.endsWith('/guidance'))?.path).toContain('guest%3Anew');
    expect(Object.keys(calls.find(c => c.path.endsWith('/guidance'))!.body as object).sort()).toEqual(['capability_token', 'expected_revision', 'procedure_id', 'request_id']);
  });

  it('copies accessibility constraints only, never familiarity, confidence or preferences', async () => {
    const { calls, request } = backend({ restricted: true });
    await createStandardComparison(original(), 'profile:session', { request, storage: memory() });
    const patch = calls.find(c => c.method === 'PATCH')!;
    expect(patch.path).toContain('guest%3Anew');
    expect(Object.keys(patch.body as object).sort()).toEqual(['context', 'expected_revision', 'request_id']);
    expect(Object.keys((patch.body as { context: object }).context)).toEqual(['accessibility']);
  });

  it('refuses a comparison when the content version differs', async () => {
    const { request } = backend({ mutate: j => { j.document.content_fingerprint = 'different'; } });
    await expect(createStandardComparison(original(), 'profile:session', { request, storage: memory() })).rejects.toMatchObject({ kind: 'content_changed' });
  });

  it('refuses a journey that is not standard routing', async () => {
    const { request } = backend({ mutate: j => { j.routing = 'adaptive'; } });
    await expect(createStandardComparison(original(), 'profile:session', { request, storage: memory() })).rejects.toBeInstanceOf(ComparisonError);
  });

  it('reports a changed learning state instead of hiding it', async () => {
    let n = 0;
    const { request } = backend({ policy: () => ({ posterior_revision: 7 + n++, posterior_fingerprint: 'abc' }) });
    await expect(createStandardComparison(original(), 'profile:session', { request, storage: memory() })).rejects.toMatchObject({ kind: 'policy_changed' });
  });

  it('reuses the earlier comparison journey instead of creating another', async () => {
    const storage = memory(), first = backend();
    await createStandardComparison(original(), 'profile:session', { request: first.request, storage });
    const reuse = backend();
    const result = await createStandardComparison(original(), 'profile:session', { request: reuse.request, storage });
    expect(result.reused).toBe(true);
    expect(reuse.calls.some(c => c.path === '/dev/v1/sessions')).toBe(false);
  });
});
