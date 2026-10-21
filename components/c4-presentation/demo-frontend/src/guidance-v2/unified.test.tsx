import {describe,it,expect,vi} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import VersionRoute from './VersionRoute';
import GuidanceMessage,{PreparationSummary} from './GuidanceMessage';
import fixture from './fixture.json';
import type {Journey} from './types';
import {previousActions} from './semantics';

describe('Integrated citizen and research routing',()=>{
 it('mounts the original professional identity workspace as the citizen entry',()=>{
  const html=renderToStaticMarkup(<VersionRoute/>);
  expect(html).toContain('Continue as guest');expect(html).toContain('Create demo profile');
  expect(html).not.toContain('C4 V2 research workspace');
 });
 it('keeps explicit support adjustments compact and exposes an enlargeable map',()=>{
  const j=structuredClone(fixture) as unknown as Journey;j.views[j.current_view].configuration.relationships='map';
  const html=renderToStaticMarkup(<GuidanceMessage journey={j} event={vi.fn()} adjust={vi.fn()} rate={vi.fn()}/>);
  expect(html).toContain('<details class="v2-adjustments"><summary>Adjust support for this visit</summary>');
  expect(html).toContain('Enlarge map');expect(html).toContain('Hide map');
 });
 it('keeps previously viewed earlier actions in recap after revisiting a later step',()=>{
  const j=structuredClone(fixture) as unknown as Journey;const actions=j.document.actions;
  j.seen=[actions[4].id,actions[0].id,actions[3].id];
  expect(previousActions(j,actions[4].id).map(a=>a.id)).toEqual([actions[0].id,actions[3].id]);
 });
 it('preserves supplied stage dependencies and parallel work even without additional relationship aids',()=>{
  const j=structuredClone(fixture) as unknown as Journey;j.views[j.current_view].configuration.relationships='none';
  const html=renderToStaticMarkup(<GuidanceMessage journey={j} event={vi.fn()} adjust={vi.fn()} rate={vi.fn()}/>);
  expect(html).toContain('Service-level dependencies');expect(html).toContain('Explicit parallel work areas');
  expect(html).not.toContain('aria-label="Integrated supplied process"');
 });
 it('does not assign a service fee to an action that has no supplied fee link',()=>{
  const doc=structuredClone(fixture.document) as unknown as Journey['document'];
  const stage=doc.stages[0],fee=doc.facts.find(f=>f.fact_id===stage.fee_fact_id)!;
  doc.actions=doc.actions.slice(0,2);doc.actions.forEach(a=>{a.service_id=stage.service_id;a.fact_ids=[];});
  doc.actions[0].fact_ids=[fee.fact_id];
  const html=renderToStaticMarkup(<PreparationSummary doc={doc}/>);
  const row=[...html.matchAll(/<li>([\s\S]*?)<\/li>/g)].map(m=>m[1]).find(text=>text.startsWith(stage.name+':'))!;
  expect(row).toContain(doc.actions[0].title);expect(row).not.toContain(doc.actions[1].title);
 });
 it('never filters joint requirements as exclusive routes',()=>{
  const j=structuredClone(fixture) as unknown as Journey;const branch=j.document.branches[0];branch.selection='AND';
  j.seen=j.document.actions.map(a=>a.id);j.focused_routes={[branch.group_id]:branch.options[0].option_id};
  const prior=previousActions(j,j.document.actions.at(-1)!.id).map(a=>a.id);
  expect(prior).toContain(branch.options[0].action_ids[0]);expect(prior).toContain(branch.options[1].action_ids[0]);
  const html=renderToStaticMarkup(<GuidanceMessage journey={j} event={vi.fn()} adjust={vi.fn()} rate={vi.fn()}/>);
  expect(html).toContain('joint requirements');expect(html).not.toContain('Focus this route');
 });
 it('associates a stage fee with its own actions rather than every source mention',()=>{
  const j=structuredClone(fixture) as unknown as Journey;
  const last=j.document.actions.at(-1)!;
  const stage=j.document.stages.find(s=>s.service_id===last.service_id)!;
  const html=renderToStaticMarkup(<PreparationSummary doc={j.document}/>);
  const row=[...html.matchAll(/<li>([\s\S]*?)<\/li>/g)].map(m=>m[1]).find(text=>text.startsWith(stage.name+':'))!;
  expect(row).toContain('Service-level charge; no action-level fee inferred.');
  expect(row).not.toContain(j.document.actions[0].title);
 });
});
