// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import ProfileContext from '../ProfileContext';
import { guidanceApi } from '../api';
import { parseSession } from '../../api/client';
import { apiStatus, guestSession } from './examples';

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

const ctx = (identity: number, familiarity: number | null) => ({ schema_version: 'x', session_id: 's', profile_id: 'p', personalization_enabled: true, service_id: 'svc', familiarity, confidence: 3, preferences: {},
  constraints: { locks: {}, no_guided: false, no_map: false, no_disclosure: false }, revision: { identity, revised: 0 }, sources: {}, scoring_use: '',
  legacy: { hard_requirements_unresolved: false, preferences_not_imported: {}, pending_preference_review: {} } });

describe('saving profile context', () => {
  it('sends the settings revision reported by the backend (not the session revision) on every save, so repeated saves do not conflict', async () => {
    const session = parseSession(guestSession());
    const sent: number[] = [];
    let identity = session.revision + 7;                         // deliberately different from the session revision, as it is after a first save
    vi.spyOn(guidanceApi, 'context').mockImplementation(async () => ctx(identity, 1) as never);
    vi.spyOn(guidanceApi, 'patchProfileContext').mockImplementation(async (_id, body) => { sent.push(body.expected_identity_revision); identity += 2; return { session: guestSession() }; });
    const procedure = { procedure_id: 'official-nic_amendment-v3', requested_service_id: 'svc:nic_amendment' } as never;
    render(<ProfileContext active={{ kind: 'profile', session, profile: {} } as never} procedure={procedure} onSession={vi.fn()} />);
    await waitFor(() => screen.getByText(/familiarity 1 of 5/));
    fireEvent.click(screen.getByText('Edit saved settings'));
    for (let i = 0; i < 3; i++) {
      fireEvent.click(screen.getByRole('button', { name: 'Save settings' }));
      await waitFor(() => expect(sent.length).toBe(i + 1));
      await waitFor(() => expect(screen.getByRole('button', { name: 'Save settings' })).toBeTruthy());
    }
    expect(sent).toEqual([session.revision + 7, session.revision + 9, session.revision + 11]);
    expect(apiStatus()).toBeTruthy();
  });

  it('sends optional soft preferences through the context endpoint with the current revision, leaving unanswered dimensions out', async () => {
    const session = parseSession(guestSession());
    const calls: { preferences: Record<string, string>; revision: { identity: number; revised: number } }[] = [];
    vi.spyOn(guidanceApi, 'context').mockImplementation(async () => ctx(session.revision + 3, 2) as never);
    vi.spyOn(guidanceApi, 'patchProfileContext').mockImplementation(async () => ({ session: guestSession() }));
    vi.spyOn(guidanceApi, 'patchContext').mockImplementation(async (_id, body) => { calls.push({ preferences: body.preferences, revision: body.expected_revision }); return {}; });
    const procedure = { procedure_id: 'official-nic_amendment-v4', requested_service_id: 'svc:nic_amendment_card' } as never;
    render(<ProfileContext active={{ kind: 'profile', session, profile: {} } as never} procedure={procedure} onSession={vi.fn()} />);
    await waitFor(() => screen.getByText(/familiarity 2 of 5/));
    fireEvent.click(screen.getByText('Edit saved settings'));
    fireEvent.click(screen.getByText('Presentation preferences (optional)'));
    expect((screen.getByLabelText('Navigation') as HTMLSelectElement).value).toBe('');             // unanswered stays "No preference"
    fireEvent.change(screen.getByLabelText('Explanation'), { target: { value: 'detailed' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save settings' }));
    await waitFor(() => expect(calls.length).toBe(1));
    expect(calls[0]).toEqual({ preferences: { explanation: 'detailed' }, revision: { identity: session.revision + 3, revised: 0 } });
  });
});
