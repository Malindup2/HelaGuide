// @vitest-environment jsdom
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import GuidanceCard from '../card/GuidanceCard';
import { v31ParallelGuided } from './examples';

beforeAll(() => {
  vi.stubGlobal('IntersectionObserver', class { observe() {} unobserve() {} disconnect() {} });
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(cleanup);

describe('the verified relationship map (retained fictional parallel procedure, real captured response)', () => {
  it('draws exactly the verified actions, prerequisites and parallel group, with a text version of the same facts', () => {
    const r = v31ParallelGuided(), aid = r.document.relationship_aid;
    expect(r.document.configuration.relationships).toBe('map');
    expect(r.document.completeness.parallel_groups).toBe('complete');
    expect(aid.map).not.toBeNull();
    render(<GuidanceCard response={r} emit={vi.fn()} />);
    expect(screen.getByRole('group', { name: /Procedure map/ })).toBeTruthy();
    expect(document.querySelectorAll('.cz-node').length).toBe(r.document.actions.length);
    expect(document.querySelectorAll('.cz-edge').length).toBe(aid.map!.edges.length);
    expect(aid.map!.parallel.length).toBe(1);                                   // one stated parallel group, none invented
    expect(aid.map!.text_equivalent.some(t => t.startsWith('Verified parallel work'))).toBe(true);
    expect(screen.getByText('Text version of the map')).toBeTruthy();
  });
});
