// @vitest-environment jsdom
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { cleanup, render } from '@testing-library/react';
import GuidanceCard from '../card/GuidanceCard';
import { mainService } from './examples';

beforeAll(() => {
  vi.stubGlobal('IntersectionObserver', class { observe() {} unobserve() {} disconnect() {} });
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(cleanup);

type R = ReturnType<typeof mainService>;
const step = (id: string) => document.getElementById(`cz-step-${id}`)!;
const options = (r: R) => r.document.routes[0].options.map(o => ({ id: o.option_id, steps: o.action_ids, label: o.label }));
const choose = (r: R, optionId: string) => { r.interaction.route_choices = { [r.document.routes[0].branch_id]: [optionId] }; return r; };
const facts = (r: R, id: string) => r.document.actions.find(a => a.id === id)!.facts;

describe('Birth certificate copy: a counter application with a fee condition', () => {
  it('has two alternative fee cases, each with its own payment and submission, and a fee card only where the source gives one', () => {
    const r = mainService('standard-birth');
    expect(r.preparation.content_state).toBe('demo_accepted');
    const [known, search] = options(r);
    expect(known.steps.length).toBe(2); expect(search.steps.length).toBe(2);
    expect(r.document.actions.map(a => a.id)).toEqual(expect.arrayContaining(['action:form', 'action:complete', 'action:pay_known', 'action:pay_search', 'action:submit_known', 'action:submit_search']));
    expect(facts(r, 'action:pay_known').filter(f => f.fact.kind === 'fee').length).toBe(1);
    expect(facts(r, 'action:pay_search').filter(f => f.fact.kind === 'fee').length).toBe(0);
    const search1 = r.document.actions.find(a => a.id === 'action:pay_search')!;
    expect(search1.essential).toMatch(/Rs\. 250/);
  });

  it('shows the known-details route with its Rs. 120 card and the postal envelope as an optional document', () => {
    render(<GuidanceCard response={choose(mainService('standard-birth'), 'option:known')} emit={vi.fn()} />);
    const pay = step('action:pay_known');
    expect(pay.textContent).toMatch(/LKR 120/);
    expect(pay.textContent).toMatch(/ATM and online payments are not accepted/);
    expect(step('action:submit_known').textContent).toMatch(/Only if you want the copies sent by post/);
    expect(document.getElementById('cz-step-action:pay_search')).toBeNull();
  });
});

describe('step order follows the verified prerequisites', () => {
  it('birth: the form and the completed application come before the payment and submission choice', () => {
    render(<GuidanceCard response={choose(mainService('standard-birth'), 'option:known')} emit={vi.fn()} />);
    const order = [...document.querySelectorAll('.cz-step, .cz-route')].map(e => (e.classList.contains('cz-route') ? 'route' : e.id.replace('cz-step-action:', '')));
    expect(order.indexOf('complete')).toBeGreaterThan(order.indexOf('form'));
    expect(order.indexOf('route')).toBeGreaterThan(order.indexOf('complete'));
  });
});

describe('NIC amendment: preparation, extra evidence, two routes, and a card at the end of each', () => {
  it('lists the full essential procedure for both routes before a choice is made', () => {
    const r = mainService('standard-nic');
    const [estate, non] = options(r);
    expect([...estate.steps].sort()).toEqual(['action:estate_certify', 'action:estate_receive']);
    expect([...non.steps].sort()).toEqual(['action:ds_countersign', 'action:gn_certify', 'action:gn_receive']);
    render(<GuidanceCard response={r} emit={vi.fn()} />);
    const nonList = [...document.querySelectorAll('.cz-preview')].find(o => o.querySelectorAll('li').length === 3)!;
    expect([...nonList.querySelectorAll('li')].map(l => l.textContent)).toEqual(['Have it certified by your Grama Niladhari', "Divisional Secretary's countersignature", 'Receive your amended card']);   // the order the verified prerequisites give
    expect(step('action:docs_core')).toBeTruthy(); expect(step('action:docs_extra')).toBeTruthy();
    expect([...document.querySelectorAll('.cz-preview')].map(o => o.querySelectorAll('li').length).sort()).toEqual([2, 3]);
  });

  it('puts the Rs. 500 payment on the certification step of the chosen route and never on the route question or the countersignature', () => {
    render(<GuidanceCard response={choose(mainService('standard-nic'), 'option:non_estate')} emit={vi.fn()} />);
    expect(document.querySelector('[aria-label="Facts for this choice"]')).toBeNull();   // nothing is paid at the route question
    expect(step('action:gn_certify').textContent).toMatch(/Pay\s*LKR 500/);
    expect(step('action:gn_certify').textContent).toMatch(/adds Rs\. 120/);
    expect(step('action:ds_countersign').querySelector('.cz-fee')).toBeNull();
    expect(step('action:ds_countersign').textContent).toContain('Divisional Secretary');
  });

  it('shows each extra document next to the circumstance it belongs to', () => {
    render(<GuidanceCard response={mainService('standard-nic')} emit={vi.fn()} />);
    const items = [...step('action:docs_extra').querySelectorAll('.cz-item')];
    expect(items.length).toBe(6);
    expect(items.every(i => i.querySelector('.cz-qual'))).toBe(true);
    expect(items.map(i => i.textContent).join('|')).toMatch(/citizenship certificate.*born abroad/i);
  });
});

describe('TIN registration: conditional documents by applicant category', () => {
  it('has three categories, each with only its own documents and its own submission step', () => {
    const r = mainService('standard-tin');
    expect(options(r).length).toBe(3);
    const names = (id: string) => facts(r, id).map(f => (f.fact.kind === 'document' ? f.fact.name : '')).join('|');
    expect(names('action:individual_docs')).toMatch(/Proof of address/i);
    expect(names('action:individual_docs')).not.toMatch(/Articles|Form 20|partnership/i);
    expect(names('action:partnership_docs')).toMatch(/Partnership registration certificate/);
    expect(names('action:partnership_docs')).not.toMatch(/Articles|Form 20|utility/i);
    expect(names('action:company_docs')).toMatch(/Form 20s/);
    expect(names('action:company_docs')).not.toMatch(/utility|Partnership registration/i);
  });

  it('marks Form 13, Form 18 and the Board of Investment documents as conditional rather than universal', () => {
    render(<GuidanceCard response={choose(mainService('standard-tin'), 'option:c_company')} emit={vi.fn()} />);
    const items = [...step('action:company_docs').querySelectorAll('.cz-item')];
    for (const key of [/Form 13/, /Form 18/, /Board of Investment/]) {
      const item = items.find(i => key.test(i.textContent ?? ''));
      expect(item?.querySelector('.cz-qual')?.textContent).toMatch(/Only (if|where|for)/);
    }
    expect(step('action:company_submit').textContent).toMatch(/Charge\s*LKR 0/);
    expect(step('action:company_submit').textContent).toMatch(/older GIC service description/);
    expect(step('action:company_submit').textContent).toMatch(/IRD e-Services portal/);
  });

  it('does not tell every applicant to register for every tax type', () => {
    const r = mainService('preview-tin-detailed-off');
    for (const a of r.document.actions) expect(`${a.essential} ${a.explanation_visible ?? ''}`).not.toMatch(/(?<!not assume you )must register for (all|every)/i);
  });
});

describe('wording and presentation', () => {
  it.each(['birth', 'nic', 'tin'])('%s: Detailed is genuinely richer than Concise, and Disclosure only moves the supplement', key => {
    const pick = (e: string, d: string) => mainService(`preview-${key}-${e}-${d}`).document.actions;
    const co = pick('concise', 'off'), dof = pick('detailed', 'off'), con = pick('concise', 'on'), don = pick('detailed', 'on');
    const richer = co.filter((a, i) => dof[i].essential.length > a.essential.length * 1.3).length;
    expect(richer).toBeGreaterThanOrEqual(Math.ceil(co.length * 0.7));
    co.forEach((a, i) => {
      expect(con[i].essential).toBe(a.essential); expect(don[i].essential).toBe(dof[i].essential);
      expect(a.explanation_visible).toBeTruthy(); expect(con[i].explanation_visible).toBeFalsy(); expect(con[i].explanation_hidden).toBe(a.explanation_visible);
    });
  });

  it.each(['birth', 'nic', 'tin'])('%s: no developer, fictional or dataset-limitation wording in the citizen text', key => {
    for (const name of [`preview-${key}-concise-off`, `preview-${key}-detailed-off`]) {
      render(<GuidanceCard response={mainService(name)} emit={vi.fn()} />);
      expect(document.querySelector('.cz-provisional')).toBeNull();
      expect(document.body.textContent).not.toMatch(/fictional|this example|snapshot|no separate fee|not supplied|another step in the same route/i);
      cleanup();
    }
  });
});
