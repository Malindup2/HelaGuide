import { describe, expect, it } from 'vitest';
import fixture from './fixture.json';
import type { Configuration, Journey } from './types';
import { actionMarks, activeSupports, agencies, browsingList, diffConfigurations, displayTitle, factActions, feedbackNote, groupFacts, originOf, presentationCounts, unavailableStates } from './presentation';

const base: Configuration = { navigation: 'overview', explanation: 'concise', disclosure: 'collapsed', relationships: 'none', recap: 'off', summary: 'off' };
const journey = () => structuredClone(fixture) as unknown as Journey;

describe('presentation helpers', () => {
  it('labels the origin only from backend routing and the view lineage', () => {
    const j = journey();
    expect(originOf(j)).toBe('standard');
    j.routing = 'adaptive';
    expect(originOf(j)).toBe('personalised');
    j.views.child = { id: 'child', parent: j.root_view, configuration: base, displayed: [], rating: null };
    j.current_view = 'child';
    expect(originOf(j)).toBe('adjusted');
    j.routing = 'standard';
    expect(originOf(j)).toBe('adjusted');
  });

  it('lists only supports that add an aid, never inventing any', () => {
    expect(activeSupports(base)).toEqual([]);
    expect(activeSupports({ ...base, navigation: 'guided', relationships: 'map', summary: 'on' }).map(s => s.dimension)).toEqual(['navigation', 'relationships', 'summary']);
  });

  it('diffs configurations dimension by dimension', () => {
    const diff = diffConfigurations(base, { ...base, recap: 'on' });
    expect(diff.filter(d => !d.same).map(d => d.dimension)).toEqual(['recap']);
    expect(diffConfigurations(base, base).every(d => d.same)).toBe(true);
  });

  it('counts only what the real document and configuration show', () => {
    const doc = journey().document;
    expect(presentationCounts(doc, base)).toMatchObject({ actionsVisible: doc.actions.length, optionalOpen: 0, relationshipCues: 0 });
    expect(presentationCounts(doc, { ...base, navigation: 'guided', relationships: 'inline' })).toMatchObject({ actionsVisible: 1, relationshipCues: doc.edges.length + doc.joins.length });
  });

  it('reports states the procedure cannot offer, with the backend reason', () => {
    const doc = journey().document;
    doc.capabilities.explanation = { states: ['concise'], applicable: true, reason: 'expanded requires reviewed full coverage variants' };
    expect(unavailableStates(doc)).toContainEqual({ dimension: 'explanation', state: 'expanded', reason: 'expanded requires reviewed full coverage variants' });
  });

  it('keeps a focused exclusive route out of the browsing list but never an AND group', () => {
    const j = journey(), branch = j.document.branches[0];
    j.focused_routes = { [branch.group_id]: branch.options[0].option_id };
    const ids = browsingList(j).map(a => a.id);
    expect(ids).toContain(branch.options[0].action_ids[0]);
    expect(ids).not.toContain(branch.options[1].action_ids[0]);
    branch.selection = 'AND';
    expect(browsingList(j).map(a => a.id)).toContain(branch.options[1].action_ids[0]);
  });

  it('scopes a stage fee to the actions of its own stage and lists the service agency once', () => {
    const doc = journey().document;
    const fee = doc.facts.find(f => f.kind === 'fee')!;
    for (const a of factActions(doc, fee)) expect(doc.stages.find(s => s.fee_fact_id === fee.fact_id)?.service_id).toBe(a.service_id);
    expect(agencies(doc)).toEqual(['Fictional C4 Demo Office']);
  });

  describe('route marks', () => {
    it('never numbers actions as a sequence and marks mutually exclusive routes by option', () => {
      const doc = journey().document, marks = actionMarks(doc);
      const route = doc.actions.filter(a => a.branch);
      expect(route.map(a => marks.get(a.id)!.label)).toEqual(['A', 'B']);
      expect(route.map(a => marks.get(a.id)!.note)).toEqual(['Route A · choose one', 'Route B · choose one']);
      for (const m of marks.values()) expect(m.label).not.toMatch(/^\d+$/);
      expect(doc.actions.filter(a => !a.branch).every(a => marks.get(a.id)!.kind === 'common')).toBe(true);
    });
    it('distinguishes joint and optional groups from exclusive routes', () => {
      const doc = journey().document;
      doc.branches[0].selection = 'AND';
      expect(actionMarks(doc).get(doc.branches[0].options[0].action_ids[0])).toMatchObject({ kind: 'joint' });
      doc.branches[0].selection = 'OR';
      expect(actionMarks(doc).get(doc.branches[0].options[0].action_ids[0])).toMatchObject({ kind: 'optional' });
    });
  });

  describe('requirement groups', () => {
    it('lists each fact once and keeps route alternatives apart', () => {
      const doc = journey().document, g = groupFacts(doc);
      expect(new Set(g.always.map(e => e.fact.fact_id)).size).toBe(g.always.length);
      const copy = g.always.find(e => e.fact.fact_id === 'svc:demo_submission:document:copy')!;
      expect(copy.always.map(a => a.id)).toEqual(['action:submit_application']);
      expect(copy.routes.map(a => a.id).sort()).toEqual(['action:obtain_copy', 'action:prepare_copy']);
    });
    it('groups a document needed only by alternative routes under each route condition, never merged', () => {
      const doc = journey().document;
      doc.actions.find(a => a.id === 'action:submit_application')!.fact_ids = ['svc:demo_submission:document:form'];
      const g = groupFacts(doc);
      expect(g.always.some(e => e.fact.fact_id === 'svc:demo_submission:document:copy')).toBe(false);
      expect(g.conditional.map(c => c.key).sort()).toEqual(['You already have the fictional supporting copy.', 'You do not have the fictional supporting copy.']);
      for (const c of g.conditional) expect(c.entries).toHaveLength(1);
    });
    it('treats facts with no supplied action link as service-level, not as unconditional action requirements', () => {
      const doc = journey().document;
      for (const a of doc.actions) a.fact_ids = a.fact_ids.filter(id => id !== 'svc:demo_submission:fee');
      expect(groupFacts(doc).service.map(f => f.fact_id)).toContain('svc:demo_submission:fee');
    });
  });

  describe('titles', () => {
    const truncated = () => {
      const a = structuredClone(journey().document.actions[0]);
      a.concise = 'Only if counter collection is chosen: after completing registration, present the fictional registration reference at the counter. Then wait.';
      a.title = a.concise.split('. ')[0].slice(0, 115).replace(/\.$/, '');
      a.wording_status = { title: 'source_excerpt', instructions: 'source_preserving' };
      return a;
    };
    it('shows the complete source sentence instead of a title cut mid-phrase', () => {
      const a = truncated();
      expect(a.title.endsWith('reference a')).toBe(true);
      expect(displayTitle(a)).toBe('Only if counter collection is chosen: after completing registration, present the fictional registration reference at the counter');
    });
    it('leaves reviewed, prepared and already-complete titles exactly as supplied', () => {
      const a = truncated();
      expect(displayTitle({ ...a, wording_status: { title: 'v2_variant', instructions: 'v2_variant' } })).toBe(a.title);
      expect(displayTitle({ ...a, wording_status: { title: 'prepared_demo', instructions: 'source_preserving' } })).toBe(a.title);
      expect(displayTitle({ ...a, title: 'A short reviewed heading' })).toBe('A short reviewed heading');
      expect(displayTitle({ ...a, concise: 'Pay the fee.', title: 'Pay the fee' })).toBe('Pay the fee');
    });
  });

  it('words feedback by origin without claiming guest or adjusted answers train anything', () => {
    expect(feedbackNote('standard')).toContain('does not change the guidance shown to you or anyone else');
    expect(feedbackNote('adjusted')).toContain('does not change which layout is selected for you');
    expect(feedbackNote('personalised')).toContain('may be used');
    expect(feedbackNote('standard')).not.toMatch(/train|learn/i);
  });
});
