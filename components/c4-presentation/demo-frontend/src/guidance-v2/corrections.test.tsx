import { describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import fixture from './fixture.json';
import GuidanceMessage, { PreparationSummary } from './GuidanceMessage';
import type { Configuration, Journey } from './types';

const base: Configuration = { navigation: 'overview', explanation: 'concise', disclosure: 'collapsed', relationships: 'none', recap: 'off', summary: 'off' };
const journey = (config: Partial<Configuration> = {}) => {
  const j = structuredClone(fixture) as unknown as Journey;
  j.views[j.current_view].configuration = { ...base, ...config };
  return j;
};
const html = (j: Journey) => renderToStaticMarkup(<GuidanceMessage journey={j} event={vi.fn()} adjust={vi.fn()} rate={vi.fn()} />);

describe('alternative routes and the path', () => {
  it('marks alternatives as routes with their condition instead of consecutive numbered steps', () => {
    const out = html(journey());
    expect(out).toContain('Route A · choose one');
    expect(out).toContain('Route B · choose one');
    expect(out).not.toMatch(/class="v2-num[^"]*"[^>]*>\d+</);
    expect(out).toContain('You do not have the fictional supporting copy');
    expect(out).toContain('You already have the fictional supporting copy');
  });

  it('keeps actual prerequisites separate from route alternatives', () => {
    const out = html(journey());
    expect(out).toContain('<strong>Do first:</strong>');
    expect(out).toContain('Choose the route that applies');
  });

  it('shows a truncated source-excerpt title as the complete source sentence in the path, stepper and map', () => {
    for (const config of [{}, { navigation: 'guided' as const }, { relationships: 'map' as const }]) {
      const j = journey(config), a = j.document.actions[0];
      a.concise = 'Only if counter collection is chosen: after completing registration, present the fictional registration reference at the counter. Then wait.';
      a.title = a.concise.split('. ')[0].slice(0, 115);
      a.wording_status = { title: 'source_excerpt', instructions: 'source_preserving' };
      j.focus = a.id;
      const out = html(j);
      expect(out).not.toMatch(/reference a</);
      expect(out).toContain('present the fictional registration reference at the counter');
    }
  });
});

describe('preparation summary', () => {
  it('separates unconditional requirements from route-dependent documents and lists each charge once', () => {
    const doc = journey().document, out = renderToStaticMarkup(<PreparationSummary doc={doc} />);
    expect(out).toContain('Needed in every case');
    const fee = doc.facts.find(f => f.kind === 'fee' && doc.actions.some(a => a.fact_ids.includes(f.fact_id)))!;
    const label = `${doc.stages.find(s => s.fee_fact_id === fee.fact_id)!.name}: ${fee.currency} ${fee.value}`;
    expect(out.split(label).length - 1).toBe(1);
    expect(out).toContain('Route-dependent: if You do not have the fictional supporting copy., Obtain a copy at the Records Desk');
    expect(out).toContain('Route-dependent: if You already have the fictional supporting copy., Prepare your existing copy');
    expect(out).not.toContain('Obtain a copy at the Records Desk (You do not have the fictional supporting copy.); Prepare');
  });

  it('puts a document needed only by alternatives under separate route conditions', () => {
    const doc = journey().document;
    doc.actions.find(a => a.id === 'action:submit_application')!.fact_ids = ['svc:demo_submission:document:form'];
    const out = renderToStaticMarkup(<PreparationSummary doc={doc} />);
    expect(out).toContain('Only if: You do not have the fictional supporting copy.');
    expect(out).toContain('Only if: You already have the fictional supporting copy.');
  });

  it('keeps the source qualification for charges that no action carries', () => {
    const out = renderToStaticMarkup(<PreparationSummary doc={journey().document} />);
    expect(out).toContain('Service-level charge; no action-level fee inferred.');
    expect(out).toContain('Not tied to a specific action');
  });

  it('describes the tick-list as the reader\'s own reference and never as confirmation', () => {
    const out = renderToStaticMarkup(<PreparationSummary doc={journey().document} checklist />);
    expect(out).toContain('does not confirm that anything is prepared or done');
    expect(out).not.toMatch(/mark (it )?(as )?(done|complete)|you have prepared|ready to submit/i);
  });
});
