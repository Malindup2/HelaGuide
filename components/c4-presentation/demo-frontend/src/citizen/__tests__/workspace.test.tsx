// @vitest-environment jsdom
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

// The API clients bind fetch when they are constructed, so the dispatcher must exist before the app is imported.
const net = vi.hoisted(() => {
  const state = { handler: (async () => { throw new TypeError('failed'); }) as (input: string, init?: RequestInit) => Promise<Response> };
  globalThis.fetch = ((input: string, init?: RequestInit) => state.handler(String(input), init)) as typeof fetch;
  return state;
});

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import Workspace from '../Workspace';
import { apiStatus, birthStandard, guestSession, procedureList } from './examples';

beforeAll(() => {
  vi.stubGlobal('IntersectionObserver', class { observe() {} unobserve() {} disconnect() {} });
  Element.prototype.scrollIntoView = vi.fn();
  HTMLDialogElement.prototype.showModal ??= function () { this.open = true; };
  HTMLDialogElement.prototype.close ??= function () { this.open = false; };
});
afterEach(() => { cleanup(); sessionStorage.clear(); });

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

function backend(status = apiStatus()) {
  const calls: Array<{ method: string; url: string }> = [];
  vi.stubGlobal('IntersectionObserver', class { observe() {} unobserve() {} disconnect() {} });
  net.handler = async (input, init) => {
    const url = String(input), method = init?.method ?? 'GET';
    calls.push({ method, url });
    if (url.endsWith('/health')) return json({ service: 'c4-independent-dev', status: 'ok', storage: 'sqlite', exposure_requires_acknowledgment: true });
    if (url.endsWith('/workspace/guidance/status')) return json(status);
    if (url.endsWith('/workspace/guidance/procedures')) return json(procedureList());
    if (url.endsWith('/workspace/guidance/profiles') && method === 'GET') return json([]);
    if (url.endsWith('/workspace/guidance/guests')) return json(guestSession());
    if (url.includes('/workspace/guidance/context/')) return json({ effective: {}, origins: {} });
    if (url.includes('/availability')) return json(birthStandard().availability);
    if (url.endsWith('/workspace/guidance/requests')) return json(birthStandard());
    return json({}, 200);
  };
  return calls;
}

describe('Workspace', () => {
  it('lists the three official procedures apart from the fictional research examples', async () => {
    backend();
    render(<Workspace />);
    await waitFor(() => expect(screen.getByText('Official-source procedures')).toBeTruthy());
    expect(screen.getByText('Research examples (fictional)')).toBeTruthy();
    expect((await screen.findAllByRole('button', { name: /Birth certificate copy/i })).length).toBeGreaterThan(0);
    expect(screen.getAllByRole('button', { name: /Continue as guest/i }).length).toBeGreaterThan(0);
  });

  it('asks for standard guidance only for a guest and shows no support, feedback or learning wording', async () => {
    const calls = backend();
    render(<Workspace />);
    await waitFor(() => expect(screen.getByText('Official-source procedures')).toBeTruthy());
    fireEvent.click(screen.getAllByRole('button', { name: /Continue as guest/i })[0]);
    await waitFor(() => expect(calls.some(c => c.url.endsWith('/guests'))).toBe(true));
    fireEvent.click((await screen.findAllByRole('button', { name: /Birth certificate copy/i }))[0]);
    const show = await screen.findByRole('button', { name: /Show (standard )?guidance|Show guidance/i });
    fireEvent.click(show);
    await waitFor(() => expect(calls.some(c => c.method === 'POST' && c.url.endsWith('/requests'))).toBe(true));
    expect(calls.filter(c => c.url.endsWith('/requests')).every(c => c.method === 'POST')).toBe(true);
    expect(calls.some(c => c.url.includes('/research/previews'))).toBe(false);
    await screen.findByText('Step 1');
    expect(screen.queryByText(/Did this way of presenting/)).toBeNull();
    expect(screen.queryByRole('button', { name: /Support/ })).toBeNull();
    expect(document.body.textContent).not.toMatch(/bandit|Thompson|posterior|reward/i);
  });

  it('shows a clear start-the-backend state when the API cannot be reached', async () => {
    net.handler = async () => { throw new TypeError('failed'); };
    render(<Workspace />);
    await waitFor(() => expect(screen.getByText('Start the C4 backend')).toBeTruthy());
  });
});
