// @vitest-environment jsdom
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import fixture from './fixture.json';
import GuidanceMessage from './GuidanceMessage';
import ComparisonSheet from './compare/ComparisonSheet';
import type { Configuration, Journey, Receipt } from './types';

const base: Configuration = { navigation: 'overview', explanation: 'concise', disclosure: 'collapsed', relationships: 'none', recap: 'off', summary: 'off' };
function journey(config: Partial<Configuration> = {}, routing: Journey['routing'] = 'standard'): Journey {
  const j = structuredClone(fixture) as unknown as Journey;
  j.routing = routing;
  j.views[j.current_view].configuration = { ...base, ...config };
  j.views[j.current_view].displayed = [j.document.actions[0].id];
  return j;
}
const receipt: Receipt = { rating: 'need_more', reward: null, eligible: false, posterior_revision: 1, exclusion_reason: 'standard_guidance' };

beforeAll(() => {
  vi.stubGlobal('IntersectionObserver', class { observe() {} unobserve() {} disconnect() {} });
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(cleanup);

describe('guidance interactions', () => {
  it('moves focus to the new action heading in guided navigation and records a navigate event', () => {
    const event = vi.fn();
    render(<GuidanceMessage journey={journey({ navigation: 'guided' })} event={event} adjust={vi.fn()} rate={vi.fn()} />);
    fireEvent.click(screen.getAllByRole('button', { name: 'Next' })[0]);
    const heading = document.activeElement as HTMLElement;
    expect(heading.tagName).toBe('H3');
    expect(heading.textContent).toContain(journey().document.actions[1].title);
    expect(event).toHaveBeenCalledWith({ type: 'navigate', action_id: journey().document.actions[1].id });
  });

  it('sends exactly the chosen backend rating value after an explicit send', async () => {
    const rate = vi.fn().mockResolvedValue(receipt);
    render(<GuidanceMessage journey={journey()} event={vi.fn()} adjust={vi.fn()} rate={rate} />);
    const send = screen.getByRole('button', { name: 'Send feedback' });
    expect((send as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByLabelText(/I needed more help/));
    fireEvent.click(send);
    await waitFor(() => expect(rate).toHaveBeenCalledWith('need_more'));
    expect(rate).toHaveBeenCalledTimes(1);
    expect((await screen.findByRole('status')).textContent).toContain('Your answer is saved with this view.');
    expect(screen.queryByText(/no policy update/i)).toBeNull();
  });

  it('explains why feedback is unavailable before the guidance has been shown', () => {
    const j = journey(); j.views[j.current_view].displayed = [];
    render(<GuidanceMessage journey={j} event={vi.fn()} adjust={vi.fn()} rate={vi.fn()} />);
    expect(screen.getByText('Available once the guidance has been on screen.')).toBeTruthy();
  });

  it('keeps technical eligibility wording out of the citizen view but shows it in research view', async () => {
    const rate = vi.fn().mockResolvedValue(receipt);
    render(<GuidanceMessage journey={journey()} event={vi.fn()} adjust={vi.fn()} rate={rate} research />);
    fireEvent.click(screen.getByLabelText(/I needed more help/));
    fireEvent.click(screen.getByRole('button', { name: 'Send feedback' }));
    expect(await screen.findByText(/Standard guidance: recorded, no policy update/)).toBeTruthy();
  });

  it('emits no events, adjustments or ratings from a read-only view', () => {
    const event = vi.fn(), adjust = vi.fn(), rate = vi.fn();
    render(<GuidanceMessage journey={journey({ navigation: 'guided', recap: 'on' })} event={event} adjust={adjust} rate={rate} readOnly />);
    fireEvent.click(screen.getAllByRole('button', { name: 'Next' })[0]);
    expect(event).not.toHaveBeenCalled(); expect(adjust).not.toHaveBeenCalled(); expect(rate).not.toHaveBeenCalled();
    expect(screen.queryByText('Was this the right amount of guidance?')).toBeNull();
    expect(screen.queryByText('Adjust support for this visit')).toBeNull();
    expect(screen.getByText(/Earlier in this journey/)).toBeTruthy();
  });

  it('changes support through the labelled controls using the same adjustment call', () => {
    const adjust = vi.fn();
    render(<GuidanceMessage journey={journey()} event={vi.fn()} adjust={adjust} rate={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Guided' }));
    expect(adjust).toHaveBeenCalledWith({ ...base, navigation: 'guided' });
  });

  it('only offers the comparison link when it is supplied and the view is not read-only', () => {
    const { rerender } = render(<GuidanceMessage journey={journey({}, 'adaptive')} event={vi.fn()} adjust={vi.fn()} rate={vi.fn()} />);
    expect(screen.queryByText('Compare with standard guidance')).toBeNull();
    rerender(<GuidanceMessage journey={journey({}, 'adaptive')} event={vi.fn()} adjust={vi.fn()} rate={vi.fn()} onCompare={vi.fn()} />);
    expect(screen.getByText('Compare with standard guidance')).toBeTruthy();
  });
});

describe('corrected behaviour', () => {
  const recapJourney = () => {
    const j = journey({ recap: 'on' }), actions = j.document.actions;
    j.focus = actions.at(-1)!.id; j.seen = actions.map(a => a.id);
    return j;
  };
  const openRecap = () => {
    const details = screen.getByText(/Earlier in this journey/).closest('details')!;
    details.open = true; fireEvent(details, new Event('toggle'));
    return details;
  };

  it('keeps recap_open as an explicit user interaction: not on render, once on opening, not on closing', () => {
    const j = recapJourney(), event = vi.fn();
    render(<GuidanceMessage journey={j} event={event} adjust={vi.fn()} rate={vi.fn()} />);
    expect(event).not.toHaveBeenCalledWith(expect.objectContaining({ type: 'recap_open' }));
    const details = openRecap();
    expect(event.mock.calls.filter(c => c[0].type === 'recap_open')).toEqual([[{ type: 'recap_open', action_id: j.focus }]]);
    details.open = false; fireEvent(details, new Event('toggle'));
    expect(event.mock.calls.filter(c => c[0].type === 'recap_open')).toHaveLength(1);
  });

  it('never records recap_open from a read-only view', () => {
    const event = vi.fn();
    render(<GuidanceMessage journey={recapJourney()} event={event} adjust={vi.fn()} rate={vi.fn()} readOnly />);
    openRecap();
    expect(event).not.toHaveBeenCalled();
  });

  it('tells people before they rate whether the answer can change what they are shown', () => {
    const standard = render(<GuidanceMessage journey={journey()} event={vi.fn()} adjust={vi.fn()} rate={vi.fn()} />);
    expect(screen.getByText(/does not change the guidance shown to you or anyone else/)).toBeTruthy();
    expect(screen.queryByText(/train/i)).toBeNull();
    standard.unmount();
    const adaptive = render(<GuidanceMessage journey={journey({}, 'adaptive')} event={vi.fn()} adjust={vi.fn()} rate={vi.fn()} />);
    expect(screen.getByText(/may be used to improve how support is chosen/)).toBeTruthy();
    adaptive.unmount();
    const j = journey({}, 'adaptive'); j.views.child = { id: 'child', parent: j.root_view, configuration: base, displayed: [j.document.actions[0].id], rating: null }; j.current_view = 'child';
    render(<GuidanceMessage journey={j} event={vi.fn()} adjust={vi.fn()} rate={vi.fn()} />);
    expect(screen.getByText(/does not change which layout is selected for you/)).toBeTruthy();
  });

  it('keeps the preparation tick-list local: no event, no request, and no completion wording', () => {
    const event = vi.fn(), adjust = vi.fn(), rate = vi.fn();
    render(<GuidanceMessage journey={journey({ summary: 'on' })} event={event} adjust={adjust} rate={rate} />);
    const box = screen.getAllByRole('checkbox')[0] as HTMLInputElement;
    fireEvent.click(box);
    expect(box.checked).toBe(true);
    expect(event).not.toHaveBeenCalled(); expect(adjust).not.toHaveBeenCalled(); expect(rate).not.toHaveBeenCalled();
    expect(screen.getByText(/does not confirm that anything is prepared or done/)).toBeTruthy();
  });

  it('describes guided position as browsing order and names alternative routes separately', () => {
    render(<GuidanceMessage journey={journey({ navigation: 'guided' })} event={vi.fn()} adjust={vi.fn()} rate={vi.fn()} />);
    expect(screen.getByText(/Browsing position 1 of 5/)).toBeTruthy();
    expect(screen.getByText(/Alternative routes are listed separately; follow only the one that applies/)).toBeTruthy();
    expect(screen.getAllByTitle(/Obtain a copy at the Records Desk/).length).toBeGreaterThan(0);
  });
});

describe('comparison sheet', () => {
  it('creates nothing until the person explicitly agrees', () => {
    const request = vi.fn();
    const onClose = vi.fn();
    render(<ComparisonSheet original={journey({ navigation: 'guided' }, 'adaptive')} sessionId="profile:s" research={false} request={request} onClose={onClose} />);
    expect(screen.getByText(/does not change your profile, your original guidance, your ratings or the learning state/)).toBeTruthy();
    expect(request).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onClose).toHaveBeenCalled();
    expect(request).not.toHaveBeenCalled();
  });

  it('shows the real difference between the standard and the selected configuration', async () => {
    const original = journey({ navigation: 'guided', summary: 'on' }, 'adaptive');
    const standard = { ...journey({}, 'standard'), id: 'journey-standard', token: 'tok' };
    const request = vi.fn(async (path: string) => {
      if (path === '/v2/policy') return { posterior_revision: 1, posterior_fingerprint: 'f' };
      if (path === '/dev/v1/sessions') return { session_id: 'guest:x' };
      if (path.endsWith('/settings')) return { session: { settings: { accessibility: { allow_relationship_visuals: true, allow_collapsed_content: true, allow_guided_navigation: true } } }, locks: {}, settings_revision: 1 };
      if (path.endsWith('/guidance')) return standard;
      throw new Error(path);
    }) as unknown as Parameters<typeof ComparisonSheet>[0]['request'];
    render(<ComparisonSheet original={original} sessionId="profile:s" research request={request} onClose={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Create comparison' }));
    expect(await screen.findByText('2 of 6 supports differ. Choose a row to highlight where it appears in both views.')).toBeTruthy();
    expect(screen.getByRole('region', { name: 'Standard guidance' })).toBeTruthy();
    expect(screen.getByText(/fingerprint unchanged/)).toBeTruthy();
  });
});
