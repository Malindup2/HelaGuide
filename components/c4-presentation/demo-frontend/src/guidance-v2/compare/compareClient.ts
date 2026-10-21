/**
 * Creates a separate standard guest journey for the same procedure, using only the existing API.
 * The original journey and its session are only read. Nothing here selects, adjusts or rates.
 */
import type { Journey } from '../types';

export type Request = <T>(path: string, body?: unknown, token?: string, method?: string) => Promise<T>;
export type PolicyStatus = { posterior_revision: number; posterior_fingerprint: string };
export type StandardComparison = { sessionId: string; journey: Journey; policyBefore: PolicyStatus; policyAfter: PolicyStatus; reused: boolean };
type Saved = { sessionId: string; id: string; token: string };
type Settings = { session: { settings: { accessibility: Record<string, boolean> } }; locks: Record<string, string>; settings_revision: number };

export class ComparisonError extends Error {
  constructor(message: string, readonly kind: 'content_changed' | 'not_standard' | 'policy_changed') { super(message); }
}

const cacheKey = (originalId: string) => `c4-compare:${originalId}`;
const enc = encodeURIComponent;

function readSaved(storage: Pick<Storage, 'getItem'> | undefined, originalId: string): Saved | null {
  try { return JSON.parse(storage?.getItem(cacheKey(originalId)) ?? 'null'); } catch { return null; }
}

/** Throws ComparisonError when the two journeys cannot honestly be compared. */
export function assertComparable(original: Journey, standard: Journey) {
  if (standard.routing !== 'standard') throw new ComparisonError('The comparison journey was not standard guidance, so it was not used.', 'not_standard');
  const a = original.document, b = standard.document;
  const same = a.id === b.id && a.graph_fingerprint === b.graph_fingerprint && a.content_fingerprint === b.content_fingerprint
    && (a.structure_fingerprint === undefined || b.structure_fingerprint === undefined || a.structure_fingerprint === b.structure_fingerprint);
  if (!same) throw new ComparisonError('The procedure content has changed since your guidance was created. Request fresh guidance, then compare again.', 'content_changed');
}

export async function createStandardComparison(original: Journey, originalSessionId: string, deps: {
  request: Request; storage?: Pick<Storage, 'getItem' | 'setItem'>; uuid?: () => string;
}): Promise<StandardComparison> {
  const { request, storage } = deps, uuid = deps.uuid ?? (() => crypto.randomUUID());
  const policyBefore = await request<PolicyStatus>('/v2/policy');

  const saved = readSaved(storage, original.id);
  if (saved) {
    try {
      const journey = await request<Journey>(`/v2/journeys/${enc(saved.id)}`, undefined, saved.token);
      assertComparable(original, journey);
      return { sessionId: saved.sessionId, journey, policyBefore, policyAfter: await request<PolicyStatus>('/v2/policy'), reused: true };
    } catch (e) { if (e instanceof ComparisonError) throw e; /* otherwise fall through and create a fresh comparison */ }
  }

  const guest = await request<{ session_id: string }>('/dev/v1/sessions', undefined, undefined, 'POST');
  const sid = guest.session_id;

  // Constraint parity only: accessibility and hard locks bind standard guidance too. Familiarity,
  // confidence and preferences are never copied, so the guest stays a plain standard guest.
  const source = await request<Settings>(`/workspace/sessions/${enc(originalSessionId)}/settings`);
  const access = source.session.settings.accessibility, locks = source.locks ?? {};
  if (Object.values(access).some(v => v === false) || Object.keys(locks).length > 0) {
    const target = await request<Settings>(`/workspace/sessions/${enc(sid)}/settings`);
    await request(`/workspace/sessions/${enc(sid)}/settings`, {
      request_id: uuid(), expected_revision: target.settings_revision, context: { accessibility: access },
      ...(Object.keys(locks).length > 0 ? { locks } : {}),
    }, undefined, 'PATCH');
  }

  const fresh = await request<Settings>(`/workspace/sessions/${enc(sid)}/settings`);
  const journey = await request<Journey>(`/workspace/sessions/${enc(sid)}/guidance`, {
    procedure_id: original.document.id, request_id: `compare-${uuid()}`, capability_token: uuid() + uuid(), expected_revision: fresh.settings_revision,
  });
  assertComparable(original, journey);
  const policyAfter = await request<PolicyStatus>('/v2/policy');
  if (policyAfter.posterior_revision !== policyBefore.posterior_revision || policyAfter.posterior_fingerprint !== policyBefore.posterior_fingerprint)
    throw new ComparisonError('The learning state changed while the comparison was created. Please report this.', 'policy_changed');
  try { storage?.setItem(cacheKey(original.id), JSON.stringify({ sessionId: sid, id: journey.id, token: journey.token! } satisfies Saved)); } catch { /* storage may be unavailable */ }
  return { sessionId: sid, journey, policyBefore, policyAfter, reused: false };
}
