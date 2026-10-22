// @vitest-environment jsdom
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import GuidanceCard from '../card/GuidanceCard';
import { actionFacts, provisional, v31Combo } from './examples';

beforeAll(() => {
  vi.stubGlobal('IntersectionObserver', class { observe() {} unobserve() {} disconnect() {} });
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(cleanup);

const step = (id: string) => document.getElementById(`cz-step-${id}`)!;
const rows = (el: Element | null) => [...(el?.querySelectorAll('.cz-facts p') ?? [])].map(p => p.textContent ?? '');

describe('step-first layout', () => {
  it('shows title, short primary text and small labelled cards, with the extra guidance behind a compact control', () => {
    const r = v31Combo('concise', 'on');
    render(<GuidanceCard response={r} emit={vi.fn()} />);
    const submit = step('action:submit_application');
    expect(submit.querySelector('h3, h4')?.textContent).toBe(r.document.actions.find(a => a.id === 'action:submit_application')!.heading);
    expect(rows(submit.querySelector('.cz-atstep')).join('|')).toMatch(/WHERE|Where/i);
    expect(submit.textContent).toContain('Submit');
    expect(submit.querySelector('button.cz-toggle')?.textContent).toBe('More guidance');
    expect(submit.querySelectorAll('.cz-expl').length).toBe(0);
    expect(submit.querySelectorAll('p.cz-essential').length).toBe(1);
  });

  it('keeps the exact source text out of every step and the oversized procedure-wide panel gone', () => {
    render(<GuidanceCard response={v31Combo('detailed', 'off')} emit={vi.fn()} />);
    expect(document.querySelector('.cz-reqs')).toBeNull();
    expect(document.querySelector('details')).toBeNull();
    expect(document.body.textContent).not.toContain('What the source says');
  });

  it('puts only facts that no step can claim into one slim whole-service strip, with no repeated disclaimer', () => {
    render(<GuidanceCard response={actionFacts('standard-synthetic-practice-v2')} emit={vi.fn()} />);
    const strip = document.querySelector('.cz-service')!;
    expect(strip.querySelectorAll('.cz-fee').length).toBe(3);
    expect(strip.textContent).not.toMatch(/Fictional (completed|supporting)/);
    expect(document.body.textContent?.match(/not added together/g)?.length).toBe(1);
  });

  it('removes a step\'s own title from its "can be done alongside" cue and writes "or" in plain letters', () => {
    const r = v31Combo('concise', 'off');
    r.document.configuration.relationships = 'inline';
    r.document.relationship_aid.inline_by_action = { 'action:prepare_form': [{ kind: 'parallel', text: 'Verified parallel work: Prepare the fictional application form after registration; The applicable route (A OR B)', evidence_ids: [], relation_id: 'x' }] };
    render(<GuidanceCard response={r} emit={vi.fn()} />);
    const cue = step('action:prepare_form').querySelector('.cz-cues')!.textContent!;
    expect(cue).toContain('The applicable route (A or B)');
    expect(cue).not.toContain('Prepare the fictional application form after registration');
  });
});

describe('provisional demo wording is labelled and sits beside the same structure rules', () => {
  it('keeps the provisional state out of the card body and states it in Sources, with no claim of review', () => {
    render(<GuidanceCard response={provisional('provisional-nic-compact')} emit={vi.fn()} />);
    expect(document.querySelector('.cz-provisional')).toBeNull();
    expect(document.querySelector('.cz-meta')!.textContent).toMatch(/Prototype guidance/);
    fireEvent.click(screen.getByRole('button', { name: /Sources/ }));
    expect(document.querySelector('dialog')!.textContent).toMatch(/No person or authority has reviewed it/);
    expect(document.body.textContent).not.toMatch(/approved by|government approved|expert reviewed/i);
  });

  it('NIC: one fee for the choice of routes, shown once with its payment channel and postal note, not in any step and not in the strip', () => {
    const r = provisional('provisional-nic-map');
    render(<GuidanceCard response={r} emit={vi.fn()} />);
    const choice = document.querySelector('.cz-route')!;
    expect(choice.textContent).toContain('Pay');
    expect(choice.textContent).toContain('Postal delivery adds LKR 120');
    expect(choice.textContent).toContain('Applies whichever route you take');
    expect(document.querySelectorAll('.cz-fee').length).toBe(1);
    expect(document.querySelector('.cz-service')).toBeNull();
  });

  it('NIC: before a choice each route lists its own numbered steps (estate one, non-estate two), and nothing is sequenced across routes', () => {
    render(<GuidanceCard response={provisional('provisional-nic-compact')} emit={vi.fn()} />);
    const lists = [...document.querySelectorAll('.cz-preview')].map(o => [...o.querySelectorAll('li')].length);
    expect(lists.sort()).toEqual([1, 2]);
    expect(document.querySelectorAll('.cz-preview').length).toBe(2);
    expect([...document.querySelectorAll('.cz-layerhead')].some(h => /Step 2/.test(h.textContent ?? ''))).toBe(false);
  });

  it('NIC: the map draws exactly the verified route frame and the one dependency, with a text version', () => {
    const r = provisional('provisional-nic-map');
    render(<GuidanceCard response={r} emit={vi.fn()} />);
    expect(document.querySelectorAll('.cz-node').length).toBe(3);
    expect(document.querySelectorAll('.cz-edge').length).toBe(r.document.relationship_aid.map!.edges.length);
    expect(document.querySelectorAll('.cz-frame').length).toBe(1);
    expect(screen.getByText('Text version of the map')).toBeTruthy();
  });

  it('NIC: choosing the non-estate route shows its two steps with a desk and the application card', () => {
    const r = provisional('provisional-nic-compact');
    const route = r.document.routes[0], two = route.options.find(o => o.action_ids.length === 2)!;
    r.interaction.route_choices = { [route.branch_id]: [two.option_id] };
    render(<GuidanceCard response={r} emit={vi.fn()} />);
    for (const id of two.action_ids) expect(step(id).querySelector('.cz-atstep')?.textContent).toMatch(/NIC amendment application/);
    expect(step('action:nic_gn').textContent).toContain('Grama Niladhari');
    expect(step('action:nic_ds').textContent).toContain('Divisional Secretary');
  });

  it('birth certificate copy: Pay and Keep at the payment step with the counter-route note, Submit at the submission step', () => {
    render(<GuidanceCard response={provisional('provisional-birth-compact')} emit={vi.fn()} />);
    const pay = step('action:birth_pay'), submit = step('action:birth_submit');
    expect(rows(pay.querySelector('.cz-atstep')).join('|')).toMatch(/Keep.*Payment receipt/);
    expect(pay.textContent).toMatch(/Pay\s*LKR 120/);
    expect(pay.textContent).toContain('excludes ATM and online payments');
    expect(submit.textContent).toMatch(/Submit.*Completed application.*Payment receipt/s);
    expect(submit.querySelector('.cz-fee')).toBeNull();
  });

  it('company: Form 1 charge is a Charge with its qualification, never a Pay instruction', () => {
    render(<GuidanceCard response={provisional('provisional-company-compact')} emit={vi.fn()} />);
    const form = step('action:company_form');
    expect(form.textContent).toMatch(/Charge\s*LKR 4,000/);
    expect(form.textContent).toContain('Payment is outside this step');
    expect(document.body.textContent).not.toMatch(/\bPay\b.*LKR 4,000/);
    expect(rows(form.querySelector('.cz-atstep')).join('|')).toMatch(/Prepare.*Form 1/);
  });

  it('company: phases group the four preparation steps and the submission, and recap never says done', () => {
    const r = provisional('provisional-company-rich');
    render(<GuidanceCard response={r} emit={vi.fn()} />);
    expect(document.querySelector('.cz-phaselabel')?.textContent).toMatch(/Prepare the four document sets|Submit for the format check/);
    expect(document.body.textContent).not.toMatch(/you have (completed|done)|marked as done/i);
  });
});

describe('compact and rich support really differ', () => {
  it('the compact Overview shows fewer scaffolds and fewer controls than the rich Guided view', () => {
    render(<GuidanceCard response={actionFacts('standard-synthetic-practice-v2')} emit={vi.fn()} />);
    const compactSupport = document.querySelectorAll('[data-support]').length, compactButtons = document.querySelectorAll('button').length;
    cleanup();
    render(<GuidanceCard response={actionFacts('preview-rich')} emit={vi.fn()} />);
    expect(document.querySelectorAll('[data-support]').length).toBeGreaterThan(compactSupport);
    expect(document.querySelectorAll('button').length).toBeGreaterThan(compactButtons);
    expect(screen.getByRole('group', { name: /Procedure map/ })).toBeTruthy();
  });

  it('opening More guidance reveals only the supplement and leaves the cards where they were', () => {
    const r = v31Combo('concise', 'on'), emit = vi.fn();
    const { rerender } = render(<GuidanceCard response={r} emit={emit} />);
    const before = rows(step('action:submit_application').querySelector('.cz-atstep')).join('|');
    fireEvent.click(step('action:submit_application').querySelector('button.cz-toggle')!);
    const open = structuredClone(r); open.interaction.explanation_open_action_ids = ['action:submit_application'];
    rerender(<GuidanceCard response={open} emit={emit} />);
    expect(rows(step('action:submit_application').querySelector('.cz-atstep')).join('|')).toBe(before);
    expect(step('action:submit_application').querySelectorAll('.cz-expl').length).toBe(1);
  });
});
