// @vitest-environment jsdom
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { cleanup, render } from '@testing-library/react';
import GuidanceCard from '../card/GuidanceCard';
import { actionFacts } from './examples';

beforeAll(() => {
  vi.stubGlobal('IntersectionObserver', class { observe() {} unobserve() {} disconnect() {} });
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(cleanup);

const step = (id: string) => document.getElementById(`cz-step-${id}`)!;
const card = (id: string) => step(id).querySelector('.cz-atstep');
const tags = (el: Element | null) => [...(el?.querySelectorAll('.cz-tag') ?? [])].map(t => t.textContent ?? '');

describe('each step receives only the facts that belong to it', () => {
  it('practice: the submission step shows its own documents and desk, and no other step shows documents or charges', () => {
    const r = actionFacts('standard-synthetic-practice-v2');
    render(<GuidanceCard response={r} emit={vi.fn()} />);
    const submit = card('action:submit_application')!;
    expect(tags(submit).join(' ')).toContain('Fictional Submission Desk');
    expect(tags(submit).join(' ')).toContain('Fictional completed application form');
    expect(tags(submit).join(' ')).toContain('Fictional supporting copy');
    expect(submit.textContent).toContain('Submit');
    for (const id of ['action:register_application', 'action:prepare_form']) {
      const c = card(id);
      expect(c?.textContent ?? '').not.toMatch(/Bring|Submit|Pay|Charge|LKR/);
    }
    expect(tags(card('action:register_application')).join(' ')).toContain('Fictional Registration Desk');
    expect(card('action:prepare_form')).toBeNull();
  });

  it('negative: a stage-level fee is never placed inside any step and is listed exactly once overall', () => {
    for (const name of ['standard-synthetic-practice-v2', 'standard-synthetic-parallel-v1'] as const) {
      const r = actionFacts(name);
      render(<GuidanceCard response={r} emit={vi.fn()} />);
      expect(document.querySelectorAll('.cz-atstep .cz-fee').length).toBe(0);
      expect(r.document.actions.every(a => a.facts.every(f => f.fact.kind !== 'fee'))).toBe(true);
      expect(document.querySelectorAll('.cz-service .cz-fee').length).toBe(r.document.requirements.fees.length);
      expect(new Set(r.document.requirements.fees.map(f => f.fact_id)).size).toBe(r.document.requirements.fees.length);
      cleanup();
    }
  });

  it('a document shown at its step is not repeated in the whole-service strip', () => {
    const r = actionFacts('standard-synthetic-parallel-v1');
    render(<GuidanceCard response={r} emit={vi.fn()} />);
    const stepsWithRows = r.document.actions.filter(a => /Submit/.test(card(a.id)?.textContent ?? '')).map(a => a.id);
    expect(stepsWithRows).toEqual(['action:submit_application']);
    const strip = document.querySelector('.cz-service')!;
    expect(strip.textContent).not.toContain('Fictional supporting copy');
    expect(strip.textContent).not.toContain('Fictional completed application form');
    expect(strip.textContent).toMatch(/LKR 0/);
  });

  it('official procedures carry no action-level facts, destinations or step cards (source fallback)', () => {
    for (const name of ['standard-official-nic_amendment-v3', 'standard-official-birth_copy-v3'] as const) {
      const r = actionFacts(name);
      render(<GuidanceCard response={r} emit={vi.fn()} />);
      expect(document.querySelectorAll('.cz-atstep').length).toBe(0);
      expect(r.document.actions.every(a => a.facts.length === 0 && a.destination === null && a.actor === null)).toBe(true);
      cleanup();
    }
  });

  it('the step card stays visible and identical in all four Explanation x Disclosure combinations', () => {
    const seen = new Set<string>();
    for (const name of ['preview-concise-off', 'preview-concise-on', 'preview-detailed-off', 'preview-detailed-on'] as const) {
      const r = actionFacts(name);
      render(<GuidanceCard response={r} emit={vi.fn()} />);
      const submit = card('action:submit_application')!;
      expect(submit).toBeTruthy();
      expect(submit.closest('details')).toBeNull();
      seen.add(tags(submit).join('|'));
      cleanup();
    }
    expect(seen.size).toBe(1);
  });

  it('rich guided view keeps the active step card next to its instruction', () => {
    const r = actionFacts('preview-rich');
    r.interaction.navigation.active_action_id = 'action:submit_application';
    render(<GuidanceCard response={r} emit={vi.fn()} />);
    const focus = document.querySelector('.cz-focus')!;
    expect(focus.querySelector('.cz-atstep')?.textContent).toContain('Fictional Submission Desk');
    expect(focus.textContent).toContain(r.document.actions.find(a => a.id === 'action:submit_application')!.essential);
  });
});

describe('numbering never implies an execution order that the source does not state', () => {
  const labels = () => [...document.querySelectorAll('.cz-layerhead, .cz-mark')].map(e => e.textContent);

  it('a verified chain is numbered one step per layer (birth certificate copy)', () => {
    render(<GuidanceCard response={actionFacts('standard-official-birth_copy-v3')} emit={vi.fn()} />);
    expect(labels()).toEqual(expect.arrayContaining(['Step 1', 'Step 2']));
    expect(document.body.textContent).not.toMatch(/no fixed order/);
  });

  it('alternative routes are a choice, not consecutive steps (NIC amendment)', () => {
    render(<GuidanceCard response={actionFacts('standard-official-nic_amendment-v3')} emit={vi.fn()} />);
    expect(document.body.textContent).toContain('Which applies to you?');
    expect(labels().some(l => /^Step 2/.test(l ?? ''))).toBe(false);
  });

  it('parallel peers share one layer, carry letters and say there is no fixed order; the join step stands alone', () => {
    const r = actionFacts('standard-synthetic-parallel-v1');
    render(<GuidanceCard response={r} emit={vi.fn()} />);
    const heads = [...document.querySelectorAll('.cz-layerhead')].map(e => e.textContent ?? '');
    expect(heads.filter(h => /no fixed order/.test(h))).toHaveLength(1);
    const peers = r.document.actions.filter(a => ['action:prepare_form', 'action:prepare_copy'].includes(a.id));
    const marks = peers.map(a => document.getElementById(`cz-step-${a.id}`)!.querySelector('.cz-mark')?.textContent);
    expect(marks.sort()).toEqual(['2a', '2b']);
    expect(heads.some(h => /^Step 3$/.test(h.trim()))).toBe(true);
    expect(document.getElementById('cz-step-action:submit_application')!.querySelector('.cz-mark')).toBeNull();
  });
});
