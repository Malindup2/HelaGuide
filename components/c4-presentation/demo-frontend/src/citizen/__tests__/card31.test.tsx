// @vitest-environment jsdom
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import GuidanceCard from '../card/GuidanceCard';
import type { GuidanceResponse } from '../types';
import { v31Combo, v31NicFallback, v31ParallelGuided, v31Rich, v31Standard } from './examples';

beforeAll(() => {
  vi.stubGlobal('IntersectionObserver', class { observe() {} unobserve() {} disconnect() {} });
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(cleanup);

const register = (r: GuidanceResponse) => r.document.actions.find(a => a.id === 'action:register_application')!;
const step = (id = 'action:register_application') => document.getElementById(`cz-step-${id}`)!;

describe('content 3.1: D2 chooses the primary explanation, D3 only the supplement', () => {
  it('Concise + OFF: short primary, supplement shown plainly, no show/hide control', () => {
    const r = v31Combo('concise', 'off'), a = register(r);
    render(<GuidanceCard response={r} emit={vi.fn()} />);
    expect(step().textContent).toContain(a.essential);
    expect(step().textContent).toContain(a.explanation_visible!);
    expect(step().querySelector('.cz-label')?.textContent).toBe('More information');
    expect(screen.queryByRole('button', { name: /More guidance/ })).toBeNull();
    expect(a.essential.length).toBeLessThan(100);
  });

  it('Concise + ON: same primary, supplement behind More/Less, opened by a recorded event', () => {
    const r = v31Combo('concise', 'on'), a = register(r), emit = vi.fn();
    const { rerender } = render(<GuidanceCard response={r} emit={emit} />);
    expect(step().textContent).toContain(a.essential);
    expect(step().textContent).not.toContain(a.explanation_hidden!);
    fireEvent.click(step().querySelector('button.cz-toggle') as HTMLElement);
    expect(emit).toHaveBeenCalledWith({ type: 'explanation_open', action_id: a.id });
    const open = structuredClone(r); open.interaction.explanation_open_action_ids = [a.id];
    rerender(<GuidanceCard response={open} emit={emit} />);
    expect(step().textContent).toContain(a.explanation_hidden!);
    expect(step().querySelector('button.cz-toggle')?.textContent).toBe('Less guidance');
  });

  it('Detailed has a fuller primary than Concise in both D3 states, and D3 never changes the primary', () => {
    const lengths: Record<string, number> = {};
    for (const e of ['concise', 'detailed'] as const) for (const d of ['off', 'on'] as const) {
      const r = v31Combo(e, d); lengths[`${e}/${d}`] = register(r).essential.length;
      render(<GuidanceCard response={r} emit={vi.fn()} />);
      expect(step().textContent).toContain(register(r).essential);
      expect(screen.queryByText('In more detail')).toBeNull();
      cleanup();
    }
    expect(lengths['concise/off']).toBe(lengths['concise/on']);
    expect(lengths['detailed/off']).toBe(lengths['detailed/on']);
    expect(lengths['detailed/off']).toBeGreaterThan(lengths['concise/off'] * 1.5);
  });

  it('keeps the heading and the primary visible when the supplement is hidden', () => {
    const r = v31Combo('detailed', 'on');
    render(<GuidanceCard response={r} emit={vi.fn()} />);
    for (const a of r.document.actions.filter(x => !x.branch)) {
      expect(step(a.id).textContent).toContain(a.essential);
      expect(step(a.id).textContent).not.toContain(a.explanation_hidden!);
      expect(step(a.id).querySelector('h3, h4')?.textContent).toBe(a.heading);
    }
  });

  it('never prints the same explanation twice in one step', () => {
    for (const e of ['concise', 'detailed'] as const) for (const d of ['off', 'on'] as const) {
      const r = v31Combo(e, d);
      render(<GuidanceCard response={r} emit={vi.fn()} />);
      for (const a of r.document.actions.filter(x => !x.branch)) {
        const text = step(a.id).textContent ?? '';
        expect(text.split(a.essential).length - 1).toBe(1);
        if (a.explanation_visible) expect(text.split(a.explanation_visible).length - 1).toBe(1);
      }
      cleanup();
    }
  });

  it('keeps the exact source wording out of the step and reachable through Sources', () => {
    const r = v31Combo('concise', 'on'), a = register(r);
    render(<GuidanceCard response={r} emit={vi.fn()} />);
    expect(step().querySelector('details')).toBeNull();
    expect(step().textContent).not.toContain('What the source says');
    fireEvent.click(screen.getByRole('button', { name: /Sources/ }));
    const sheet = document.querySelector('dialog')!;
    expect(sheet.textContent).toContain('Source wording, step by step');
    expect(sheet.textContent).toContain(a.source_wording!.split('\n\n')[0]);
    expect(a.essential).not.toBe(a.source_wording);
  });
});

describe('content 3.1: fallback, structure and scan-friendly facts', () => {
  it('official procedures stay on their source fallback with no invented supplement or source block', () => {
    const r = v31NicFallback();
    render(<GuidanceCard response={r} emit={vi.fn()} />);
    expect(document.querySelector('details.cz-source')).toBeNull();
    expect(screen.queryByText('More information')).toBeNull();
    expect(screen.queryByRole('button', { name: /More guidance/ })).toBeNull();
    expect(screen.getAllByText(/not live or independently verified/).length).toBeGreaterThan(0);
  });

  it('standard 3.1 practice guidance shows documents and charges once, scoped to the stage, and numbered peers', () => {
    const r = v31Standard();
    render(<GuidanceCard response={r} emit={vi.fn()} />);
    expect(screen.getAllByText('LKR 0').length).toBeGreaterThanOrEqual(3);
    expect(document.querySelectorAll('.cz-service').length).toBe(1);
    expect(screen.queryByText('Agency')).toBeNull();
    expect(screen.getByText(/no fixed order/)).toBeTruthy();
  });

  it('rich guidance keeps phases, the map and recap controls while the primary text stays complete', () => {
    const r = v31Rich();
    render(<GuidanceCard response={r} emit={vi.fn()} />);
    expect(screen.getByRole('group', { name: /Procedure map/ })).toBeTruthy();
    expect(document.querySelector('.cz-phaselabel')).toBeTruthy();
    const active = r.document.actions.find(a => a.id === r.interaction.navigation.active_action_id)!;
    expect(document.querySelector('.cz-focus')?.textContent).toContain(active.essential);
  });

  it('guided parallel guidance shows orientation without implying order or completion', () => {
    const r = v31ParallelGuided();
    render(<GuidanceCard response={r} emit={vi.fn()} />);
    expect(document.body.textContent).not.toMatch(/you have (completed|done)|marked as (done|complete)|step (completed|done)|browsing order/i);
    expect(screen.getAllByText(/\d of \d/).length).toBeGreaterThan(0);
  });
});

describe('accessibility', () => {
  it('returns focus to the control that opened a sheet, even when React replays effects (StrictMode)', async () => {
    const { StrictMode } = await import('react');
    render(<StrictMode><GuidanceCard response={v31Rich()} emit={vi.fn()} /></StrictMode>);
    const opener = screen.getByRole('button', { name: /Sources/ });
    opener.focus();
    fireEvent.click(opener);
    expect(screen.getByRole('button', { name: 'Close Sources and scope' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Close Sources and scope' }));
    expect(document.activeElement).toBe(opener);
  });

  it('gives every visible control an accessible name', () => {
    render(<GuidanceCard response={v31Rich()} emit={vi.fn()} />);
    const controls = [...document.querySelectorAll('button, a[href], input, select, summary')];
    const unnamed = controls.filter(el => !(el.getAttribute('aria-label') || el.textContent?.trim() || el.getAttribute('title') || (el as HTMLInputElement).labels?.length));
    expect(unnamed.map(el => el.outerHTML.slice(0, 80))).toEqual([]);
  });
});
