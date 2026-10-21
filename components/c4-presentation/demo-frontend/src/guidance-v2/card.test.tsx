// @vitest-environment jsdom
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import fixture from './fixture.json';
import GuidanceMessage from './card/GuidanceCard';
import { outline, resolveLayout } from './presentation';
import type { Configuration, Journey } from './types';

const base: Configuration = { navigation: 'overview', explanation: 'concise', disclosure: 'collapsed', relationships: 'none', recap: 'off', summary: 'off' };
const make = (config: Partial<Configuration> = {}, mutate?: (j: Journey) => void) => {
  const j = structuredClone(fixture) as unknown as Journey;
  j.views[j.current_view].configuration = { ...base, ...config };
  j.views[j.current_view].displayed = [j.document.actions[0].id];
  mutate?.(j);
  return j;
};
const show = (config: Partial<Configuration> = {}, mutate?: (j: Journey) => void, event = vi.fn()) =>
  render(<GuidanceMessage journey={make(config, mutate)} event={event} adjust={vi.fn()} rate={vi.fn()} />);

beforeAll(() => {
  vi.stubGlobal('IntersectionObserver', class { observe() {} unobserve() {} disconnect() {} });
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(cleanup);

describe('each backend dimension is expressed, and only by its own state', () => {
  it('navigation: overview is an accordion list, guided is one focused action with a pager', () => {
    const overview = show();
    expect(document.querySelector('.gc-list')).toBeTruthy();
    expect(document.querySelector('.gc-pager')).toBeNull();
    overview.unmount();
    show({ navigation: 'guided' });
    expect(document.querySelector('.gc-list')).toBeNull();
    expect(screen.getByRole('button', { name: 'Next' })).toBeTruthy();
    expect(document.querySelectorAll('.gc-focus')).toHaveLength(1);
  });

  it('explanation: expanded shows the reviewed fuller text visibly and separately from optional extras', () => {
    const concise = show();
    expect(screen.queryByText('Fuller explanation')).toBeNull();
    expect(document.body.textContent).not.toContain('Registration is the common prerequisite');
    concise.unmount();
    show({ explanation: 'expanded' });
    expect(screen.getByText('Fuller explanation')).toBeTruthy();
    const prose = screen.getByText(/Registration is the common prerequisite/);
    expect(prose.closest('details')).toBeNull();
    expect(document.querySelectorAll('.gc-extra').length).toBeGreaterThan(0);
  });

  it('disclosure: optional extras exist in both states and only start open when expanded', () => {
    const closed = show();
    expect((document.querySelector('.gc-extra details') as HTMLDetailsElement).open).toBe(false);
    closed.unmount();
    show({ disclosure: 'expanded' });
    expect((document.querySelector('.gc-extra details') as HTMLDetailsElement).open).toBe(true);
  });

  it('relationships: none is text, inline adds references, map adds a compact expandable map', () => {
    const none = show();
    expect(screen.getAllByText('Do first').length).toBeGreaterThan(0);
    expect(document.querySelector('.gc-ref')).toBeNull();
    expect(document.querySelector('.gc-map')).toBeNull();
    none.unmount();
    const inline = show({ relationships: 'inline' });
    expect(document.querySelector('.gc-ref')).toBeTruthy();
    expect(document.querySelector('.gc-map')).toBeNull();
    inline.unmount();
    show({ relationships: 'map' });
    expect(document.querySelector('.gc-map')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /Expand map/ }));
    expect(document.querySelector('.gc-sheet .gc-graph-large')).toBeTruthy();
  });

  it('recap: nothing is invented before anything has been viewed, and appears once earlier actions were viewed', () => {
    const empty = show({ recap: 'on' }, j => { j.focus = j.document.actions.at(-1)!.id; j.seen = []; });
    expect(screen.queryByText(/Earlier in this journey/)).toBeNull();
    empty.unmount();
    show({ recap: 'on' }, j => { j.focus = j.document.actions.at(-1)!.id; j.seen = j.document.actions.map(a => a.id); });
    expect(screen.getByText(/Earlier in this journey/)).toBeTruthy();
  });

  it('summary: a single consolidated view, with per-action needs reduced to a reference', () => {
    const off = show();
    expect(screen.queryByRole('button', { name: /Before you start/ })).toBeNull();
    expect(screen.queryByText(/listed in Before you start/)).toBeNull();
    off.unmount();
    show({ summary: 'on' });
    fireEvent.click(screen.getByRole('button', { name: /Before you start/ }));
    expect(screen.getByText('Needed in every case')).toBeTruthy();
    expect(screen.getAllByText(/listed in Before you start/).length).toBeGreaterThan(0);
  });
});

describe('overview rows keep essential information visible while collapsed', () => {
  it('shows prerequisites and required documents without opening the row', () => {
    show();
    const submit = document.getElementById('gc-h-action:submit_application')!.closest('.gc-row')!;
    expect(submit.getAttribute('data-open')).toBe('false');
    expect(submit.textContent).toContain('Do first');
    expect(submit.textContent).toContain('Bring Fictional supporting copy, Fictional completed application form');
  });
});

describe('accessible names', () => {
  it('names row, support and stepper controls by their visible labels', () => {
    show({ explanation: 'concise' });
    expect(screen.getByRole('button', { name: 'Prepare the form' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Support' }));
    for (const label of ['Overview', 'Guided', 'Concise', 'Text only', 'Inline', 'Process map']) expect(screen.getByRole('button', { name: label })).toBeTruthy();
  });
});

describe('route choice', () => {
  it('only focuses a route: it records route_focus, keeps the other route reachable and never numbers alternatives', () => {
    const event = vi.fn();
    show({}, undefined, event);
    expect(screen.getByText('You do not have the fictional supporting copy.')).toBeTruthy();
    fireEvent.click(screen.getAllByRole('button', { name: 'Show steps' })[0]);
    const routeEvents = event.mock.calls.filter(c => c[0].type === 'route_focus');
    expect(routeEvents).toHaveLength(1);
    expect(screen.getByText('You already have the fictional supporting copy.')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Show this route' })).toBeTruthy();
    expect(document.querySelector('.gc-mark-route')!.textContent).toBe('A');
  });

  it('opening a row records a navigate event for that action', () => {
    const event = vi.fn();
    show({}, undefined, event);
    fireEvent.click(document.getElementById('gc-h-action:prepare_form')!);
    expect(event).toHaveBeenCalledWith({ type: 'navigate', action_id: 'action:prepare_form' });
  });
});

describe('layout resolver and outline', () => {
  it('maps configuration to layout without choosing or changing it', () => {
    expect(resolveLayout(base)).toMatchObject({ list: 'accordion', strip: 'none', needs: 'inline', cues: 'text', explanation: 'plain' });
    expect(resolveLayout({ ...base, navigation: 'guided' })).toMatchObject({ list: 'focused', strip: 'dots' });
    expect(resolveLayout({ ...base, navigation: 'guided', relationships: 'map' })).toMatchObject({ strip: 'graph', map: true });
    expect(resolveLayout({ ...base, summary: 'on' })).toMatchObject({ needs: 'reference', prepare: true });
    expect(resolveLayout({ ...base, summary: 'on', navigation: 'guided' })).toMatchObject({ needs: 'inline' });
  });

  it('gathers alternative routes into one group at the position where they are first browsed', () => {
    const blocks = outline(make().document);
    expect(blocks.map(b => b.kind)).toEqual(['action', 'group', 'action', 'action']);
    const group = blocks[1];
    expect(group.kind === 'group' && group.options.map(o => o.actions.length)).toEqual([1, 1]);
  });
});
