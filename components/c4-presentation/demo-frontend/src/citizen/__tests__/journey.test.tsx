// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { GuidanceError } from '../api';
import type { GuidanceApi } from '../api';
import { useJourney } from '../useJourney';
import type { ApiStatus } from '../types';
import { apiStatus, birthStandard, practiceRich } from './examples';

afterEach(() => { cleanup(); sessionStorage.clear(); });

function fake(over: Record<string, unknown> = {}) {
  const r = birthStandard();
  return {
    start: vi.fn().mockResolvedValue(r), preview: vi.fn().mockResolvedValue(practiceRich()), journey: vi.fn().mockResolvedValue(r),
    event: vi.fn().mockResolvedValue({ recorded: true }), adjust: vi.fn().mockResolvedValue(r), rate: vi.fn().mockResolvedValue({}), ...over,
  } as unknown as GuidanceApi & Record<string, ReturnType<typeof vi.fn>>;
}
const hook = (api: GuidanceApi, status: ApiStatus | null = apiStatus()) => renderHook(() => useJourney({ sessionId: 's1', procedureId: 'p1', status, api }));

describe('useJourney', () => {
  it('starts standard guidance with a request id and a token, and keeps the token only in session storage', async () => {
    const api = fake(), { result } = hook(api);
    await act(async () => { await result.current.start({ kind: 'standard' }); });
    const body = (api.start as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(body).toMatchObject({ mode: 'standard', session_id: 's1', procedure_id: 'p1' });
    expect(body.capability_token.length).toBeGreaterThanOrEqual(32);
    expect(result.current.response?.journey_id).toBeTruthy();
  });

  it('does not call the personalized endpoint while the policy is unavailable, and invents no decision', async () => {
    const api = fake(), { result } = hook(api, { ...apiStatus(), personalized_selection_available: false });
    await act(async () => { await result.current.start({ kind: 'personalized' }); });
    expect(api.start).not.toHaveBeenCalled();
    expect(result.current.policyUnavailable).toBe(true);
    expect(result.current.response).toBeNull();
  });

  it('treats a 503 revised_policy_unavailable as a notice, not an error or a fallback', async () => {
    const api = fake({ start: vi.fn().mockRejectedValue(new GuidanceError('no', 503, 'revised_policy_unavailable')) });
    const { result } = hook(api, { ...apiStatus(), personalized_selection_available: true });
    await act(async () => { await result.current.start({ kind: 'personalized' }); });
    expect(result.current.policyUnavailable).toBe(true);
    expect(result.current.error).toBeNull();
    expect(result.current.response).toBeNull();
  });

  it('reuses the request id and token when a failed start is retried', async () => {
    const api = fake({ start: vi.fn().mockRejectedValueOnce(new GuidanceError('down', 0, 'unreachable')).mockResolvedValue(birthStandard()) });
    const { result } = hook(api);
    await act(async () => { await result.current.start({ kind: 'standard' }); });
    expect(result.current.error?.code).toBe('unreachable');
    await act(async () => { await result.current.start({ kind: 'standard' }); });
    const [first, second] = (api.start as ReturnType<typeof vi.fn>).mock.calls.map(c => c[0]);
    expect(second.request_id).toBe(first.request_id);
    expect(second.capability_token).toBe(first.capability_token);
    expect(result.current.error).toBeNull();
  });

  it('sends the preview through the preview endpoint with the chosen configuration', async () => {
    const api = fake(), { result } = hook(api), configuration = practiceRich().document.configuration;
    await act(async () => { await result.current.start({ kind: 'preview', configuration }); });
    expect(api.preview).toHaveBeenCalledWith(expect.objectContaining({ mode: 'research_preview', configuration }));
    expect(api.start).not.toHaveBeenCalled();
  });

  it('sends events for the current view with a fresh event id and then re-reads the journey', async () => {
    const api = fake(), { result } = hook(api);
    await act(async () => { await result.current.start({ kind: 'standard' }); });
    const view = result.current.response!.view_id;
    await act(async () => { await result.current.emit({ type: 'overview_peek' }); });
    const sent = (api.event as ReturnType<typeof vi.fn>).mock.calls[0][2];
    expect(sent).toMatchObject({ type: 'overview_peek', view_id: view });
    expect(sent.event_id).toBeTruthy();
    expect(api.journey).toHaveBeenCalledTimes(1);
    await act(async () => { await result.current.emit({ type: 'view_displayed' }, { refresh: false }); });
    expect(api.journey).toHaveBeenCalledTimes(1);
  });

  it('adjusts through a child view and submits ratings with their reasons', async () => {
    const api = fake(), { result } = hook(api), config = practiceRich().document.configuration;
    await act(async () => { await result.current.start({ kind: 'standard' }); });
    const parent = result.current.response!.view_id;
    await act(async () => { await result.current.adjust(config); });
    expect(api.adjust).toHaveBeenCalledWith(expect.any(String), expect.any(String), expect.objectContaining({ parent_view_id: parent, configuration: config }));
    await act(async () => { await result.current.rate('does_not_fit', ['too_much_explanation']); });
    expect(api.rate).toHaveBeenCalledWith(expect.any(String), expect.any(String), expect.objectContaining({ rating: 'does_not_fit', reasons: ['too_much_explanation'] }));
  });

  it('restores a saved journey on reload using the stored capability and forgets it when the server refuses', async () => {
    const api = fake(), first = hook(api);
    await act(async () => { await first.result.current.start({ kind: 'standard' }); });
    first.unmount();
    const again = hook(api);
    await waitFor(() => expect(again.result.current.response).not.toBeNull());
    expect(api.journey).toHaveBeenCalled();
    again.unmount();
    const refused = fake({ journey: vi.fn().mockRejectedValue(new GuidanceError('gone', 404, 'not_found')) });
    const third = hook(refused);
    await waitFor(() => expect(refused.journey).toHaveBeenCalled());
    expect(third.result.current.response).toBeNull();
  });
});
