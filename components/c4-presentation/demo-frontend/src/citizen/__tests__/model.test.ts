import { describe, expect, it } from 'vitest';
import { allowedValues, byId, cueView, headingOf, layerMap, layersOf, originOf, paragraphs, phaseGroups, procedureFacts, reasonText, scopeNote } from '../model';
import { birthStandard, companyStandard, nicStandard, practiceRich, practiceStd } from './examples';

describe('layers come from verified prerequisites and never imply more than the backend states', () => {
  it('numbers a verified chain (birth certificate: pay, then submit)', () => {
    const layers = layersOf(birthStandard().document);
    expect(layers.map(l => l.layer)).toEqual([1, 2]);
    expect(layers.map(l => l.peers.map(a => a.id))).toEqual([['action:birth_pay'], ['action:birth_submit']]);
  });

  it('keeps unordered siblings in one layer so no order is invented among them (company documents)', () => {
    const layers = layersOf(companyStandard().document);
    expect(layers.map(l => l.peers.length)).toEqual([4, 1]);
    expect(layers[0].peers.map(a => a.id)).not.toContain('action:company_check');
  });

  it('places a route group as one choice at the layer of its first action, not as steps', () => {
    const doc = nicStandard().document, layers = layersOf(doc);
    expect(layers).toHaveLength(1);
    expect(layers[0].peers).toEqual([]);
    expect(layers[0].routes.map(r => r.branch_id)).toEqual(['branch:nic_amendment']);
  });

  it('does not produce "Step 0" once a route is chosen and the other route has no layer', () => {
    const doc = nicStandard().document;
    for (const e of doc.navigation.entries) if (e.option_id === 'option:estate') { e.layer = null; e.route_layer = null; }
    expect(layersOf(doc).map(l => l.layer)).toEqual([1]);
    expect(layerMap(doc, doc.relationship_aid.map?.edges ?? doc.navigation.entries.map(() => ({ source_id: 'x', target_id: 'y' })).slice(0, 0)).get('action:nic_estate')).toBe(1);
  });

  it('puts the preparation peer and the copy route together in layer 2 for the practice procedure', () => {
    const l2 = layersOf(practiceStd().document).find(l => l.layer === 2)!;
    expect(l2.peers.map(a => a.id)).toEqual(['action:prepare_form']);
    expect(l2.routes.map(r => r.branch_id)).toEqual(['branch:copy_route']);
  });
});

describe('source text handling', () => {
  it('also drops a paragraph that is only the opening sentence of the source limitation', () => {
    const doc = nicStandard().document, gn = byId(doc, 'action:nic_gn')!;
    const opening = doc.source_limit.split(/(?<=\.)\s/)[0];
    expect(opening.length).toBeGreaterThan(40);
    expect(paragraphs(`${gn.heading.split('\n\n')[0]}\n\n${opening}`, doc.source_limit)).toEqual([gn.heading.split('\n\n')[0]]);
  });

  it('shows the source limitation once instead of repeating it inside an action', () => {
    const doc = nicStandard().document, ds = byId(doc, 'action:nic_ds')!;
    expect(paragraphs(ds.essential, doc.source_limit).join('\n')).not.toContain('Manually curated official-source snapshot');
    expect(headingOf(ds, doc.source_limit)).toBe(ds.heading.split('\n\n')[0]);
    expect(headingOf(ds, doc.source_limit)).not.toContain('Manually curated');
  });
});

describe('facts keep their backend scope', () => {
  it('lists every fact the actions do not carry exactly once', () => {
    const doc = practiceStd().document, f = procedureFacts(doc);
    expect(f.documents.map(x => x.fact_id).sort()).toEqual(['svc:demo_submission:document:copy', 'svc:demo_submission:document:form']);
    expect(f.fees).toHaveLength(3);
    expect(new Set(f.fees.map(x => x.id)).size).toBe(3);
    expect(f.fees.every(x => x.scope === 'stage')).toBe(true);
  });

  it('names the stage for a stage fee only when the procedure has several stages', () => {
    const multi = practiceStd().document, single = birthStandard().document;
    expect(scopeNote(multi, multi.requirements.fees[0])).toMatch(/^For: /);
    expect(scopeNote(single, single.requirements.fees[0])).toBeNull();
  });
});

describe('segmentation and relationship cues', () => {
  it('has no phases when Segmentation is off and unordered phases when it is on without a phase order', () => {
    expect(phaseGroups(practiceStd().document)).toBeNull();
    const groups = phaseGroups(practiceRich().document)!;
    expect(groups.map(g => g.label)).toContain('Open the application journey');
    expect(groups.every(g => !g.ordered)).toBe(true);
  });

  it('turns backend cues into plain labels without dropping their text', () => {
    expect(cueView({ kind: 'before', text: 'Before this: Register', evidence_ids: [], relation_id: 'a' })).toEqual({ label: 'Before this', body: 'Register' });
    expect(cueView({ kind: 'join', text: 'Before Submit: All of: A; B', evidence_ids: [], relation_id: 'b' })).toEqual({ label: 'Also required', body: 'All of: A; B' });
    expect(cueView({ kind: 'parallel_area', text: 'These verified work areas may proceed independently: A; B', evidence_ids: [], relation_id: 'c' }).body).toBe('A; B');
  });
});

describe('origin and feasibility', () => {
  it('labels the origin from the backend selection only', () => {
    const r = practiceRich();
    expect(originOf(r)).toMatchObject({ kind: 'preview', label: 'Research preview' });
    r.selection.kind = 'manual_adjustment'; expect(originOf(r).label).toBe('Adjusted by you');
    r.selection.kind = 'shared_gaussian_lints'; expect(originOf(r).label).toBe('Selected for you');
    r.selection.kind = 'standard'; expect(originOf(r).label).toBe('Standard guidance');
  });

  it('offers only values the backend marks feasible and explains the rest', () => {
    const r = nicStandard(), values = allowedValues(r.availability, r.document.configuration, 'explanation');
    expect(values.find(v => v.value === 'concise')!.feasible).toBe(true);
    const detailed = values.find(v => v.value === 'detailed')!;
    expect(detailed.feasible).toBe(false);
    expect(reasonText(detailed.reason!)).toMatch(/no reviewed detailed explanation/);
  });
});
