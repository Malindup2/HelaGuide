// @vitest-environment jsdom
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import GuidanceCard from '../card/GuidanceCard';
import type { Configuration, GuidanceResponse } from '../types';
import { birthStandard, nicStandard, practiceRich, practiceStd, practiceWithRecap } from './examples';

beforeAll(() => {
  vi.stubGlobal('IntersectionObserver', class { observe() {} unobserve() {} disconnect() {} });
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(cleanup);

const show = (response: GuidanceResponse, props: Partial<Parameters<typeof GuidanceCard>[0]> = {}) => {
  const emit = vi.fn();
  return { emit, ...render(<GuidanceCard response={response} emit={emit} {...props} />) };
};

/** Rebuilds a response the way the backend does for one depth/disclosure choice (test-only variation of captured data). */
function variant(explanation: Configuration['explanation'], disclosure: Configuration['disclosure'], navigation: Configuration['navigation'] = 'overview'): GuidanceResponse {
  const r = practiceRich();
  const config = { ...r.document.configuration, explanation, disclosure, navigation, recap: 'off', relationships: 'none', segmentation: 'off' } as Configuration;
  r.document.configuration = config; r.selection.configuration = config; r.document.relationship_aid = { mode: 'none', inline_by_action: {}, map: null, essential_relationships_remain_in_instructions: true };
  r.document.phases = []; r.interaction.recap.enabled = false; r.interaction.recap.items = [];
  for (const a of r.document.actions) {
    const text = a.explanation_hidden ?? a.explanation_visible;
    a.explanation_visible = disclosure === 'off' ? text : null; a.explanation_hidden = disclosure === 'on' ? text : null; a.disclosure_available = disclosure === 'on';
  }
  r.document.navigation.mode = navigation; r.interaction.navigation.mode = navigation;
  return r;
}
const registerText = (r: GuidanceResponse) => r.document.actions.find(a => a.id === 'action:register_application')!;

describe('standard guidance for a guest', () => {
  it('shows numbered layers, scoped documents and charges, and the source limit, with no support or feedback controls', () => {
    const r = birthStandard();
    show(r);
    expect(screen.getByText('Step 1')).toBeTruthy();
    expect(screen.getByText('Step 2')).toBeTruthy();
    expect(screen.getAllByText('Completed application').length).toBeGreaterThan(0);
    expect(screen.getAllByText('LKR 120').length).toBeGreaterThan(0);
    expect(screen.getByText('Standard guidance')).toBeTruthy();
    expect(screen.getByText(/not live or independently verified/)).toBeTruthy();
    expect(screen.queryByRole('button', { name: /Support/ })).toBeNull();
    expect(screen.queryByText(/Did this way of presenting/)).toBeNull();
  });

  it('states each instruction once: a fallback heading is not repeated by the essential text', () => {
    const r = birthStandard(), pay = r.document.actions.find(a => a.id === 'action:birth_pay')!;
    show(r);
    expect(screen.getAllByText(pay.heading)).toHaveLength(1);
    expect(screen.getAllByText(/does not describe the separate online application service/).length).toBeGreaterThan(0);
  });

  it('never shows a stage fee as a payment at a step', () => {
    show(practiceStd());
    expect(screen.getAllByText('LKR 0').length).toBeGreaterThanOrEqual(3);
    expect(screen.getAllByText(/Recorded for: /).length).toBeGreaterThan(0);
    expect(screen.queryByText(/^Pay$/)).toBeNull();
  });

  it('records exposure once per view and no visits on mount', () => {
    const r = practiceStd();
    const { emit } = show(r);
    const calls = emit.mock.calls.map(c => c[0]);
    expect(calls.filter(c => c.type === 'view_displayed')).toHaveLength(1);
    expect(calls.some(c => c.type === 'navigate' || c.type === 'step_open')).toBe(false);
  });

  it('records an explicit visit once when a step is engaged', () => {
    const r = birthStandard();
    const { emit } = show(r);
    const step = document.getElementById('cz-step-action:birth_submit')!;
    fireEvent.click(step); fireEvent.click(step);
    expect(emit.mock.calls.filter(c => c[0].type === 'step_open' && c[0].action_id === 'action:birth_submit')).toHaveLength(1);
  });
});

describe('route alternatives', () => {
  it('present a choice with the source conditions and no sequential numbering', () => {
    show(nicStandard());
    expect(screen.getByText('Which applies to you?')).toBeTruthy();
    expect(screen.getByText('The applicant is an estate resident seeking an NIC amendment.')).toBeTruthy();
    expect(screen.getByText('The applicant is not an estate resident and seeks an NIC amendment.')).toBeTruthy();
    expect(screen.queryByText('Step 2')).toBeNull();
    expect(screen.getByText('Choose the route that applies to see its steps in full.')).toBeTruthy();
  });

  it('only focuses a route and records route_focus, never a visit or eligibility', () => {
    const { emit } = show(nicStandard());
    fireEvent.click(screen.getAllByRole('button', { name: 'Show steps' })[0]);
    expect(emit).toHaveBeenCalledWith({ type: 'route_focus', branch_id: 'branch:nic_amendment', option_ids: ['option:estate'] });
    expect(emit.mock.calls.some(c => c[0].type === 'navigate' || c[0].type === 'step_open')).toBe(false);
  });

  it('shows the chosen route with a way to change it and keeps the other reachable', () => {
    const r = nicStandard();
    r.interaction.route_choices = { 'branch:nic_amendment': ['option:non_estate'] };
    for (const e of r.document.navigation.entries) if (e.option_id === 'option:estate') { e.layer = null; e.route_layer = null; }
    const { emit } = show(r);
    expect(screen.getByRole('button', { name: 'Showing' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Switch' }));
    expect(emit).toHaveBeenCalledWith({ type: 'route_focus', branch_id: 'branch:nic_amendment', option_ids: ['option:estate'] });
    fireEvent.click(screen.getByRole('button', { name: 'Change route' }));
    expect(emit).toHaveBeenCalledWith({ type: 'route_focus', branch_id: 'branch:nic_amendment', option_ids: [] });
    expect(screen.queryByText('Step 0')).toBeNull();
  });
});

describe('D1 Navigation: guided', () => {
  it('shows one step with position, phase orientation and Back/Next that record navigation', () => {
    const r = practiceRich();
    const { emit } = show(r);
    expect(screen.getByText(/Item 1 of 3 in browsing order/)).toBeTruthy();
    expect(screen.getByText('Open the application journey')).toBeTruthy();
    expect(screen.queryByRole('heading', { name: /Prepare the fictional application form after registration/ })).toBeNull();
    expect((screen.getByRole('button', { name: 'Back' }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    expect(emit).toHaveBeenCalledWith({ type: 'navigate', action_id: r.interaction.navigation.next_action_id });
  });

  it('offers a read-only overview peek that is recorded and changes no configuration', () => {
    const { emit } = show(practiceRich());
    fireEvent.click(screen.getByRole('button', { name: /Overview/ }));
    expect(emit).toHaveBeenCalledWith({ type: 'overview_peek' }, { refresh: false });
    expect(screen.getByText('A temporary look at every step. Your guided view and its settings stay as they are.')).toBeTruthy();
    expect(emit.mock.calls.some(c => c[0].type === 'adjust')).toBe(false);
  });
});

describe('D2 x D3: explanation depth and disclosure', () => {
  for (const explanation of ['concise', 'detailed'] as const) {
    it(`${explanation} + disclosure OFF shows the explanation normally with no show/hide control`, () => {
      const r = variant(explanation, 'off'), text = registerText(r).explanation_visible!;
      show(r);
      expect(screen.getByText(text.split('\n\n')[0])).toBeTruthy();
      expect(screen.queryByRole('button', { name: 'More' })).toBeNull();
      expect(screen.queryAllByText('In more detail').length > 0).toBe(explanation === 'detailed');
    });

    it(`${explanation} + disclosure ON keeps essentials visible and the remainder behind More/Less`, () => {
      const r = variant(explanation, 'on'), emit = vi.fn(), essentials = r.document.actions.map(x => x.essential).join(' ');
      const texts = r.document.actions.flatMap(x => x.explanation_hidden ? [x.explanation_hidden.split('\n\n')[0]] : []).filter(t => !essentials.includes(t));
      const shown = () => texts.filter(t => screen.queryAllByText(t).length > 0);
      const { rerender } = render(<GuidanceCard response={r} emit={emit} />);
      expect(screen.getAllByText(/\S/).length).toBeGreaterThan(0);
      expect(texts.length).toBeGreaterThan(0);
      expect(shown()).toHaveLength(0);
      fireEvent.click(screen.getAllByRole('button', { name: 'More' })[0]);
      expect(emit).toHaveBeenCalledWith({ type: 'explanation_open', action_id: expect.any(String) });
      const open = structuredClone(r); open.interaction.explanation_open_action_ids = r.document.actions.map(x => x.id);
      rerender(<GuidanceCard response={open} emit={emit} />);
      expect(shown().length).toBeGreaterThan(0);
      expect(screen.getAllByRole('button', { name: 'Less' }).length).toBeGreaterThan(0);
    });
  }

  it('keeps conditions and facts outside the disclosure', () => {
    const r = variant('detailed', 'on');
    const route = r.document.actions.find(a => a.id === 'action:obtain_copy')!;
    r.interaction.route_choices = { 'branch:copy_route': ['option:office'] };
    show(r);
    expect(screen.getAllByText('You do not have the fictional supporting copy.').length).toBeGreaterThan(0);
    expect(route.explanation_hidden).toBeTruthy();
  });
});

describe('D4 Relationships', () => {
  it('shows a compact map with hide, expand and a text version, recording map events', () => {
    const { emit } = show(practiceRich());
    expect(screen.getByRole('group', { name: /Procedure map/ })).toBeTruthy();
    expect(screen.getByText('Text version of the map')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /Expand/ }));
    expect(emit).toHaveBeenCalledWith({ type: 'map_expand' });
    expect(document.querySelector('dialog .cz-graph-large')).toBeTruthy();
    expect(screen.getByText('Text version')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Hide map' }));
    expect(emit).toHaveBeenCalledWith({ type: 'map_hide' });
  });

  it('renders inline cues from the backend with plain labels', () => {
    const r = practiceStd();
    r.document.configuration.relationships = 'inline'; r.document.relationship_aid = { mode: 'inline', map: null, essential_relationships_remain_in_instructions: true,
      inline_by_action: { 'action:submit_application': [{ kind: 'join', text: 'Before Submit: All of: Prepare the form; The applicable route', evidence_ids: [], relation_id: 'j' }] } };
    show(r);
    expect(screen.getByText('Also required')).toBeTruthy();
    expect(screen.getByText(/All of: Prepare the form; The applicable route/)).toBeTruthy();
  });
});

describe('D5 Recap', () => {
  it('renders only the backend reminders, as text, labelled as viewed and not done', () => {
    const r = practiceWithRecap();
    show(r);
    expect(screen.getByText(/Earlier steps you viewed \(1\)/)).toBeTruthy();
    expect(screen.getByText(r.interaction.recap.items[0].text)).toBeTruthy();
    expect(screen.getByText('Earlier guidance viewed, not confirmed as done')).toBeTruthy();
    expect(within(document.querySelector('.cz-recap') as HTMLElement).queryAllByRole('button')).toHaveLength(0);
  });

  it('shows nothing when the backend reports no qualifying earlier step', () => {
    const r = practiceRich();
    show(r);
    expect(screen.queryByText(/Earlier steps you viewed/)).toBeNull();
  });
});

describe('D6 Segmentation', () => {
  it('groups overview steps under reviewed phase headings without ordering them', () => {
    const r = practiceRich();
    const config = { ...r.document.configuration, navigation: 'overview' } as Configuration;
    r.document.configuration = config; r.selection.configuration = config; r.document.navigation.mode = 'overview';
    show(r);
    expect(screen.getByRole('heading', { name: 'Open the application journey' })).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'Prepare the required items' })).toBeTruthy();
    expect(screen.queryByText(/Phase 1/)).toBeNull();
  });

  it('shows no phase headings when Segmentation is off', () => {
    show(practiceStd());
    expect(screen.queryByRole('heading', { name: 'Prepare the required items' })).toBeNull();
  });
});

describe('origin, support and feedback', () => {
  it('labels preview, adjusted and standard views from the selection record', () => {
    const r = practiceRich();
    show(r); expect(screen.getByText('Research preview')).toBeTruthy(); cleanup();
    r.selection.kind = 'manual_adjustment'; r.parent_view_id = 'view:parent'; show(r); expect(screen.getByText('Adjusted by you')).toBeTruthy();
  });

  it('offers only feasible support values and asks for a child view with the full configuration', () => {
    const r = practiceRich(), adjust = vi.fn();
    for (const c of r.availability.candidates) if (c.configuration.recap === 'off') { c.feasible = false; c.reasons = ['recap:reviewed_reminders_missing']; }
    render(<GuidanceCard response={r} emit={vi.fn()} adjust={adjust} />);
    fireEvent.click(screen.getByRole('button', { name: /Support/ }));
    expect(within(document.querySelector('dialog') as HTMLElement).getAllByRole('button', { name: 'Off' }).some(b => (b as HTMLButtonElement).disabled)).toBe(true);
    const sheet = document.querySelector('dialog') as HTMLElement;
    fireEvent.click(within(sheet).getAllByRole('button', { name: 'Overview' }).find(b => !(b as HTMLButtonElement).disabled)!);
    expect(adjust).toHaveBeenCalledWith({ ...r.document.configuration, navigation: 'overview' });
  });

  it('shows no support control when the backend does not allow adjustment', () => {
    show(practiceStd());
    expect(screen.queryByRole('button', { name: /Support/ })).toBeNull();
  });

  it('labels preview feedback as a diagnostic and sends fit / does-not-fit with diagnostic reasons only', async () => {
    const rate = vi.fn().mockResolvedValue({}), r = practiceRich();
    render(<GuidanceCard response={r} emit={vi.fn()} rate={rate} research />);
    expect(screen.getByText('Did this way of presenting the guidance suit you?')).toBeTruthy();
    expect(screen.getByText(/Preview or adjusted-view diagnostic\. It does not train/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /Does not fit/ }));
    fireEvent.click(screen.getByLabelText('Too much explanation'));
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));
    await Promise.resolve();
    expect(rate).toHaveBeenCalledWith('does_not_fit', ['too_much_explanation']);
  });

  it('hides feedback for previews outside research view and never for guests', () => {
    show(practiceRich()); expect(screen.queryByText(/Did this way of presenting/)).toBeNull(); cleanup();
    show(birthStandard(), { rate: vi.fn(), research: true }); expect(screen.queryByText(/Did this way of presenting/)).toBeNull();
  });
});

describe('sources and scope', () => {
  it('describes fictional wording as AI-assisted author review and denies independent validation', () => {
    show(practiceRich());
    fireEvent.click(screen.getByRole('button', { name: /Sources/ }));
    expect(screen.getByText(/internal, AI-assisted author review/)).toBeTruthy();
    expect(screen.getByText(/No independent or government validation/)).toBeTruthy();
  });

  it('does not present a bounded snapshot as live or verified', () => {
    show(birthStandard());
    fireEvent.click(screen.getByRole('button', { name: /Sources/ }));
    expect(screen.getByText(/No reviewed explanation has been published/)).toBeTruthy();
    expect(screen.getByText(/not independently validated/)).toBeTruthy();
  });
});

describe('read-only views', () => {
  it('keep every interaction local and send nothing', () => {
    const r = practiceRich(), emit = vi.fn();
    render(<GuidanceCard response={r} emit={emit} readOnly />);
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    expect(screen.getAllByText(/Item 2 of 3/).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', { name: 'Hide map' }));
    expect(emit).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: /Support/ })).toBeNull();
    expect(screen.queryByText(/Did this way of presenting/)).toBeNull();
  });
});
