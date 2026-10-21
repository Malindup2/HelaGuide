import { API_BASE } from '../api/client';
import type {
  ApiStatus, Availability, Configuration, EffectiveContext, EventBody, GuidanceResponse, InspectorRecord, ProcedureInfo, RatingReason, Receipt,
} from './types';

const BASE = '/workspace/guidance';

/** Backend errors use detail={code,message,...}; FastAPI validation errors use a list. Both are normalised. */
export class GuidanceError extends Error {
  constructor(message: string, readonly status: number, readonly code: string, readonly reasons: string[] = [], readonly detail: unknown = null) {
    super(message);
    this.name = 'GuidanceError';
  }
}

export const newId = () => crypto.randomUUID();
/** 32-128 characters; generated once per request and reused on retries. */
export const newToken = () => crypto.randomUUID().replaceAll('-', '') + crypto.randomUUID().replaceAll('-', '');

function normalise(status: number, body: unknown): GuidanceError {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    const d = detail as { code?: string; message?: string; reasons?: string[] };
    return new GuidanceError(d.message ?? `The backend returned HTTP ${status}.`, status, d.code ?? 'error', d.reasons ?? [], detail);
  }
  if (Array.isArray(detail)) return new GuidanceError('The request was not accepted by the backend.', status, 'validation', [], detail);
  return new GuidanceError(`The backend returned HTTP ${status}.`, status, 'error', [], body);
}

export class GuidanceApi {
  constructor(private readonly baseUrl = API_BASE, private readonly fetcher: typeof fetch = globalThis.fetch.bind(globalThis)) {}

  async request<T>(path: string, method: 'GET' | 'POST' | 'PATCH', opts: { body?: unknown; token?: string; signal?: AbortSignal } = {}): Promise<T> {
    let response: Response;
    try {
      response = await this.fetcher(`${this.baseUrl}${BASE}${path}`, {
        method, signal: opts.signal, cache: 'no-store',
        headers: { Accept: 'application/json', ...(opts.body === undefined ? {} : { 'Content-Type': 'application/json' }), ...(opts.token ? { 'X-C4-Token': opts.token } : {}) },
        ...(opts.body === undefined ? {} : { body: JSON.stringify(opts.body) }),
      });
    } catch (error) {
      if (opts.signal?.aborted) throw error;
      throw new GuidanceError(`Cannot reach the guidance service at ${this.baseUrl}.`, 0, 'unreachable');
    }
    const text = await response.text();
    let body: unknown = null;
    if (text) { try { body = JSON.parse(text); } catch { throw new GuidanceError('The backend returned invalid JSON.', response.status, 'invalid_json'); } }
    if (!response.ok) throw normalise(response.status, body);
    return body as T;
  }

  status(signal?: AbortSignal) { return this.request<ApiStatus>('/status', 'GET', { signal }); }
  procedures(signal?: AbortSignal) { return this.request<ProcedureInfo[]>('/procedures', 'GET', { signal }); }
  context(sessionId: string, procedureId: string, signal?: AbortSignal) {
    return this.request<EffectiveContext>(`/context/${encodeURIComponent(sessionId)}?procedure_id=${encodeURIComponent(procedureId)}`, 'GET', { signal });
  }
  availability(procedureId: string, sessionId: string, signal?: AbortSignal) {
    return this.request<Availability>(`/procedures/${encodeURIComponent(procedureId)}/availability?session_id=${encodeURIComponent(sessionId)}&language=en`, 'GET', { signal });
  }
  start(body: { request_id: string; session_id: string; procedure_id: string; capability_token: string; mode: 'standard' | 'personalized'; expected_context_revision?: { identity: number; revised: number } | null }) {
    return this.request<GuidanceResponse>('/requests', 'POST', { body });
  }
  preview(body: { request_id: string; session_id: string; procedure_id: string; capability_token: string; mode: 'research_preview'; configuration: Configuration }) {
    return this.request<GuidanceResponse>('/research/previews', 'POST', { body });
  }
  journey(id: string, token: string, signal?: AbortSignal) { return this.request<GuidanceResponse>(`/journeys/${encodeURIComponent(id)}`, 'GET', { token, signal }); }
  event(id: string, token: string, body: EventBody & { event_id: string; view_id: string }) {
    return this.request<Receipt>(`/journeys/${encodeURIComponent(id)}/events`, 'POST', { token, body });
  }
  adjust(id: string, token: string, body: { request_id: string; parent_view_id: string; configuration: Configuration }) {
    return this.request<GuidanceResponse>(`/journeys/${encodeURIComponent(id)}/views`, 'POST', { token, body });
  }
  rate(id: string, token: string, body: { event_id: string; view_id: string; rating: 'fits' | 'does_not_fit'; reasons: RatingReason[] }) {
    return this.request<Receipt>(`/journeys/${encodeURIComponent(id)}/ratings`, 'POST', { token, body });
  }
  inspector(id: string, token: string, signal?: AbortSignal) { return this.request<InspectorRecord>(`/journeys/${encodeURIComponent(id)}/inspector`, 'GET', { token, signal }); }
  /** Saved service familiarity, navigation confidence and accessibility, through the existing profile services. */
  patchProfileContext(sessionId: string, body: { request_id: string; expected_identity_revision: number; familiarity?: { service_id: string; score: number | null; source: 'self_reported' }[]; confidence?: number | null; accessibility?: { allow_relationship_visuals: boolean; allow_collapsed_content: boolean; allow_guided_navigation: boolean } }) {
    return this.request<{ session: unknown }>(`/profile-context/${encodeURIComponent(sessionId)}`, 'PATCH', { body });
  }
}

export const guidanceApi = new GuidanceApi();
