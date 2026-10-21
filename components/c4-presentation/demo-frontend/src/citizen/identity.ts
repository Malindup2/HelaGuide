import { API_BASE, C4Api, ContractError, parseProfileResponse, parseSession } from '../api/client';
import type { CreateDemoProfileRequest, DemoProfile, DemoProfileResponse, GuestSession, PersonalizationRequest, ProcedureSummary } from '../api/types';
import type { ProcedureInfo } from './types';

const G = '/workspace/guidance';

/** Adapts the revised procedure list to the shape the saved-profile onboarding already understands. */
export function toProcedureSummary(p: ProcedureInfo): ProcedureSummary {
  return {
    procedure_id: p.procedure_id, plan_id: p.procedure_id, title: p.title, requested_service_id: p.service_id,
    synthetic: p.synthetic, disclaimer: p.source_limit, action_ids: [], completeness: p.completeness, features: {},
  };
}

/**
 * Identity and procedure access through the documented revised endpoints. It keeps the saved-profile
 * workflow of the existing hook. Reading one guest session by id is the only call without a documented
 * revised equivalent, so it uses the existing identity read; a failure simply creates a new guest.
 */
export class GuidanceIdentityApi extends C4Api {
  constructor(baseUrl = API_BASE, fetcher: typeof fetch = globalThis.fetch.bind(globalThis)) { super(baseUrl, fetcher); }

  override async procedures(signal?: AbortSignal): Promise<ProcedureSummary[]> {
    const body = await this.request(`${G}/procedures`, 'GET', signal);
    if (!Array.isArray(body)) throw new ContractError('Invalid procedure list response.');
    return (body as ProcedureInfo[]).map(toProcedureSummary);
  }
  override async createSession(): Promise<GuestSession> { return parseSession(await this.request(`${G}/guests`, 'POST')); }
  override async getSession(sessionId: string, signal?: AbortSignal): Promise<GuestSession> {
    const session = parseSession(await this.request(`/dev/v1/sessions/${encodeURIComponent(sessionId)}`, 'GET', signal));
    if (session.session_id !== sessionId) throw new ContractError('The backend returned a different guest-session identity.');
    return session;
  }
  private async responses(signal?: AbortSignal): Promise<DemoProfileResponse[]> {
    const body = await this.request(`${G}/profiles`, 'GET', signal);
    if (!Array.isArray(body)) throw new ContractError('Invalid saved-profile list response.');
    return body.map(parseProfileResponse);
  }
  override async profiles(signal?: AbortSignal): Promise<DemoProfile[]> { return (await this.responses(signal)).map(r => r.profile); }
  override async getProfile(profileId: string, signal?: AbortSignal): Promise<DemoProfileResponse> {
    const found = (await this.responses(signal)).find(r => r.profile.profile_id === profileId);
    if (!found) throw new ContractError('The saved profile was not found.');
    return found;
  }
  override async createProfile(request: CreateDemoProfileRequest): Promise<DemoProfileResponse> {
    const result = parseProfileResponse(await this.request(`${G}/profiles`, 'POST', undefined, request));
    if (result.profile.profile_id !== request.profile_id) throw new ContractError('Profile creation returned a different identity.');
    return result;
  }
  override async setPersonalization(profileId: string, request: PersonalizationRequest): Promise<DemoProfileResponse> {
    const result = parseProfileResponse(await this.request(`${G}/profiles/${encodeURIComponent(profileId)}/personalization`, 'PATCH', undefined, request));
    if (result.profile.profile_id !== profileId) throw new ContractError('The personalization update returned a different profile.');
    return result;
  }
}

export const guidanceIdentity = new GuidanceIdentityApi();
