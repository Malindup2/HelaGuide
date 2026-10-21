import { describe, expect, it, vi } from 'vitest';
import { GuidanceApi, GuidanceError, newToken } from '../api';
import { GuidanceIdentityApi, toProcedureSummary } from '../identity';
import { procedureList } from './examples';

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

describe('GuidanceApi', () => {
  it('sends the capability token as a header and never in the URL or body', async () => {
    const fetcher = vi.fn().mockResolvedValue(json({ ok: true }));
    const api = new GuidanceApi('http://x', fetcher as unknown as typeof fetch);
    await api.journey('guidance:abc', 'T'.repeat(40));
    const [url, init] = fetcher.mock.calls[0];
    expect(url).toBe('http://x/workspace/guidance/journeys/guidance%3Aabc');
    expect((init.headers as Record<string, string>)['X-C4-Token']).toBe('T'.repeat(40));
    expect(String(url)).not.toContain('T'.repeat(40));
  });

  it('creates 32 to 128 character tokens', () => {
    expect(newToken().length).toBeGreaterThanOrEqual(32);
    expect(newToken().length).toBeLessThanOrEqual(128);
    expect(newToken()).not.toBe(newToken());
  });

  it('turns the policy-unavailable response into a typed error with its code', async () => {
    const api = new GuidanceApi('http://x', vi.fn().mockResolvedValue(json({ detail: { code: 'revised_policy_unavailable', message: 'not yet' } }, 503)) as unknown as typeof fetch);
    const error = await api.start({ request_id: 'r', session_id: 's', procedure_id: 'p', capability_token: newToken(), mode: 'personalized' }).catch(e => e);
    expect(error).toBeInstanceOf(GuidanceError);
    expect(error).toMatchObject({ status: 503, code: 'revised_policy_unavailable' });
  });

  it('keeps infeasible-configuration reasons and handles validation lists', async () => {
    const reasons = ['explanation:reviewed_detailed_missing'];
    const infeasible = new GuidanceApi('http://x', vi.fn().mockResolvedValue(json({ detail: { code: 'infeasible_configuration', message: 'unavailable', reasons } }, 422)) as unknown as typeof fetch);
    expect(await infeasible.status().catch(e => e)).toMatchObject({ code: 'infeasible_configuration', reasons });
    const listed = new GuidanceApi('http://x', vi.fn().mockResolvedValue(json({ detail: [{ msg: 'bad' }] }, 422)) as unknown as typeof fetch);
    expect(await listed.status().catch(e => e)).toMatchObject({ code: 'validation', status: 422 });
  });

  it('reports an unreachable service without a status code', async () => {
    const api = new GuidanceApi('http://x', vi.fn().mockRejectedValue(new TypeError('failed')) as unknown as typeof fetch);
    expect(await api.status().catch(e => e)).toMatchObject({ code: 'unreachable', status: 0 });
  });
});

describe('GuidanceIdentityApi', () => {
  it('uses the documented revised endpoints and adapts procedures for the profile questionnaire', async () => {
    const calls: string[] = [];
    const fetcher = vi.fn(async (url: string) => { calls.push(url); return json(url.endsWith('/procedures') ? procedureList() : []); });
    const api = new GuidanceIdentityApi('http://x', fetcher as unknown as typeof fetch);
    const list = await api.procedures();
    expect(calls).toEqual(['http://x/workspace/guidance/procedures']);
    expect(list).toHaveLength(7);
    expect(list.filter(p => !p.synthetic)).toHaveLength(3);
    expect(toProcedureSummary(procedureList()[3])).toMatchObject({ requested_service_id: 'svc:birth_copy', action_ids: [], features: {} });
    expect(await api.profiles()).toEqual([]);
    expect(calls[1]).toBe('http://x/workspace/guidance/profiles');
  });
});
