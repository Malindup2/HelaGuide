// @vitest-environment jsdom
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import GuidanceCard from '../card/GuidanceCard';
import { accepted } from './examples';

beforeAll(() => {
  vi.stubGlobal('IntersectionObserver', class { observe() {} unobserve() {} disconnect() {} });
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(cleanup);

const step = (id: string) => document.getElementById(`cz-step-${id}`)!;

describe('demo-accepted cached wording in ordinary journeys (real responses, trained policy copy)', () => {
  it.each(['birth', 'nic', 'company'])('%s: standard guest guidance uses the accepted wording with an honest local-demo label and no review claim', key => {
    const r = accepted(`standard-${key}`);
    render(<GuidanceCard response={r} emit={vi.fn()} />);
    expect(r.preparation.content_state).toBe('demo_accepted');
    expect(document.querySelector('.cz-provisional')).toBeNull();                           // no repeated banner on the card
    expect(document.querySelector('.cz-meta')!.textContent).toMatch(/Prototype guidance/);
    fireEvent.click(screen.getByRole('button', { name: /Sources/ }));
    const sheet = document.querySelector('dialog')!.textContent!;
    expect(sheet).toMatch(/accepted it for this local research demonstration/);
    expect(sheet).toMatch(/No expert, agency or government body has reviewed it/);
    expect(document.body.textContent).not.toMatch(/approved by (an? )?(expert|government)|expert reviewed|independently validated guidance/i);
    expect(r.selection.kind).toBe('standard');
  });

  it.each(['birth', 'nic', 'company'])('%s: personalised views are genuine LinTS selections, and experienced citizens get lighter guidance than novices', key => {
    const compact = accepted(`personalised-${key}-experienced-compact`), rich = accepted(`personalised-${key}-novice-rich`);
    for (const r of [compact, rich]) {
      expect(r.selection.kind).toBe('shared_gaussian_lints');
      expect(r.selection.learning_eligible && r.selection.scoring_status === 'executed').toBe(true);
      expect(r.preparation.content_state).toBe('demo_accepted');
    }
    const extras = (r: typeof compact) => Object.values(r.selection.configuration).filter(v => !['overview', 'concise', 'off', 'none'].includes(v)).length;
    expect(extras(rich)).toBeGreaterThan(extras(compact));
    render(<GuidanceCard response={compact} emit={vi.fn()} />);
    expect(document.querySelector('.cz-focus')).toBeNull();   // an experienced citizen's compact overview has no guided focus panel
    expect(compact.selection.configuration.navigation).toBe('overview');
  });

  it('four D2 x D3 combinations: Detailed is richer than Concise, D3 only moves the separate supplement', () => {
    const view = (e: string, d: string) => accepted(`preview-birth-${e}-${d}`).document.actions.find(a => a.id === 'action:birth_pay')!;
    const [co, cn, dof, dn] = [view('concise', 'off'), view('concise', 'on'), view('detailed', 'off'), view('detailed', 'on')];
    expect(dof.essential.length).toBeGreaterThan(co.essential.length * 1.5);
    expect(cn.essential).toBe(co.essential); expect(dn.essential).toBe(dof.essential);
    for (const [off, on] of [[co, cn], [dof, dn]]) {
      expect(off.explanation_visible).toBeTruthy(); expect(off.explanation_hidden).toBeFalsy();
      expect(on.explanation_visible).toBeFalsy(); expect(on.explanation_hidden).toBe(off.explanation_visible);
    }
    for (const [e, d] of [['concise', 'off'], ['concise', 'on'], ['detailed', 'off'], ['detailed', 'on']]) {
      render(<GuidanceCard response={accepted(`preview-birth-${e}-${d}`)} emit={vi.fn()} />);
      const pay = step('action:birth_pay');
      expect(!!pay.querySelector('button.cz-toggle')).toBe(d === 'on');
      expect(pay.querySelectorAll('p.cz-essential').length).toBe(1);
      expect(pay.textContent).toMatch(/Pay\s*LKR 120/);
      cleanup();
    }
  });

  it('NIC: both routes keep their own steps and the one route fee is shown once, not repeated in the supplement text', () => {
    const r = accepted('standard-nic');
    render(<GuidanceCard response={r} emit={vi.fn()} />);
    const lists = [...document.querySelectorAll('.cz-preview')].map(o => o.querySelectorAll('li').length).sort();
    expect(lists).toEqual([1, 2]);
    expect(document.querySelectorAll('.cz-fee').length).toBe(1);
    const detailed = accepted('preview-nic-detailed-off');
    for (const a of detailed.document.actions) expect(`${a.essential} ${a.explanation_visible ?? ''}`).not.toMatch(/LKR 500/);
  });

  it('NIC guided (novice) selection still shows the route fee and both routes before a choice is made', () => {
    const r = accepted('personalised-nic-novice-rich');
    expect(r.selection.configuration.navigation).toBe('guided');
    render(<GuidanceCard response={r} emit={vi.fn()} />);
    expect(document.querySelector('.cz-route')!.textContent).toMatch(/LKR 500/);
    expect(document.querySelectorAll('.cz-fee').length).toBe(1);
    expect([...document.querySelectorAll('.cz-preview')].map(o => o.querySelectorAll('li').length).sort()).toEqual([1, 2]);
  });

  it('structural limits stay visible: no phases for birth and NIC, no map without verified parallel coverage', () => {
    for (const key of ['birth', 'nic']) {
      const av = accepted(`availability-${key}`) as unknown as { candidates: { feasible: boolean; configuration: Record<string, string> }[]; feasible_count: number };
      const ok = av.candidates.filter(c => c.feasible);
      expect(av.feasible_count).toBe(32);
      expect(ok.every(c => c.configuration.segmentation === 'off' && c.configuration.relationships !== 'map')).toBe(true);
    }
    const company = accepted('availability-company') as unknown as { feasible_count: number };
    expect(company.feasible_count).toBe(64);
  });
});
