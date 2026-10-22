import { useCallback, useEffect, useRef, useState } from 'react';
import { API_BASE } from '../api/client';
import { GuidanceError, guidanceApi, newId, newToken } from './api';
import type { GuidanceApi } from './api';
import type { ApiStatus, Configuration, EventBody, GuidanceResponse, RatingReason, Receipt } from './types';

export type StartMode = { kind: 'standard' } | { kind: 'personalized' } | { kind: 'preview'; configuration: Configuration; provisional?: boolean };
type Capability = { id: string; token: string };

const storeKey = (sessionId: string, procedureId: string) => `c4-guidance:${API_BASE}:${sessionId}:${procedureId}`;
function readCap(key: string): Capability | null { try { return JSON.parse(sessionStorage.getItem(key) ?? 'null'); } catch { return null; } }
function writeCap(key: string, cap: Capability | null) {
  try { if (cap) sessionStorage.setItem(key, JSON.stringify(cap)); else sessionStorage.removeItem(key); } catch { /* storage unavailable */ }
}

/**
 * Owns one guidance journey: the response is always the backend's, never edited locally. Capability tokens are
 * created once per request and reused on retries. Events are serialised and the journey is re-read afterwards so
 * navigation, route, map and recap state always come from the server.
 */
export function useJourney(opts: { sessionId: string; procedureId: string; status: ApiStatus | null; api?: GuidanceApi }) {
  const api = opts.api ?? guidanceApi, key = storeKey(opts.sessionId, opts.procedureId);
  const [response, setResponse] = useState<GuidanceResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<GuidanceError | null>(null);
  const [policyUnavailable, setPolicyUnavailable] = useState(false);
  const cap = useRef<Capability | null>(null), latest = useRef<GuidanceResponse | null>(null), queue = useRef<Promise<void>>(Promise.resolve());
  const pending = useRef(new Map<string, { request_id: string; token: string }>());

  const accept = useCallback((r: GuidanceResponse) => { latest.current = r; setResponse(r); }, []);
  const fail = useCallback((e: unknown) => setError(e instanceof GuidanceError ? e : new GuidanceError(String(e), 0, 'error')), []);

  useEffect(() => {
    const saved = readCap(key);
    cap.current = saved; latest.current = null;
    let live = true;
    if (saved) api.journey(saved.id, saved.token).then(r => { if (live) accept(r); }).catch(() => { writeCap(key, null); cap.current = null; });
    return () => { live = false; };
  }, [api, key, accept]);

  const refresh = useCallback(async () => {
    const c = cap.current; if (!c) return;
    const r = await api.journey(c.id, c.token);
    if (cap.current?.id === c.id) accept(r);
  }, [api, accept]);

  const start = useCallback(async (mode: StartMode) => {
    setBusy(true); setError(null); setPolicyUnavailable(false);
    const signature = JSON.stringify([key, mode]);
    const retry = pending.current.get(signature) ?? { request_id: newId(), token: newToken() };
    pending.current.set(signature, retry);
    try {
      await queue.current;
      if (mode.kind === 'personalized' && !opts.status?.personalized_selection_available) { setPolicyUnavailable(true); return; }
      const base = { request_id: retry.request_id, session_id: opts.sessionId, procedure_id: opts.procedureId, capability_token: retry.token };
      const r = mode.kind === 'preview'
        ? await api.preview({ ...base, mode: 'research_preview', configuration: mode.configuration, ...(mode.provisional ? { allow_provisional: true } : {}) })
        : await api.start({ ...base, mode: mode.kind });
      cap.current = { id: r.journey_id, token: retry.token }; writeCap(key, cap.current); pending.current.delete(signature); accept(r);
    } catch (e) {
      if (e instanceof GuidanceError && e.code === 'revised_policy_unavailable') { setPolicyUnavailable(true); pending.current.delete(signature); }
      else { if (e instanceof GuidanceError && e.status !== 0) pending.current.delete(signature); fail(e); }
    } finally { setBusy(false); }
  }, [api, key, opts.sessionId, opts.procedureId, opts.status, accept, fail]);

  const emit = useCallback((body: EventBody, options: { refresh?: boolean } = {}): Promise<Receipt | null> => {
    const run = queue.current.then(async () => {
      const c = cap.current, view = latest.current?.view_id; if (!c || !view) return null;
      const receipt = await api.event(c.id, c.token, { ...body, event_id: newId(), view_id: view });
      if (options.refresh !== false) await refresh();
      return receipt;
    });
    queue.current = run.then(() => undefined, () => undefined);
    return run.catch(e => { fail(e); return null; });
  }, [api, refresh, fail]);

  const adjust = useCallback(async (configuration: Configuration) => {
    const c = cap.current, view = latest.current?.view_id; if (!c || !view) return;
    setBusy(true); setError(null);
    try { await queue.current; accept(await api.adjust(c.id, c.token, { request_id: newId(), parent_view_id: view, configuration })); } catch (e) { fail(e); } finally { setBusy(false); }
  }, [api, accept, fail]);

  const rate = useCallback(async (rating: 'fits' | 'does_not_fit', reasons: RatingReason[]) => {
    const c = cap.current, view = latest.current?.view_id; if (!c || !view) return null;
    try { await queue.current; const r = await api.rate(c.id, c.token, { event_id: newId(), view_id: view, rating, reasons }); await refresh(); return r; } catch (e) { fail(e); return null; }
  }, [api, refresh, fail]);

  const reset = useCallback(() => { cap.current = null; latest.current = null; writeCap(key, null); setResponse(null); setError(null); setPolicyUnavailable(false); }, [key]);
  const token = () => cap.current?.token ?? null;

  return { response, busy, error, policyUnavailable, start, emit, adjust, rate, refresh, reset, token, clearError: () => setError(null) };
}
